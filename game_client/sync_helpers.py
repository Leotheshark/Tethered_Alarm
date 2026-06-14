"""
遠端實體同步輔助模組。

提供所有小遊戲共用的「Dead Reckoning + LERP」遠端位置平滑邏輯，
讓任何持有 x/y 的物件都能透過 RemoteSyncState + tick_remote_sync 取得一致的同步行為。

使用方式：
    state = RemoteSyncState(x, y)               # 建立同步狀態（建議與實體初始位置一致）
    ...
    apply_server_update(state, x, y, dx, dy)    # 收到伺服器封包時呼叫
    ...
    tick_remote_sync(entity, state, dt,         # 每幀對遠端實體呼叫
                     speed=PLAYER_SPEED,
                     bounds=(min_x, min_y, max_x, max_y))
"""

from dataclasses import dataclass


# 預設參數：個別呼叫端可在 tick_remote_sync 覆寫
DEFAULT_LERP_SPEED = 24   # 降低係數以獲得更平滑的追蹤效果，減少網路抖動造成的跳動感
DEFAULT_DR_TIMEOUT = 0.15 # 超過此秒數未收到封包則啟動 Dead Reckoning


@dataclass
class RemoteSyncState:
    """單一遠端實體的同步狀態（伺服器目標、最後速度、封包時效）。"""
    target_x: float = 0.0
    target_y: float = 0.0
    dr_dx: float = 0.0      # 上次封包帶來的速度方向（單位向量）
    dr_dy: float = 0.0
    stale_time: float = 0.0 # 距上次收到封包的秒數


def apply_server_update(state: RemoteSyncState, x: float, y: float,
                        dx: float = 0.0, dy: float = 0.0) -> None:
    """收到伺服器轉發的封包時呼叫：更新目標與最後速度方向，重置 stale 計時。"""
    state.target_x = x
    state.target_y = y
    state.dr_dx = dx
    state.dr_dy = dy
    state.stale_time = 0.0


def reset_sync_state(state: RemoteSyncState, x: float, y: float) -> None:
    """重置同步狀態到指定位置（小遊戲 on_enter 時呼叫，避免上局殘留 target 拖動畫面）。"""
    state.target_x = x
    state.target_y = y
    state.dr_dx = 0.0
    state.dr_dy = 0.0
    state.stale_time = 0.0


def tick_remote_sync(entity, state: RemoteSyncState, dt: float, speed: float,
                     bounds: tuple[float, float, float, float] | None = None,
                     lerp_speed: float = DEFAULT_LERP_SPEED,
                     dr_timeout: float = DEFAULT_DR_TIMEOUT) -> None:
    """
    對遠端實體每幀進行 Dead Reckoning + LERP：
    1. 累加 stale_time。
    2. 若封包過舊且最後速度非零，將 target 沿 (dr_dx, dr_dy) 推進（DR 預測）。
    3. 視 bounds 將 target 夾緊在合法範圍內，避免預測超出地圖造成渲染漂移。
    4. 用 LERP 讓 entity.x/y 平滑逼近 target。

    :param entity:     任何具有 x、y 屬性的物件，會被直接更新。
    :param state:      該實體對應的 RemoteSyncState。
    :param dt:         本幀時間。
    :param speed:      DR 推進速度（像素/秒），通常等於該實體在小遊戲中的常態速度。
    :param bounds:     可選的 (min_x, min_y, max_x, max_y) 邊界。
    :param lerp_speed: LERP 係數，越大越貼近 target。
    :param dr_timeout: 距上次封包多少秒後啟動 DR。
    """
    state.stale_time += dt

    if state.stale_time > dr_timeout and (state.dr_dx != 0 or state.dr_dy != 0):
        state.target_x += state.dr_dx * speed * dt
        state.target_y += state.dr_dy * speed * dt
        if bounds is not None:
            min_x, min_y, max_x, max_y = bounds
            state.target_x = max(min_x, min(max_x, state.target_x))
            state.target_y = max(min_y, min(max_y, state.target_y))

    factor = min(1.0, lerp_speed * dt)
    entity.x += (state.target_x - entity.x) * factor
    entity.y += (state.target_y - entity.y) * factor

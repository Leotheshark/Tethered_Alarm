"""
Reverse Pac-Man 小遊戲邏輯模組。

玩法概述：
- 玩家在迷宮中移動並吃掉所有「飼料（pellet）」，過程中需要按下按鈕開啟對應的閘門。
- Pac-Man 是敵人，玩家需閃躲 Pac-Man 的追蹤。
- 被 Pac-Man 碰到後需隊友在原地按 E 救援（每人最多 2 次，超出則永久無法動作）。
- 所有 pellet 吃完即通關。

授權客戶端（藍色玩家所在機器）執行 Pac-Man AI，並每隔 100ms 廣播 Pac-Man 位置，
其他客戶端接收廣播後純粹更新渲染位置，不自行計算 AI。
"""

import math
import time
from collections import deque

from games.base_game import BaseLogicInterface
from entities import Ghost, PLAYER_SPEED
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（飼料）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）

# ─── 地圖定義（17 行 × 32 列，TILE_SIZE=60px，符合 1920x1080） ──────────────
MAP_LAYOUT = [
    # 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 0
    [W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 1
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W],  # 2
    [W, P, W, W, B, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, W, W, P, P, P, G, B, W, W, W, W, W],  # 3
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W],  # 4
    [W, P, P, P, P, P, P, G, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 5
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, W],  # 6
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, W],  # 7
    [W, P, P, P, P, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W, P, P, P, W],  # 8
    [W, W, W, W, P, W, P, W, W, W, W, W, P, W, W, P, W, W, P, W, W, W, W, W, P, W, P, W, W, W, W, W],  # 9
    [W, P, P, P, P, P, P, P, P, P, P, P, P, W, W, P, W, W, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 10
    [W, W, W, W, P, W, P, W, W, W, W, W, P, W, W, P, W, W, P, W, W, W, W, W, P, W, P, W, W, W, P, W],  # 11
    [W, W, W, W, P, W, G, W, W, W, W, W, P, W, W, P, W, W, P, W, W, W, W, W, P, W, P, W, W, W, P, W],  # 11
    [W, P, P, P, P, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W, P, P, P, W],  # 12
    [W, P, W, W, B, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, P, W, P, W, W, W, B, W, W, W, P, W],  # 13
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, P, W, P, W, W, W, P, W, W, W, P, W],  # 14
    [W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, G, P, P, P, W],  # 15
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 16
]

ROWS = len(MAP_LAYOUT)
COLS = len(MAP_LAYOUT[0])
TILE_SIZE = 60
AVATAR_SIZE = 24

# ─── 玩家初始出生位置（格座標，依顏色）──────────────────────────────────────
SPAWN_TILES = {
    "blue":  (1, 1),    # 左上
    "green": (15, 30),  # 右下（移動到新的倒數第二行）
    "pink":  (1, 30),   # 右上
    "red":   (16, 1),   # 左下
}

# Pac-Man 初始出生格
PACMAN_SPAWN_TILE = (8, 16)  # 地圖中心

# ─── 遊戲數值常數 ─────────────────────────────────────────────────────────────
# PLAYER_SPEED 由 entities.py 提供，確保與 Ghost 預設速度一致
PACMAN_BASE_SPEED   = 100   # 正常速度
PACMAN_FAST_SPEED   = 165   # 被獵食後暫時加速（1.5 倍）
CATCH_RADIUS        = 56    # 增加捕捉半徑，配合 64x64 的角色尺寸
MAX_RESCUES         = 2     # 每位玩家被救援的上限次數
RESCUE_RADIUS       = 70   # 救援互動的有效距離（像素）
RESCUE_HOLD_TIME    = 2.0   # 按住 E 多少秒才完成救援
DEBUFF_DURATION     = 15.0  # 被抓後移速減半持續秒數
SPIKE_SLOW_DURATION = 3.0   # 釘板緩速持續秒數
PACMAN_BOOST_DURATION = 5.0 # 吃掉 pellet 後短暫加速秒數
PACMAN_AI_INTERVAL  = 0.10  # 授權客戶端廣播 Pac-Man 位置的時間間隔（秒）

# 按鈕 → 閘門 的映射（格座標對）
# 鍵：button (row, col)，值：gate (row, col)
BUTTON_GATE_MAP = {
    (3,  4):  (16, 27),   # Button A (左上) -> Gate (右下)
    (14, 4):  (3,  25),   # Button B (左下) -> Gate (右上)
    (3,  26): (12, 6),    # Button C (右上) -> Gate (左下)
    (14, 26): (5,  7),    # Button D (右下) -> Gate (左上)
}

def tile_center(row, col):
    """回傳指定格子中心點的像素座標 (x, y)。"""
    x = col * TILE_SIZE + TILE_SIZE // 2
    y = row * TILE_SIZE + TILE_SIZE // 2
    return x, y


def pixel_to_tile(px, py):
    """將像素座標轉換為格座標 (row, col)，用於碰撞查詢。"""
    col = int(px / TILE_SIZE)
    row = int(py / TILE_SIZE)
    return row, col


def is_wall(tile_map, row, col):
    """判斷指定格座標是否為牆壁或閘門（不可通行）。"""
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return True  # 超出邊界視為牆
    t = tile_map[row][col]
    return t == W or t == G


def bfs_next_step(tile_map, start_row, start_col, goal_row, goal_col):
    """
    使用 BFS 在格座標上找出從 start 到 goal 的最短路徑，
    回傳第一步的方向向量 (dr, dc)，若無路徑則回傳 (0, 0)。
    """
    if (start_row, start_col) == (goal_row, goal_col):
        return 0, 0

    queue = deque()
    queue.append((start_row, start_col, []))
    visited = {(start_row, start_col)}

    while queue:
        r, c, path = queue.popleft()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if (nr, nc) in visited:
                continue
            if is_wall(tile_map, nr, nc):
                continue
            visited.add((nr, nc))
            new_path = path + [(dr, dc)]
            if nr == goal_row and nc == goal_col:
                return new_path[0] if new_path else (0, 0)
            queue.append((nr, nc, new_path))

    return 0, 0  # 找不到路徑


class PlayerState(Ghost):
    """單一玩家在小遊戲中的所有狀態資料。"""

    def __init__(self, color, spawn_row, spawn_col):
        self.rescue_count = 0       # 已被救援次數
        self.debuff_timer = 0.0     # 被救援後的速度減半倒數
        self.spike_timer = 0.0      # 踩到釘板後的緩速倒數
        self.rescue_progress = 0.0  # 隊友救援進度
        # 是否正在被某人救援；所有 client 收到 rescue_progress_start 後設為 True，
        # 進入 update 後本地以 dt 累加 rescue_progress，讓畫面上的進度弧線在每台都會動。
        self.being_rescued = False

        super().__init__(color_key=color, avatar_size=AVATAR_SIZE)
        self.speed = PLAYER_SPEED # 更新為小遊戲專用的速度數值
        cx, cy = tile_center(spawn_row, spawn_col)
        self.x, self.y = float(cx), float(cy)
        # 遠端同步狀態（target + Dead Reckoning），本地玩家不使用
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    @property
    def speed(self):
        """根據當前狀態決定移動速度（釘板或被救後減半）。"""
        if not self.is_alive:
            return 0.0
        # 使用被設定的基礎速度，若無則回退至常數
        base = getattr(self, '_base_speed', PLAYER_SPEED)
        if self.debuff_timer > 0 or self.spike_timer > 0:
            base *= 0.5
        return base

    @speed.setter
    def speed(self, value):
        self._base_speed = value

    @property
    def permanently_down(self):
        """已達最大救援次數且再次倒下，無法再被救援。"""
        return not self.is_alive and self.rescue_count >= MAX_RESCUES


class PacManState:
    """Pac-Man 的位置、速度、目標玩家等狀態。"""

    def __init__(self):
        sr, sc = PACMAN_SPAWN_TILE
        cx, cy = tile_center(sr, sc)
        self.x = float(cx)
        self.y = float(cy)
        self.speed_boost_timer = 0.0    # 吃到 pellet 後短暫加速的倒數計時
        self.current_target_id = None   # 目前追蹤的玩家 ID（字串）
        self.avatar_size = AVATAR_SIZE  # 讓 Pac-Man 也具備尺寸屬性

        # 格子對齊移動：鎖定下一個目標格的中心點，到達後再重新 BFS
        self.next_tile_x = float(cx)    # 目前正在朝向的格中心 X
        self.next_tile_y = float(cy)    # 目前正在朝向的格中心 Y
        # 遠端同步狀態（target + Dead Reckoning），授權端不使用
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    @property
    def speed(self):
        return PACMAN_FAST_SPEED if self.speed_boost_timer > 0 else PACMAN_BASE_SPEED


class ReversePacman(BaseLogicInterface):
    """
    Reverse Pac-Man 小遊戲的完整邏輯實作。

    授權分配：
    - 顏色為 "blue" 的玩家所在客戶端負責執行 Pac-Man AI 並廣播位置。
    - 其他客戶端接收廣播，只更新本地的渲染座標。
    """

    def __init__(self, socket_client, player_id_list):
        super().__init__(socket_client, player_id_list)

        # 取得本地玩家資訊
        self.local_color = socket_client.player_color       # 本機玩家顏色
        self.local_pid = socket_client.player_id            # 本機玩家 Socket ID

        # 判斷本機是否為 Pac-Man AI 授權客戶端：名單第一位負責
        # 改用顏色判定，因為伺服器保證第一個訂閱房間的是藍色，這比動態列表更穩定
        self.is_pacman_authority = (self.local_color == "blue")

        # 地圖狀態：使用可修改的二維陣列（原始 MAP_LAYOUT 不應被修改）
        self.tile_map = [row[:] for row in MAP_LAYOUT]

        # 統計尚未被吃掉的 pellet 數量，用於判定通關
        self.pellets_remaining = sum(
            1 for row in self.tile_map for t in row if t == P
        )

        # 哪些閘門目前是開著的（格座標 set）
        self.open_gates = set()

        # 所有玩家狀態字典 { color: PlayerState }
        # 依照 player_id_list 的順序依次對應 colors
        colors = ["blue", "green", "pink", "red"]
        self.players: dict[str, PlayerState] = {}
        for i, pid in enumerate(player_id_list):
            color = colors[i % len(colors)]
            sr, sc = SPAWN_TILES.get(color, (10, 1))
            self.players[color] = PlayerState(color, sr, sc)

        # Pac-Man 狀態（所有客戶端都持有，AI 客戶端計算，其餘接收）
        self.pacman = PacManState()

        # Pac-Man AI 廣播計時器
        self._pacman_broadcast_timer = 0.0

        # 遊戲是否通關
        self._cleared = False

        # 本地玩家輸入向量（由 handle_event 設定）
        self._input_dx = 0
        self._input_dy = 0

        # 正在對哪個倒地玩家進行救援（color 字串），None 表示未在救援
        self._rescuing_target: str | None = None

    # ─────────────────────────────────────────────────────────────────────
    # BaseLogicInterface 生命週期方法
    # ─────────────────────────────────────────────────────────────────────

    def on_enter(self, params: dict = None):
        """重置所有遊戲狀態，準備開始。"""
        super().on_enter(params)
        # 重置地圖（恢復所有 pellet 與閘門）
        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.pellets_remaining = sum(1 for row in self.tile_map for t in row if t == P)
        self.open_gates.clear()

        # 重置所有玩家至出生點
        colors = ["blue", "green", "pink", "red"]
        for i, pid in enumerate(self.player_id_list):
            color = colors[i % len(colors)]
            if color in self.players:
                sr, sc = SPAWN_TILES.get(color, (10, 1))
                cx, cy = tile_center(sr, sc)
                p = self.players[color]
                p.x, p.y = float(cx), float(cy)
                reset_sync_state(p.sync, float(cx), float(cy))
                p.is_alive = True
                p.visual_key = f"{color}_{p.direction}"
                p.rescue_count = 0
                p.debuff_timer = 0.0
                p.spike_timer = 0.0
                p.rescue_progress = 0.0
                p.being_rescued = False

        # 重置 Pac-Man
        sr, sc = PACMAN_SPAWN_TILE
        cx, cy = tile_center(sr, sc)
        self.pacman.x, self.pacman.y = float(cx), float(cy)
        self.pacman.next_tile_x, self.pacman.next_tile_y = float(cx), float(cy)
        reset_sync_state(self.pacman.sync, float(cx), float(cy))
        self.pacman.speed_boost_timer = 0.0
        self.pacman.current_target_id = None

        self._cleared = False
        self._input_dx = 0
        self._input_dy = 0
        self._rescuing_target = None
        print("[ReversePacman] game started")

    def on_exit(self):
        """清理遊戲資源。"""
        super().on_exit()
        print("[ReversePacman] game exited")

    def handle_event(self, event_data: dict):
        """
        處理本地玩家的輸入事件。
        event_data 格式：{ 'type': 'move', 'dx': int, 'dy': int }
                         { 'type': 'rescue_start' }
                         { 'type': 'rescue_stop' }
        """
        etype = event_data.get("type")
        if etype == "move":
            # 更新本地輸入方向向量（由 engine 每幀傳入）
            self._input_dx = event_data.get("dx", 0)
            self._input_dy = event_data.get("dy", 0)
        elif etype == "rescue_start":
            # 玩家按下 E：掃描附近是否有倒地的隊友
            self._rescuing_target = self._find_rescue_target()
            # DEBUG：印出本機看到的所有玩家狀態，協助診斷救援為何失敗
            local = self.players.get(self.local_color)
            local_pos = (local.x, local.y) if local else None
            states = {
                c: {
                    "is_alive": p.is_alive,
                    "perm_down": p.permanently_down,
                    "rescue_count": p.rescue_count,
                    "pos": (round(p.x, 1), round(p.y, 1)),
                    "dist_to_local": round(math.hypot(p.x - local.x, p.y - local.y), 1) if local else None,
                }
                for c, p in self.players.items()
            }
            print(f"[ReversePacman] rescue_start by {self.local_color} at {local_pos} -> target={self._rescuing_target}")
            print(f"[ReversePacman]   all players: {states}")

            # 廣播救援開始，讓其他 client 在本機累加進度條（畫面同步）
            if self._rescuing_target:
                target = self.players.get(self._rescuing_target)
                if target:
                    target.being_rescued = True
                    target.rescue_progress = 0.0
                try:
                    self.socket_client.send_game_event({
                        "type": "rescue_progress_start",
                        "color": self._rescuing_target,
                    })
                except Exception:
                    pass
        elif etype == "rescue_stop":
            # 玩家放開 E：取消救援進度，並廣播給其他 client 一起清掉本機進度條
            if self._rescuing_target:
                target = self.players.get(self._rescuing_target)
                if target:
                    target.rescue_progress = 0.0
                    target.being_rescued = False
                try:
                    self.socket_client.send_game_event({
                        "type": "rescue_progress_stop",
                        "color": self._rescuing_target,
                    })
                except Exception:
                    pass
            self._rescuing_target = None

    def update(self, dt: float):
        """每幀更新所有玩家移動、Pac-Man AI、碰撞偵測、救援計時。"""
        if not self.is_active or self._cleared:
            return

        local = self.players.get(self.local_color)

        # 1. 更新本地玩家移動
        if local and local.is_alive and not local.permanently_down:
            # 收集其他玩家的碰撞矩形（包含倒地者）
            other_rects = [p.rect for c, p in self.players.items() if c != self.local_color]
            # 使用封裝在實體中的移動邏輯
            local.move(
                self._input_dx, self._input_dy, dt, 
                TILE_SIZE, 
                lambda px, py: is_wall(self.tile_map, *pixel_to_tile(px, py)),
                others=other_rects
            )
            # 移動後處理地圖互動
            self._handle_tile_interaction(local)

        # 2. 更新所有玩家的計時器（debuff、spike）
        for p in self.players.values():
            p.update(dt) # 驅動動畫影格
            if p.debuff_timer > 0:
                p.debuff_timer = max(0.0, p.debuff_timer - dt)
            if p.spike_timer > 0:
                p.spike_timer = max(0.0, p.spike_timer - dt)

        # 2.5. 遠端實體位置同步：交由 sync_helpers 統一處理 Dead Reckoning + LERP
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE,
                      COLS * TILE_SIZE - AVATAR_SIZE,
                      ROWS * TILE_SIZE - AVATAR_SIZE)
        for color, p in self.players.items():
            if color == self.local_color:
                continue
            tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

        # 非授權端的 Pac-Man：同套邏輯（授權端用 AI 直接更新，不參與）
        if not self.is_pacman_authority:
            tick_remote_sync(self.pacman, self.pacman.sync, dt, PACMAN_BASE_SPEED,
                             bounds=map_bounds)

        # 3. 處理救援進度
        # 3a. 本機是救援者：每幀累加目標的 rescue_progress，並在完成 / 中斷時廣播
        if self._rescuing_target:
            target = self.players.get(self._rescuing_target)
            in_range = False
            dist_now = None
            if target and local:
                dist_now = math.hypot(local.x - target.x, local.y - target.y)
                in_range = dist_now <= RESCUE_RADIUS
            # DEBUG：每約 0.5 秒印一次進度狀態，避免洗版
            self._rescue_debug_timer = getattr(self, "_rescue_debug_timer", 0.0) + dt
            if self._rescue_debug_timer >= 0.5:
                self._rescue_debug_timer = 0.0
                t_alive = target.is_alive if target else "no-target"
                t_perm = target.permanently_down if target else "no-target"
                t_prog = round(target.rescue_progress, 2) if target else "no-target"
                print(f"[ReversePacman] rescuing {self._rescuing_target}: alive={t_alive} perm={t_perm} dist={round(dist_now or -1, 1)} in_range={in_range} progress={t_prog}")
            if target and not target.is_alive and not target.permanently_down and in_range:
                target.rescue_progress += dt
                if target.rescue_progress >= RESCUE_HOLD_TIME:
                    # 救援完成：復活目標玩家
                    target.is_alive = True
                    target.visual_key = f"{target.color_key}_{target.direction}"
                    target.rescue_count += 1
                    target.debuff_timer = DEBUFF_DURATION  # 被救後速度減半
                    target.rescue_progress = 0.0
                    target.being_rescued = False
                    rescued_color = self._rescuing_target
                    self._rescuing_target = None
                    print(f"[ReversePacman] {target.color_key} rescued (count={target.rescue_count})")
                    # 廣播給其他 client（含被救者本人、Pac-Man authority）
                    # 其他 client 收到 player_rescued 時會一併清掉 being_rescued
                    try:
                        self.socket_client.send_game_event({
                            "type": "player_rescued",
                            "color": rescued_color,
                            "rescue_count": target.rescue_count,
                        })
                    except Exception:
                        pass
            else:
                # 目標已復活、消失，或本地玩家走出救援範圍：中斷救援並通知其他 client
                interrupted_color = self._rescuing_target
                if target:
                    target.rescue_progress = 0.0
                    target.being_rescued = False
                self._rescuing_target = None
                try:
                    self.socket_client.send_game_event({
                        "type": "rescue_progress_stop",
                        "color": interrupted_color,
                    })
                except Exception:
                    pass

        # 3b. 其他 client（旁觀者、被救者）：對 being_rescued=True 的玩家本機累加進度條，
        # 確保畫面上的進度弧線在每台都會動。救援完成 / 中斷時由事件清掉旗標。
        for color, p in self.players.items():
            if color == self._rescuing_target:
                continue  # 本機是救援者，已在 3a 處理
            if p.being_rescued and not p.is_alive and not p.permanently_down:
                p.rescue_progress = min(p.rescue_progress + dt, RESCUE_HOLD_TIME)

        # 3.5. 壓力板閘門：authority 每幀重新評估，狀態變化才廣播
        # 放在 Pac-Man AI 之前，確保 AI 用最新的閘門牆壁狀態做 BFS
        if self.is_pacman_authority:
            self._evaluate_gates()

        # 4. Pac-Man AI（僅授權客戶端執行）
        if self.is_pacman_authority:
            self._update_pacman_ai(dt)
            self._pacman_broadcast_timer += dt
            if self._pacman_broadcast_timer >= PACMAN_AI_INTERVAL:
                self._pacman_broadcast_timer = 0.0
                # 廣播 Pac-Man 最新位置 + 當下速度向量（單位化），供非授權端做 Dead Reckoning
                dx_raw = self.pacman.next_tile_x - self.pacman.x
                dy_raw = self.pacman.next_tile_y - self.pacman.y
                norm = math.hypot(dx_raw, dy_raw)
                if norm > 0:
                    pm_dx, pm_dy = dx_raw / norm, dy_raw / norm
                else:
                    pm_dx, pm_dy = 0.0, 0.0
                try:
                    self.socket_client.send_game_event({
                        "type": "pacman_pos",
                        "x":  self.pacman.x,
                        "y":  self.pacman.y,
                        "dx": pm_dx,
                        "dy": pm_dy,
                    })
                except Exception:
                    pass

        # 5. 更新 Pac-Man 加速計時器
        if self.pacman.speed_boost_timer > 0:
            self.pacman.speed_boost_timer = max(0.0, self.pacman.speed_boost_timer - dt)

        # 6. 通關判定
        if self.pellets_remaining <= 0:
            self._cleared = True
            print("[ReversePacman] cleared! all pellets eaten")

    def get_render_data(self) -> dict:
        """回傳渲染器需要的所有物件資料。"""
        return {
            "tile_map":    self.tile_map,
            "tile_size":   TILE_SIZE,
            "open_gates":  list(self.open_gates),      # [(row, col), ...]
            "pellets_left": self.pellets_remaining,
            "pacman": {
                "x": self.pacman.x,
                "y": self.pacman.y,
                "avatar_size": self.pacman.avatar_size,
            },
            "players": {
                color: {
                    "x":              p.x,
                    "y":              p.y,
                    "is_alive":       p.is_alive,
                    "permanently_down": p.permanently_down,
                    "rescue_progress": p.rescue_progress,
                    "rescue_count":   p.rescue_count,
                    "debuff":         p.debuff_timer > 0,
                    "spike":          p.spike_timer > 0,
                    "dx":             p.current_dx,
                    "dy":             p.current_dy,
                    "avatar_size":    p.avatar_size,
                    "visual_key":     p.visual_key,
                    "frame_index":    p.frame_index,
                }
                for color, p in self.players.items()
            },
        }

    def is_cleared(self) -> bool:
        """所有 pellet 吃完時通關。"""
        return self._cleared

    def get_sync_data(self) -> dict:
        """
        打包本地玩家位置封包，供主引擎定期廣播。
        Pac-Man 位置由授權客戶端單獨廣播，不在此封包中。
        """
        local = self.players.get(self.local_color)
        if not local:
            return {}
        return {
            "type":  "player_pos",
            "color": self.local_color,
            "x":     local.x,
            "y":     local.y,
            "dx":    local.current_dx,
            "dy":    local.current_dy,
            "is_alive": local.is_alive,
        }

    def receive_sync_data(self, data: dict):
        """
        接收來自其他客戶端的遊戲封包：
        - player_pos：遠端玩家位置同步
        - pacman_pos：Pac-Man 位置同步（非授權客戶端接收）
        - gate_open：閘門狀態同步（觸發按鈕的客戶端廣播）
        - pellet_eaten：pellet 被吃掉的同步
        """
        dtype = data.get("type")

        if dtype == "player_pos":
            color = data.get("color")
            p = self.players.get(color)
            if p and color != self.local_color:
                # 玩家封包的 dx/dy 是原始輸入方向（含斜向 1+1），需正規化才能正確用於 Dead Reckoning
                raw_dx = data.get("dx", 0.0)
                raw_dy = data.get("dy", 0.0)
                if raw_dx != 0 and raw_dy != 0:
                    raw_dx *= 0.7071
                    raw_dy *= 0.7071
                
                # 更新遠端玩家視覺朝向
                if raw_dx > 0: p.direction = "right"
                elif raw_dx < 0: p.direction = "left"
                elif raw_dy != 0: p.direction = "frontback"
                else: p.direction = "idle"
                p.visual_key = f"{p.color_key}_{p.direction}"

                apply_server_update(p.sync,
                                    data.get("x", p.sync.target_x),
                                    data.get("y", p.sync.target_y),
                                    raw_dx, raw_dy)
                p.current_dx = data.get("dx", p.current_dx)
                p.current_dy = data.get("dy", p.current_dy)
                # 不直接覆寫 alive：alive 的權威來源是 player_caught / player_rescued 兩個事件。
                # 被抓的玩家自己 client 在收到 player_caught 之前，仍會持續用 player_pos
                # 廣播 alive=True，若這裡蓋回去會讓救援端的 _find_rescue_target 永遠找不到目標。

        elif dtype == "pacman_pos" and not self.is_pacman_authority:
            # Pac-Man 廣播的 dx/dy 已是單位向量，直接傳入
            apply_server_update(self.pacman.sync,
                                data.get("x", self.pacman.sync.target_x),
                                data.get("y", self.pacman.sync.target_y),
                                data.get("dx", 0.0), data.get("dy", 0.0))

        elif dtype == "gate_state":
            # 由 authority 廣播完整當前開啟集合：非 authority 直接套用，
            # 不自行判斷壓力板狀態，避免邏輯分歧。
            new_open = {tuple(g) for g in data.get("open_gates", [])}
            newly_closed = self.open_gates - new_open
            newly_open = new_open - self.open_gates

            for gr, gc in newly_open:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = E

            for gr, gc in newly_closed:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = G
                    # 閘門剛關上：本機是否有玩家站在門上需要推離
                    # （包含本機玩家自己，因為他的本機位置由 move_in_maze 控制，
                    # authority 推不到他，要靠本機收到事件後自己跳開）
                    self._push_players_off_gate(gr, gc)

            self.open_gates = new_open

        elif dtype == "pellet_eaten":
            rc = data.get("tile")  # [row, col]
            if rc:
                pr, pc = rc
                if 0 <= pr < ROWS and 0 <= pc < COLS:
                    if self.tile_map[pr][pc] == P:
                        self.tile_map[pr][pc] = E
                        self.pellets_remaining -= 1

        elif dtype == "player_caught":
            # 由 Pac-Man authority 廣播：標記玩家為倒地，避免被抓者本人持續送出 alive=True
            color = data.get("color")
            p = self.players.get(color)
            print(f"[ReversePacman] received player_caught: color={color} (local={self.local_color}, existing_alive={p.is_alive if p else 'N/A'}, rescue_count={p.rescue_count if p else 'N/A'})")
            if p and p.is_alive:
                p.is_alive = False
                p.rescue_progress = 0.0
                p.being_rescued = False  # 被抓時若剛好正在被救，清掉進度條旗標

        elif dtype == "player_rescued":
            # 由執行救援的 client 廣播：標記玩家為復活，套用 debuff 與救援次數
            color = data.get("color")
            p = self.players.get(color)
            print(f"[ReversePacman] received player_rescued: color={color} (local={self.local_color}, existing_alive={p.is_alive if p else 'N/A'})")
            if p and not p.is_alive:
                p.is_alive = True
                p.visual_key = f"{p.color_key}_{p.direction}"
                p.rescue_count = data.get("rescue_count", p.rescue_count + 1)
                p.debuff_timer = DEBUFF_DURATION
                p.rescue_progress = 0.0
                p.being_rescued = False  # 救援完成，清掉本機累加進度的旗標

        elif dtype == "rescue_progress_start":
            # 由救援者廣播：在本機標記目標為「正在被救援」，update 會自動累加進度條
            color = data.get("color")
            p = self.players.get(color)
            if p:
                if not p.is_alive: p.being_rescued = True
                p.rescue_progress = 0.0

        elif dtype == "rescue_progress_stop":
            # 由救援者廣播：放開 E 或走出範圍，本機清掉進度條
            color = data.get("color")
            p = self.players.get(color)
            if p:
                p.being_rescued = False
                p.rescue_progress = 0.0

    # ─────────────────────────────────────────────────────────────────────
    # 內部輔助方法
    # ─────────────────────────────────────────────────────────────────────

    def _handle_tile_interaction(self, player: PlayerState):
        """
        玩家中心格發生的互動：
        - P (pellet) → 吃掉，廣播 pellet_eaten
        - S (spike)  → 觸發緩速
        按鈕 (B) 是壓力板，由 authority 在 _evaluate_gates 每幀處理，這裡不再特別偵測。
        """
        row, col = pixel_to_tile(player.x, player.y)
        if row < 0 or row >= ROWS or col < 0 or col >= COLS:
            return

        tile = self.tile_map[row][col]

        if tile == P:
            # 本地玩家吃掉 pellet：更新本地地圖，廣播給其他人
            self.tile_map[row][col] = E
            self.pellets_remaining -= 1
            try:
                self.socket_client.send_game_event({
                    "type": "pellet_eaten",
                    "tile": [row, col],
                })
            except Exception:
                pass

        elif tile == S:
            # 踩到釘板：觸發緩速計時器
            if player.spike_timer <= 0:
                player.spike_timer = SPIKE_SLOW_DURATION

    def _update_pacman_ai(self, dt: float):
        """
        授權客戶端執行的 Pac-Man 格子對齊追蹤 AI。

        移動策略：
        1. Pac-Man 每次鎖定「下一個目標格的中心點」並直線移動過去。
        2. 到達目標格中心後，BFS 計算距最近存活玩家的下一步方向，鎖定新目標格。
        3. 這樣確保 Pac-Man 永遠沿格子走廊移動，不會卡在牆角或來回抖動。
        """
        pm = self.pacman
        speed = pm.speed

        # 計算距當前目標格中心點的距離
        dx = pm.next_tile_x - pm.x
        dy = pm.next_tile_y - pm.y
        dist = math.hypot(dx, dy)
        step = speed * dt

        if dist <= step:
            # 已到達（或超過）目標格中心：貼齊後重新選下一格
            pm.x = pm.next_tile_x
            pm.y = pm.next_tile_y

            pm_row, pm_col = pixel_to_tile(pm.x, pm.y)

            # 尋找最近的存活玩家
            best_dist = float("inf")
            best_color = None
            for color, p in self.players.items():
                if not p.is_alive:
                    continue
                pr, pc = pixel_to_tile(p.x, p.y)
                d = abs(pr - pm_row) + abs(pc - pm_col)
                if d < best_dist:
                    best_dist = d
                    best_color = color

            if best_color is None:
                return  # 全員倒地，停止移動

            tr, tc = pixel_to_tile(self.players[best_color].x, self.players[best_color].y)

            # BFS 找下一步方向（返回格偏移 dr/dc）
            dr, dc = bfs_next_step(self.tile_map, pm_row, pm_col, tr, tc)

            if dr == 0 and dc == 0:
                return  # 已在目標格，不移動

            # 鎖定下一格的中心點
            next_row = pm_row + dr
            next_col = pm_col + dc
            pm.next_tile_x, pm.next_tile_y = tile_center(next_row, next_col)

            # 繼續用剩餘的 step 補移動（避免低速時明顯停頓）
            remaining = step - dist
            ndx = pm.next_tile_x - pm.x
            ndy = pm.next_tile_y - pm.y
            nd = math.hypot(ndx, ndy)
            if nd > 0:
                pm.x += ndx / nd * remaining
                pm.y += ndy / nd * remaining
        else:
            # 尚未到達目標格：朝目標格中心直線移動
            pm.x += dx / dist * step
            pm.y += dy / dist * step

        # 碰撞偵測：Pac-Man 是否抓到任何存活玩家
        for color, p in self.players.items():
            if not p.is_alive:
                continue
            if math.hypot(pm.x - p.x, pm.y - p.y) < CATCH_RADIUS:
                self._catch_player(p)

    def _evaluate_gates(self):
        """
        壓力板邏輯（僅 authority 執行）：每幀檢查哪些 button 正被存活玩家踩著，
        進而決定哪些 gate 該開、哪些該關。狀態與上一幀有差異時：
        1. 更新本機 tile_map 與 open_gates
        2. 對「閘門剛關上但有玩家站在門上」的情況把玩家推到相鄰空地
        3. 廣播 gate_state 給其他 client（旁觀端不自己算，避免不一致）
        """
        # 1. 算出當下被踩的 button 座標集合（只看存活玩家、不看 Pac-Man）
        pressed_buttons = set()
        for p in self.players.values():
            if not p.is_alive:
                continue
            r, c = pixel_to_tile(p.x, p.y)
            if 0 <= r < ROWS and 0 <= c < COLS and (r, c) in BUTTON_GATE_MAP:
                pressed_buttons.add((r, c))

        # 2. 算出當下應該開啟的 gate 座標集合
        should_open = {BUTTON_GATE_MAP[btn] for btn in pressed_buttons}

        # 3. 找出狀態變化：新開的閘門與新關的閘門
        newly_open = should_open - self.open_gates
        newly_closed = self.open_gates - should_open

        if not newly_open and not newly_closed:
            return  # 無變化，省下廣播

        # 4. 套用本機變化
        for gr, gc in newly_open:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = E  # 開啟時視為空地
        for gr, gc in newly_closed:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = G  # 關上時恢復閘門
                # 把站在這格閘門上的玩家推到相鄰空地
                self._push_players_off_gate(gr, gc)

        self.open_gates = set(should_open)

        # 5. 廣播給其他 client，附帶完整當前開啟集合（power-on resync 也能正確）
        try:
            self.socket_client.send_game_event({
                "type": "gate_state",
                "open_gates": [list(g) for g in self.open_gates],
            })
        except Exception:
            pass

    def _push_players_off_gate(self, gr, gc):
        """
        閘門 (gr, gc) 剛關上，把站在這格上的玩家瞬移到相鄰空地，
        避免被卡在牆裡。優先嘗試上下左右四方向。
        """
        # 嘗試順序：上、下、左、右
        neighbors = [(gr - 1, gc), (gr + 1, gc), (gr, gc - 1), (gr, gc + 1)]
        for p in self.players.values():
            if not p.is_alive:
                continue
            pr, pc = pixel_to_tile(p.x, p.y)
            if (pr, pc) != (gr, gc):
                continue  # 不在這扇門上
            # 找第一個可通行的相鄰格
            for nr, nc in neighbors:
                if 0 <= nr < ROWS and 0 <= nc < COLS and not is_wall(self.tile_map, nr, nc):
                    nx = nc * TILE_SIZE + TILE_SIZE // 2
                    ny = nr * TILE_SIZE + TILE_SIZE // 2
                    p.x, p.y = float(nx), float(ny)
                    print(f"[ReversePacman] pushed {p.color_key} off closing gate ({gr},{gc}) -> ({nr},{nc})")
                    break
            else:
                # 四周都是牆，極端情況：留在原地（按理不會發生）
                print(f"[ReversePacman] gate ({gr},{gc}) closed but no empty neighbor for {p.color_key}")
            # 推離後重設遠端同步目標，避免 LERP 又把他拖回門裡
            reset_sync_state(p.sync, p.x, p.y)

    def _catch_player(self, player: PlayerState):
        """
        Pac-Man 抓到玩家的處理邏輯：
        - 若未達最大救援次數：將玩家標記為倒地。
        - 若已達最大次數：玩家永久無法動作（不再計入存活）。
        - Pac-Man 獲得短暫加速。
        - 廣播 player_caught 給其他 client，避免被抓者本人持續廣播 alive=True 把狀態蓋回去。
        """
        if not player.is_alive:
            return  # 已經倒地，不重複觸發

        player.is_alive = False
        player.visual_key = "dead"
        player.rescue_progress = 0.0
        self.pacman.speed_boost_timer = PACMAN_BOOST_DURATION
        print(f"[ReversePacman] {player.color_key} caught! rescue_count={player.rescue_count}")

        # 廣播給其他 client，包含被抓者本人，讓他停止輸入並更新 UI
        try:
            self.socket_client.send_game_event({
                "type": "player_caught",
                "color": player.color_key,
            })
        except Exception:
            pass

    def _find_rescue_target(self) -> str | None:
        """
        尋找本地玩家附近（RESCUE_RADIUS 內）倒地且未達最大救援次數的隊友。
        回傳目標顏色字串，或 None。
        """
        local = self.players.get(self.local_color)
        if not local:
            return None
        for color, p in self.players.items():
            if color == self.local_color:
                continue
            if p.is_alive or p.permanently_down:
                continue
            dist = math.hypot(local.x - p.x, local.y - p.y)
            if dist <= RESCUE_RADIUS:
                return color
        return None

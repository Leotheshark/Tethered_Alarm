"""
Reverse Pac-Man 小遊戲邏輯模組。

玩法概述（v2 蓄能版）：
- 移除「吃豆子」：地圖上的 pellet 全部視為空地。
- 通關改成「蓄能」：每位玩家有一個專屬蓄能點，跑到自己的點上長按 E 即可蓄滿自己的能量條；
  放開 E（或離開點 / 被抓倒地）能量會緩慢下降。四位玩家的能量條全部蓄滿且全員存活即通關。
- Pac-Man 是敵人，會持續追玩家。被碰到後需隊友在原地按住 E 救援。
- 死亡模型：沒有永久死亡，玩家永遠可被救；但每次被救都會累積一階「永久減速」，
  越救越慢，最後趨近一個地板值（幾乎動不了）。
- 失敗條件：四位玩家「同時」全部倒地。
- 壓力來源（取代倒數）：Pac-Man 會隨時間「階段性加速」並「複製」出更多隻。
- 陷阱：致盲迷霧（F）——踩到後本地視野縮小數秒（純本地視覺效果，不影響移速）。

授權客戶端（藍色玩家所在機器）執行 Pac-Man AI、升級排程與失敗/通關判定，並廣播狀態；
其他客戶端接收廣播後純粹更新渲染與本地能量條，不自行計算 AI。
"""
import pygame
import math
from collections import deque
from typing import Any

from games.player_game_base import (
    PlayerGameLogicInterface,
    W, E, P, G, B, S, F,
    TILE_SIZE, ROWS, COLS,
    RESCUE_RADIUS,
    FOG_VISION_RADIUS,
    DEFEAT_VOTE_TIME,
    tile_center, pixel_to_tile, is_wall, nearest_empty_tile
)
from entities import Ghost, PLAYER_SPEED, ColorButton, AVATAR_SIZE
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖定義（18 行 × 32 列，TILE_SIZE=60px）──────────────────────────────────
# 本檔內建這張關卡為唯一地圖來源（含牆、按鈕/閘門、釘板、迷霧與蓄能站）。
_FALLBACK_MAP_LAYOUT = [
    # 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 0
    [W, P, P, P, P, P, P, P, P, P, P, P, P, W, W, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 1
    [W, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W],  # 2
    [W, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W],  # 3
    [W, W, W, W, P, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W],  # 4
    [W, P, P, P, P, P, P, P, P, P, P, P, F, P, P, P, P, P, B, P, G, P, P, P, F, P, P, P, P, P, P, W],  # 5
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W, P, W],  # 6
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, W, P, W],  # 7
    [W, P, W, W, P, W, P, P, P, P, F, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 8
    [W, P, W, W, P, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, P, W, W, W, W, W],  # 9
    [W, G, W, W, P, F, P, P, P, P, P, P, G, W, W, B, W, W, P, P, P, P, P, P, P, W, P, P, P, P, P, W],  # 10
    [W, P, W, W, P, W, P, W, W, W, W, W, P, W, W, P, W, W, P, W, W, W, W, W, P, W, P, W, W, W, P, W],  # 11
    [W, P, W, W, P, W, P, W, W, W, W, W, P, W, W, P, W, W, P, W, W, W, W, W, P, W, P, W, W, W, P, W],  # 12
    [W, P, W, W, P, W, P, P, P, P, P, P, P, P, P, P, P, P, F, P, P, W, P, P, P, W, P, W, W, W, P, W],  # 13
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, P, W, P, W, W, W, P, W, W, W, P, W],  # 14
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, P, W, P, W, W, W, P, W, W, W, P, W],  # 15
    [W, P, P, P, P, P, P, P, F, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, G, P, P, P, W],  # 16
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 17
]

# ─── 玩家初始出生位置（格座標，依顏色）──────────────────────────────────────
_FALLBACK_SPAWN_TILES = {
    "blue":  (1, 1),    # 左上
    "green": (16, 30),  # 右下
    "pink":  (1, 30),   # 右上
    "red":   (16, 1),   # 左下
}

# Pac-Man 初始出生格（地圖中心，所有複製出的 Pac-Man 也從這裡誕生）
_FALLBACK_PACMAN_SPAWNS = [(8, 13), (8, 19)]

# ─── 蓄能點配置 ───────────────────────────────────────────────────────────────
# 每位玩家有一個專屬蓄能點，預設放在「中央危險區」的四個象限，逼玩家離開安全角落、
# 深入 Pac-Man 巢穴附近蓄能。下列為「理想格」，on_enter 會用 BFS 吸附到最近的空地，
# 確保一定落在可站立的格子（避免手動座標不小心落在牆裡）。
_FALLBACK_DESIRED_STATIONS = {
    "blue":  (15, 28),  # 右下
    "pink":  (11, 1),   # 左下
    "red":   (6, 20),  # 中央
    "green": (10, 11),  # 中央
}

# ─── 遊戲數值常數 ─────────────────────────────────────────────────────────────
# PLAYER_SPEED 由 entities.py 提供，確保與 Ghost 預設速度一致
PACMAN_BASE_SPEED   = 100   # Pac-Man 起始基礎速度（會隨時間升級）
PACMAN_BOOST_MULT   = 1.5
CATCH_RADIUS        = 56
RESCUE_HOLD_TIME    = 2.0
PACMAN_BOOST_DURATION = 2.0 # 吃掉玩家後短暫加速秒數
PACMAN_AI_INTERVAL  = 0.05  # 提升廣播頻率至 20Hz 以對齊玩家同步

# 復活累積永久減速：每被救一次，移速永久降一階，趨近地板值（幾乎動不了但仍能爬）
REVIVE_SLOW_STEP    = 0.18  # 每次復活的減速階（移速 = base × (1 - count×step)）
REVIVE_SLOW_FLOOR   = 0.12  # 減速地板（最低保留 12% 移速）

# 蓄能機制數值
BUTTON_HOLD_TIME    = 5 

# Pac-Man 階段升級排程（取代倒數計時的壓力來源；僅 authority 依此排程）
PACMAN_SPEED_STAGE_INTERVAL = 1  # 每幾秒提升一階基礎速度
PACMAN_SPEED_STAGE_STEP     = 1  # 每階增加的速度
PACMAN_SPEED_CAP            = 250   # 基礎速度上限
PACMAN_DUPLICATE_INTERVAL   = 5000  # 每幾秒複製出一隻新 Pac-Man
PACMAN_MAX_COUNT            = 4     # Pac-Man 數量上限


def bfs_next_step(tile_map, start_row, start_col, goal_row, goal_col, extra_walls=None):
    """
    使用 BFS 在格座標上找出從 start 到 goal 的最短路徑，
    回傳第一步的方向向量 (dr, dc)，若無路徑則回傳 (0, 0)。
    :param extra_walls: 可選的集合，包含要暫時視為牆壁的 (row, col) 座標。
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
            if is_wall(tile_map, nr, nc, ROWS, COLS) or (extra_walls and (nr, nc) in extra_walls):
                continue
            visited.add((nr, nc))
            new_path = path + [(dr, dc)]
            if nr == goal_row and nc == goal_col:
                return new_path[0] if new_path else (0, 0)
            queue.append((nr, nc, new_path))

    return 0, 0  # 找不到路徑


# ─── 關卡建構：用本檔內建常數組出唯一一張關卡 ──────────────────────────────────


def _snap_stations(tile_map, desired):
    """把理想蓄能點吸附到最近空地，確保一定落在可站立的格子。"""
    return {color: nearest_empty_tile(tile_map, r, c) for color, (r, c) in desired.items()}


def _clear_station_floor(tile_map, stations):
    """確保每個蓄能站底下是乾淨空地（清掉可能疊到的迷霧等）。"""
    rows, cols = len(tile_map), len(tile_map[0]) if tile_map else 0
    for (r, c) in stations.values():
        if 0 <= r < rows and 0 <= c < cols:
            tile_map[r][c] = E


def _build_level():
    """用本檔內建常數組出完整關卡（pellet→空地、疊迷霧、蓄能站吸附）。"""
    tile_map = [[E if t == P else t for t in row] for row in _FALLBACK_MAP_LAYOUT]
    
    gate_coords = []
    button_coords = []
    for r in range(ROWS):
        for c in range(COLS):
            t = tile_map[r][c]
            if t == G: gate_coords.append((r, c))
            if t == B: button_coords.append((r, c))

    stations = _snap_stations(tile_map, _FALLBACK_DESIRED_STATIONS)
    _clear_station_floor(tile_map, stations)
    return {
        "tile_map": tile_map, "rows": ROWS, "cols": COLS,
        "spawns": dict(_FALLBACK_SPAWN_TILES),
        "pacman_spawns": list(_FALLBACK_PACMAN_SPAWNS),
        "charge_stations": stations,
        "gate_coords": gate_coords,
        "button_coords": button_coords,
    }


# 建構一次，導出給下方 class 使用的最終地圖資料。
_LEVEL = _build_level()
SPAWN_TILES = _LEVEL["spawns"]
PACMAN_SPAWN_TILES = _LEVEL["pacman_spawns"]
GATE_COORDS = _LEVEL["gate_coords"]
BUTTON_COORDS = _LEVEL["button_coords"]
CHARGE_STATIONS = _LEVEL["charge_stations"]


def build_tile_map():
    """回傳一份可修改的最終地圖副本（已套用內建關卡設定，含迷霧）。"""
    return [row[:] for row in _LEVEL["tile_map"]]


class PacManState:
    """單一 Pac-Man 的位置、速度、目標玩家等狀態。"""

    def __init__(self, pacman_id, spawn_tile):
        self.id = pacman_id             # 唯一識別碼，用於多體 roster 同步對齊
        self.avatar_size = AVATAR_SIZE
        self.base_speed = PACMAN_BASE_SPEED  # 基礎速度（authority 隨時間升級）
        self.speed_boost_timer = 0.0    # 吃到玩家後短暫加速的倒數計時
        self.current_target_id = None   # 目前追蹤的玩家顏色

        sr, sc = spawn_tile
        cx, cy = tile_center(sr, sc)
        self.x = float(cx)
        self.y = float(cy)
        # 格子對齊移動：鎖定下一個目標格的中心點，到達後再重新 BFS
        self.next_tile_x = float(cx)
        self.next_tile_y = float(cy)

        self.direction = "left"         # 當前朝向：up, down, left, right
        self.frame_index = 0            # 1x2 影格索引
        self.animation_timer = 0.0      # 動畫計時
        self.animation_speed = 0.3     # 影格切換間隔

        # 遠端同步狀態（target + Dead Reckoning），授權端不使用
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    def update(self, dt):
        """更新動畫影格，確保頻率恆定且不隨轉向重置。"""
        # 使用模數運算維持連續的計時器循環 (0.0 ~ 0.6s)
        self.animation_timer = (self.animation_timer + dt) % (self.animation_speed * 2)
        # 直接根據總時間算出影格索引 (0 或 1)，確保咬合節奏完全獨立於移動邏輯
        self.frame_index = int(self.animation_timer // self.animation_speed)

    @property
    def speed(self):
        s = self.base_speed
        if self.speed_boost_timer > 0:
            s *= PACMAN_BOOST_MULT
        return s


class ReversePacman(PlayerGameLogicInterface):
    """
    Reverse Pac-Man（蓄能版）小遊戲的完整邏輯實作。
    
    基類提供的通用功能：
    - 玩家移動與碰撞
    - 救援邏輯
    - 地圖物體互動（釘板、迷霧）
    - 玩家位置重置與同步
    
    本類實現的特定功能：
    - Pac-Man AI 與追蹤
    - 蓄能站與按鈕邏輯
    - 通關與失敗判定
    - 失敗投票機制
    """

    def __init__(self, socket_client, player_id_list, sound_manager):
        # 地圖初始化（在 super().__init__ 之前必須完成，因為基類會呼叫虛擬方法）
        self.tile_map = build_tile_map()
        self.gate_coords = list(GATE_COORDS)
        self.button_coords = list(BUTTON_COORDS)
        self.open_gates = set()
        self._any_gate_pressed = False
        
        # 所有玩家狀態字典 { color: Ghost }
        colors = ["blue", "green", "pink", "red"]
        self.players: dict[str, Ghost] = {}
        for color in colors:
            sr, sc = SPAWN_TILES.get(color, (10, 1))
            self.players[color] = Ghost(color, avatar_size=AVATAR_SIZE, x=tile_center(sr, sc)[0], y=tile_center(sr, sc)[1])

        super().__init__(socket_client, player_id_list, sound_manager)

        # 取得本地玩家資訊
        self.local_color = socket_client.player_color
        self.local_pid = socket_client.player_id
        self.is_authority = bool(getattr(socket_client, "is_authority", self.local_color == "blue"))

        # 蓄能站與按鈕
        self.charge_stations = dict(_LEVEL["charge_stations"])
        self.buttons = []

        # Pac-Man 清單
        self.pacmen: list[PacManState] = [
            PacManState(0, PACMAN_SPAWN_TILES[0]), 
            PacManState(1, PACMAN_SPAWN_TILES[1])
        ]

        # 計時器
        self._pacman_broadcast_timer = 0.0
        self._elapsed = 0.0

        # 遊戲失敗旗標
        self._failed = False

        # 失敗投票
        self._voting = False
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False

        # 本地玩家輸入
        self._input_dx = 0
        self._input_dy = 0
        
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0

    # ─────────────────────────────────────────────────────────────────────
    # PlayerGameLogicInterface 虛擬方法實作
    # ─────────────────────────────────────────────────────────────────────

    def _get_player_dict(self) -> dict:
        """回傳玩家狀態字典。"""
        return self.players

    def get_map_data(self) -> dict:
        """回傳遊戲關卡的完整配置字典。"""
        return {
            "tile_map": [row[:] for row in self.tile_map],
            "spawn_points": dict(_LEVEL["spawns"]),
            "charge_stations": dict(_LEVEL["charge_stations"]),
            "gate_coords": list(_LEVEL["gate_coords"]),
            "button_coords": list(_LEVEL["button_coords"]),
            "pacman_spawns": list(_LEVEL["pacman_spawns"]),
        }

    def get_tile_at(self, x: float, y: float) -> int:
        """根據像素座標回傳磚片類型。"""
        row, col = pixel_to_tile(x, y)
        if row < 0 or row >= ROWS or col < 0 or col >= COLS:
            return None
        return self.tile_map[row][col]

    def on_player_move(self, player: Ghost, dx: float, dy: float, dt: float):
        """玩家移動後的特定邏輯（本遊戲無特殊移動規則，只在基類中處理）。"""
        pass

    def on_tile_interaction(self, player: Any, tile_type: int):
        """
        處理玩家踩踏的磚片互動。
        基類已自動處理 SPIKE 和 FOG，此方法用於遊戲特定的邏輯。
        """
        # ReversePacman 中，SPIKE 和 FOG 由基類自動處理
        # 子類可在此新增其他磚片類型的互動邏輯
        pass

    def on_player_caught(self, player: Ghost):
        """玩家被抓住時的處理（已在 _catch_player 中實作）。"""
        pass

    def on_player_rescued(self, player: Ghost, rescuer: Ghost):
        """玩家被救起時的處理。"""
        player.rescue_count += 1

    def get_rescue_radius(self) -> float:
        """救援檢測半徑。"""
        return RESCUE_RADIUS

    def get_rescue_hold_time(self) -> float:
        """救援需要的按住秒數。"""
        return RESCUE_HOLD_TIME

    # ─────────────────────────────────────────────────────────────────────
    # BaseLogicInterface 生命週期方法

    def on_enter(self, params: dict = None):
        """重置所有遊戲狀態，準備開始。"""
        super().on_enter(params)
        
        # 重置地圖
        self.tile_map = build_tile_map()
        self.open_gates.clear()
        self.charge_stations = dict(_LEVEL["charge_stations"])

        self.buttons.clear()
        for color, pos in self.charge_stations.items():
            rx, ry = tile_center(*pos)
            self.buttons.append(ColorButton(rx, ry, color))

        # 重置所有玩家
        for color, p in self.players.items():
            sr, sc = SPAWN_TILES.get(color, (10, 1))
            self.reset_player_position(p, sr, sc, TILE_SIZE)
            p.is_alive = True
            p.visual_key = f"{color}_{p.direction}"
            p.rescue_count = 0
            p.spike_timer = 0.0
            p.fog_timer = 0.0
            p.charge = 0.0

        # 重置 Pac-Man
        self.pacmen = [
            PacManState(0, PACMAN_SPAWN_TILES[0]), 
            PacManState(1, PACMAN_SPAWN_TILES[1])
        ]

        # 重置計時與旗標
        self._pacman_broadcast_timer = 0.0
        self._elapsed = 0.0
        self._failed = False
        self._voting = False
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False
        self._input_dx = 0
        self._input_dy = 0
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0
        self.is_input_locked = True
        
        # 重置基類的救援追蹤
        self._rescue_progress = {}
        
        print("[ReversePacman] game started (charge mode)")

    def on_exit(self):
        """清理遊戲資源。"""
        super().on_exit()
        print("[ReversePacman] game exited")

    def handle_event(self, event_data: dict):
        """
        處理本地玩家的輸入事件。
        event_data 格式：{ 'type': 'move', 'dx': int, 'dy': int }
                         { 'type': 'rescue_start' }   # E 鍵按下
                         { 'type': 'rescue_stop' }    # E 鍵放開
        E 鍵為情境鍵：附近有可救的倒地隊友 → 救援；否則站在自己蓄能點上 → 蓄能。
        投票期間（_voting）只處理 'vote'（由 engine 把 Y/N 轉入），其餘輸入忽略。
        """
        etype = event_data.get("type")

        # 失敗投票階段：只接受投票，且每人只投一次。
        if self._voting:
            if etype == "vote" and not self._local_voted:
                value = bool(event_data.get("value"))
                self._local_voted = True
                self._apply_vote(self.local_color, value)
                try:
                    self.socket_client.send_game_event({
                        "type": "vote_cast", "color": self.local_color, "value": value,
                    })
                except Exception as e:
                    print(f"[ReversePacman] vote_cast broadcast failed: {e}")
            return  # 投票期間凍結其餘輸入

        if etype == "move":
            # 更新本地輸入方向向量（由 engine 每幀傳入）
            self._input_dx = event_data.get("dx", 0)
            self._input_dy = event_data.get("dy", 0)

    def update(self, dt: float):
        """每幀更新所有玩家移動、Pac-Man AI、碰撞偵測、救援與蓄能計時。"""
        if not self.is_active or self._failed:
            return
        
        # 開場動畫邏輯
        if getattr(self, "start_anim_stage", 0) > 0 and self.start_anim_stage < 5:
            self.start_anim_timer += dt
            if self.start_anim_stage == 1 and self.start_anim_timer >= 1.0:
                self.start_anim_stage = 2
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 2 and self.start_anim_timer >= 0.3:
                self.start_anim_stage = 3
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 3 and self.start_anim_timer >= 1.5:
                self.start_anim_stage = 4
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 4 and self.start_anim_timer >= 0.3:
                self.start_anim_stage = 5
                self.start_anim_timer = 0.0
                self.is_input_locked = False
            
            # 開場期間仍需更新動畫影格
            for p in self.players.values():
                p.update(dt)
            return

        # 推進通關動畫狀態機
        self._update_clear_animation(dt)
        if super().is_cleared():
            return

        # 失敗投票階段：凍結遊戲邏輯
        if self._voting:
            self._update_defeat_vote(dt)
            return

        self._elapsed += dt
        local = self.players.get(self.local_color)

        # 1. 使用基類方法更新本地玩家移動
        self.update_player_movement(
            dt, local, self._input_dx, self._input_dy,
            lambda px, py: is_wall(self.tile_map, *pixel_to_tile(px, py)),
            TILE_SIZE
        )

        # 2. 更新所有玩家的計時器（spike、fog）與動畫
        for p in self.players.values():
            p.update(dt)  # 驅動動畫影格
            if p.spike_timer > 0:
                p.spike_timer = max(0.0, p.spike_timer - dt)
            if p.fog_timer > 0:
                p.fog_timer = max(0.0, p.fog_timer - dt)

        # 2.5. 使用基類方法更新遠端玩家位置同步
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE,
                      COLS * TILE_SIZE - AVATAR_SIZE,
                      ROWS * TILE_SIZE - AVATAR_SIZE)
        self.sync_remote_players(dt, PLAYER_SPEED, bounds=map_bounds)

        # 非授權端的所有 Pac-Man：以同套 Dead Reckoning + LERP 更新
        if not self.is_authority and self.clear_anim_stage == 0:
            for pm in self.pacmen:
                tick_remote_sync(pm, pm.sync, dt, pm.speed, bounds=map_bounds)

        # 3. 使用基類方法處理救援進度
        if not self.is_input_locked:
            self.update_rescues(dt, local)

        # 4. 蓄能邏輯
        if self.clear_anim_stage == 0:
            for btn in self.buttons:
                if btn.is_triggered:
                    continue
                owner = self.players.get(btn.assigned_color)
                on_button = (owner and owner.is_alive and btn.rect.colliderect(owner.rect))
                if on_button:
                    btn.charge_timer = min(BUTTON_HOLD_TIME, btn.charge_timer + dt)
                    if self.is_authority and not btn.is_triggered and btn.charge_timer >= BUTTON_HOLD_TIME:
                        btn.is_triggered = True
                        btn.activated_time = pygame.time.get_ticks()
                        self.sound_manager.play("charged")
                        self.socket_client.send_game_event({
                            "type": "button_activated", "color": btn.assigned_color
                        })
                else:
                    btn.charge_timer = max(0.0, btn.charge_timer - dt * 0.2)

        # 3.5. 壓力板閘門評估
        if self.is_authority:
            self._evaluate_gates()

        # 4. Pac-Man AI 與廣播
        if self.is_authority and self.clear_anim_stage == 0:
            self._escalate_pacmen()
            for pm in self.pacmen:
                pm.update(dt)
                self._update_pacman_ai(pm, dt)
            self._pacman_broadcast_timer += dt
            if self._pacman_broadcast_timer >= PACMAN_AI_INTERVAL:
                self._pacman_broadcast_timer = 0.0
                self._broadcast_pacman_roster()

        # 5. 更新 Pac-Man 動畫與加速計時器
        for pm in self.pacmen:
            if not self.is_authority:
                pm.update(dt)
            if pm.speed_boost_timer > 0:
                pm.speed_boost_timer = max(0.0, pm.speed_boost_timer - dt)

        # 6. 通關與失敗判定
        if self.is_authority:
            self._check_win_and_fail()

    def get_render_data(self) -> dict:
        """回傳渲染器需要的所有物件資料。"""
        local = self.players.get(self.local_color)
        # 蓄能站餵給 renderer 既有的「按鈕充能繪圖」重用：每站帶該玩家的能量進度
        stations = []
        for btn in self.buttons:
            stations.append({
                "x": btn.x,
                "y": btn.y,
                "color": btn.assigned_color,
                "progress": btn.charge_timer / BUTTON_HOLD_TIME,
                "triggered": btn.is_triggered,
                "activated_time": btn.activated_time,
            })

        return {
            "tile_map":    self.tile_map,
            "tile_size":   TILE_SIZE,
            "open_gates":  list(self.open_gates),
            "buttons":     stations,   # 蓄能站（重用 renderer 的按鈕充能繪圖）
            "fog_active":  bool(local and local.fog_timer > 0 and self.clear_anim_stage == 0),
            "fog_radius":  FOG_VISION_RADIUS,
            "clear_anim":  self._get_clear_anim_data(),
            "start_anim":  {"stage": getattr(self, "start_anim_stage", 0), "timer": getattr(self, "start_anim_timer", 0.0)},
            "pacmen": [
                {
                    "x": pm.x, "y": pm.y, "avatar_size": pm.avatar_size,
                    "visual_key": f"pacman_{pm.direction}",
                    "frame_index": pm.frame_index,
                }
                for pm in self.pacmen
            ],
            "players": {
                color: {
                    "x":              p.x,
                    "y":              p.y,
                    "is_alive":       p.is_alive,
                    "rescue_progress": p.rescue_progress,
                    "rescue_count":   p.rescue_count,
                    "spike":          p.spike_timer > 0,
                    "dx":             p.current_dx,
                    "dy":             p.current_dy,
                    "avatar_size":    p.avatar_size,
                    "visual_key":     p.visual_key,
                    "frame_index":    p.frame_index,
                }
                for color, p in self.players.items()
            },
            # 失敗投票畫面資料：renderer 依此繪製覆蓋層（未投票時 active=False）。
            "defeat_vote": {
                "active":      self._voting,
                "time_left":   max(0.0, DEFEAT_VOTE_TIME - self._vote_timer),
                "votes":       dict(self._votes),   # { color: True/False }
                "local_voted": self._local_voted,
                "local_color": self.local_color,
            },
        }

    def is_cleared(self) -> bool:
        """所有按鈕皆已觸發且全員存活時通關。"""
        return super().is_cleared()

    @property
    def is_voting(self) -> bool:
        """是否處於失敗投票階段（engine 用來決定是否把 Y/N 鍵轉為投票事件）。"""
        return self._voting

    def get_sync_data(self) -> dict:
        """
        打包本地玩家位置 + 能量封包，供主引擎定期廣播。
        Pac-Man 位置由授權客戶端單獨以 pacman_roster 廣播，不在此封包中。
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
        - player_pos：遠端玩家位置 + 能量同步
        - pacman_roster：所有 Pac-Man 位置同步（非授權客戶端接收）
        - gate_state：閘門狀態同步
        - player_caught / player_rescued：倒地/復活權威狀態
        - rescue_progress_start / rescue_progress_stop：救援進度條旗標
        - game_cleared：authority 宣告通關
        """
        dtype = data.get("type")

        if dtype == "player_pos":
            # 使用基類方法處理遠端玩家位置更新
            self.handle_remote_player_update(data)

        elif dtype == "pacman_roster" and not self.is_authority:
            # 由 authority 廣播所有 Pac-Man 的位置；觀眾端依 id 對齊清單（補新、刪舊）
            incoming = data.get("pacmen", [])
            by_id = {pm.id: pm for pm in self.pacmen}
            for entry in incoming:
                pid = entry.get("id")
                pm = by_id.get(pid)
                if pm is None:
                    # 觀眾端補位時，位置會立刻被接下來的 apply_server_update 覆蓋
                    pm = PacManState(pid, PACMAN_SPAWN_TILES[0])
                    self.pacmen.append(pm)
                    by_id[pid] = pm
                # Pac-Man 廣播的 dx/dy 已是單位向量，直接傳入做 Dead Reckoning
                apply_server_update(pm.sync,
                                    entry.get("x", pm.sync.target_x),
                                    entry.get("y", pm.sync.target_y),
                                    entry.get("dx", 0.0), entry.get("dy", 0.0))
                # 同步當前實際速度，確保 Dead Reckoning 預測位移精確
                pm.base_speed = entry.get("speed", pm.base_speed)
                # 根據移動方向向量更新視覺朝向
                pdx, pdy = entry.get("dx", 0.0), entry.get("dy", 0.0)
                if abs(pdx) > abs(pdy):
                    pm.direction = "right" if pdx > 0 else "left"
                elif abs(pdy) > 0:
                    pm.direction = "down" if pdy > 0 else "up"

            # 移除 authority 已不再廣播的（理論上只增不減，保險用）
            incoming_ids = {entry.get("id") for entry in incoming}
            self.pacmen = [pm for pm in self.pacmen if pm.id in incoming_ids]

        elif dtype == "gate_state":
            # 由 authority 廣播完整當前開啟集合：非 authority 直接套用，不自行判斷壓力板狀態。
            new_open = {tuple(g) for g in data.get("open_gates", [])}
            newly_closed = self.open_gates - new_open
            newly_open = new_open - self.open_gates

            for gr, gc in newly_open:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = E

            for gr, gc in newly_closed:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = G
                    self._push_players_off_gate(gr, gc)

            self.open_gates = new_open

        elif dtype == "button_activated":
            btn_color = data.get("color")
            for b in self.buttons:
                if b.assigned_color == btn_color:
                    b.is_triggered = True
                    self.sound_manager.play("charged")
                    b.activated_time = pygame.time.get_ticks()

        elif dtype == "player_caught":
            # 由 Pac-Man authority 廣播：標記玩家為倒地
            self.handle_player_caught_event(data)

        elif dtype == "player_rescued":
            # 由執行救援的 client 廣播：標記玩家復活
            color = data.get("color")
            p = self.players.get(color)
            if p and not p.is_alive:
                p.is_alive = True
                p.visual_key = f"{p.color_key}_{p.direction}"
                p.rescue_count = data.get("rescue_count", p.rescue_count + 1)
                self.on_player_rescued(p, None)

        elif dtype == "rescue_progress_start":
            self.handle_rescue_progress_start(data)

        elif dtype == "rescue_progress_stop":
            self.handle_rescue_progress_stop(data)

        elif dtype == "sfx_trigger":
            sfx = data.get("sfx")
            if sfx:
                self.sound_manager.play(sfx)

        elif dtype == "game_cleared":
            # authority 宣告四條全滿通關：所有 client 一起結束本局
            self.trigger_clear_sequence()

        elif dtype == "defeat_vote_start":
            # 由 authority 開啟失敗投票：非 authority 同步進入投票畫面。
            if not self._voting:
                self._start_defeat_vote()

        elif dtype == "vote_cast":
            # 某玩家投票：各端都記錄（authority 用來收齊判定；其他端用來顯示誰投了）。
            self._apply_vote(data.get("color"), data.get("value"))

        elif dtype == "vote_result":
            # authority 宣告投票結果：所有 client 一致套用。
            if data.get("value") == "continue":
                self.on_enter()  # 完全重置本局，重新開始
            else:
                # abort：結束本局；實際 game_over 由 server 廣播驅動 engine 結束迴圈。
                self._failed = True
                self._voting = False

    # ─────────────────────────────────────────────────────────────────────
    # 內部輔助方法
    # ─────────────────────────────────────────────────────────────────────

    def _escalate_pacmen(self):
        """
        Pac-Man 階段升級（僅 authority）：依進場後經過秒數
        1. 提升所有 Pac-Man 的基礎速度（封頂）。
        2. 從巢穴複製出新的 Pac-Man（上限 PACMAN_MAX_COUNT）。
        """
        # 加速：目前應到第幾階
        stage = int(self._elapsed / PACMAN_SPEED_STAGE_INTERVAL)
        new_base = min(PACMAN_SPEED_CAP, PACMAN_BASE_SPEED + stage * PACMAN_SPEED_STAGE_STEP)
        for pm in self.pacmen:
            pm.base_speed = new_base

        # 複製：目前應有幾隻
        # desired_count = min(PACMAN_MAX_COUNT, 1 + int(self._elapsed / PACMAN_DUPLICATE_INTERVAL))
        # while len(self.pacmen) < desired_count:
        #     new_id = len(self.pacmen)
        #     pm = PacManState(new_id)
        #     pm.base_speed = new_base  # 新生 Pac-Man 直接套用當前基礎速度
        #     self.pacmen.append(pm)
        #     print(f"[ReversePacman] Pac-Man duplicated -> count={len(self.pacmen)}")

    def _broadcast_pacman_roster(self):
        """廣播所有 Pac-Man 的位置 + 單位化速度向量（供觀眾端 Dead Reckoning）。"""
        roster = []
        for pm in self.pacmen:
            dx_raw = pm.next_tile_x - pm.x
            dy_raw = pm.next_tile_y - pm.y
            norm = math.hypot(dx_raw, dy_raw)
            if norm > 0:
                pm_dx, pm_dy = dx_raw / norm, dy_raw / norm
            else:
                pm_dx, pm_dy = 0.0, 0.0
            roster.append({
                "id": pm.id, "x": pm.x, "y": pm.y, 
                "dx": pm_dx, "dy": pm_dy, "speed": pm.speed
            })
        try:
            self.socket_client.send_game_event({"type": "pacman_roster", "pacmen": roster})
        except Exception as e:
            print(f"[ReversePacman] pacman_roster broadcast failed: {e}")

    def _check_win_and_fail(self):
        """authority 偵測通關（四條全滿且全員存活）與失敗（四人同時倒地），並廣播給全房。"""
        if self._failed or self._voting or self.clear_anim_stage != 0:
            return
        present = list(self.players.values())
        if not present:
            return

        # 通關：所有按鈕皆已觸發 且 所有玩家皆存活
        if all(b.is_triggered for b in self.buttons) and all(p.is_alive for p in present):
            self.trigger_clear_sequence()
            print("[ReversePacman] all charged and alive -> cleared!")
            try:
                self.socket_client.send_game_event({"type": "game_cleared"})
            except Exception as e:
                print(f"[ReversePacman] game_cleared broadcast failed: {e}")
            return

        # 失敗：所有在場玩家同時倒地 → 進入失敗投票階段（不再直接投降）。
        # 由 authority 開啟投票並廣播，讓全房同步進入投票畫面；
        # 只要有人投「繼續」就重玩本局，全員放棄/逾時才真正結束。
        if all(not p.is_alive for p in present):
            print("[ReversePacman] all players down -> defeat vote")
            self._start_defeat_vote()
            try:
                self.socket_client.send_game_event({"type": "defeat_vote_start"})
            except Exception as e:
                print(f"[ReversePacman] defeat_vote_start broadcast failed: {e}")

    def _start_defeat_vote(self):
        """進入失敗投票階段（authority 與非 authority 共用，確保各端狀態一致）。"""
        self._voting = True
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False

    def _update_defeat_vote(self, dt: float):
        """投票階段每幀邏輯：推進倒數；authority 負責收齊投票或逾時後結算並廣播。"""
        self._vote_timer += dt

        # 只有 authority 做判定與廣播，確保各 client 結果一致。
        if not self.is_authority:
            return

        present = list(self.players.values())
        all_voted = len(self._votes) >= len(present) and len(present) > 0
        timed_out = self._vote_timer >= DEFEAT_VOTE_TIME
        if not (all_voted or timed_out):
            return  # 尚未收齊也未逾時，繼續等

        # 結算：逾時 = 那些沒投的人視同投了 give up。
        # 因此只要有人投過「繼續」(True) 就重玩本局；否則（其餘全 give up，含逾時未投者）放棄。
        # 補的是 give up(False)，不影響 any() 只看有無 True，故無需真的補票即等價。
        if any(self._votes.values()):
            print("[ReversePacman] defeat vote -> CONTINUE (someone voted to continue)")
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "continue"})
            except Exception as e:
                print(f"[ReversePacman] vote_result(continue) broadcast failed: {e}")
            self.on_enter()  # 完全重置本局
        else:
            print("[ReversePacman] defeat vote -> ABORT (all gave up / timed out = give up)")
            self._failed = True
            self._voting = False
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "abort"})
                self.socket_client.send_surrender()
            except Exception as e:
                print(f"[ReversePacman] vote_result(abort)/surrender failed: {e}")

    def _apply_vote(self, color, value):
        """記錄某顏色玩家的投票（以 color 為鍵天然去重，重投以最後一次為準）。

        有人投「繼續」(value=True) 時，把投票剩餘時間壓到最多 5 秒：
        若投票當下剩餘 > 5 秒則縮成 5 秒，剩餘 <= 5 秒則維持不動（只縮不延）。
        作法是把 _vote_timer 往前推到「再過 5 秒就逾時」的位置，用 max 保證單調遞增、
        天然冪等（之後再有 continue 票也不會把倒數拉長）。各 client 都會經過 _apply_vote，
        故壓縮在四端同步發生，倒數顯示與最終結算（逾時走 any(votes)→continue）保持一致。"""
        if color in self.players:
            self._votes[color] = bool(value)
            if value:
                self._vote_timer = max(self._vote_timer, DEFEAT_VOTE_TIME - RESTART_DELAY)

    def _update_pacman_ai(self, pm: PacManState, dt: float):
        """
        授權客戶端執行的單隻 Pac-Man 格子對齊追蹤 AI（並偵測抓人）。

        移動策略：
        1. 每次鎖定「下一個目標格的中心點」並直線移動過去。
        2. 到達後 BFS 計算距最近存活玩家的下一步方向，鎖定新目標格。
        3. 沿格子走廊移動，不會卡牆角或抖動。
        """
        speed = pm.speed

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
                self._check_pacman_catches(pm)
                return  # 全員倒地，停止移動

            pm.current_target_id = best_color
            tr, tc = pixel_to_tile(self.players[best_color].x, self.players[best_color].y)

            # --- 方案三：虛擬障礙物排斥實作 ---
            # 1. 蒐集其他隊友目前佔據與即將前往的格子
            other_pm_tiles = set()
            for other in self.pacmen:
                if other.id != pm.id:
                    other_pm_tiles.add(pixel_to_tile(other.x, other.y))
                    other_pm_tiles.add(pixel_to_tile(other.next_tile_x, other.next_tile_y))

            # 2. 優先嘗試「避開隊友」的尋路
            dr, dc = bfs_next_step(self.tile_map, pm_row, pm_col, tr, tc, extra_walls=other_pm_tiles)

            # 3. 降級機制：如果避不開（dr, dc == 0），則改用原始尋路（排隊前進）
            if dr == 0 and dc == 0:
                dr, dc = bfs_next_step(self.tile_map, pm_row, pm_col, tr, tc)

            if dr == 0 and dc == 0:
                self._check_pacman_catches(pm)
                return
            
            # 根據 BFS 下一步方向更新視覺朝向
            if dr < 0: pm.direction = "up"
            elif dr > 0: pm.direction = "down"
            elif dc < 0: pm.direction = "left"
            elif dc > 0: pm.direction = "right"

            next_row = pm_row + dr
            next_col = pm_col + dc
            pm.next_tile_x, pm.next_tile_y = tile_center(next_row, next_col)

            # 用剩餘的 step 補移動（避免低速時明顯停頓）
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

        self._check_pacman_catches(pm)

    def _check_pacman_catches(self, pm: PacManState):
        """檢查單隻 Pac-Man 是否抓到任何存活玩家，抓到則該 Pac-Man 取得短暫加速。"""
        for color, p in self.players.items():
            if not p.is_alive:
                continue
            if math.hypot(pm.x - p.x, pm.y - p.y) < CATCH_RADIUS:
                self._catch_player(p)
                pm.speed_boost_timer = PACMAN_BOOST_DURATION

    def _evaluate_gates(self):
        """
        壓力板邏輯（僅 authority）：每幀檢查哪些 button 正被存活玩家踩著，
        進而決定哪些 gate 該開、哪些該關。狀態與上一幀有差異時更新並廣播。
        """
        any_pressed = False
        for p in self.players.values():
            if not p.is_alive:
                continue
            r, c = pixel_to_tile(p.x, p.y)
            if (r, c) in self.button_coords:
                any_pressed = True
                break

        # 偵測閘門按鈕踩下/放開的邊緣觸發
        if any_pressed != self._any_gate_pressed:
            self._any_gate_pressed = any_pressed
            sfx = "button_in" if any_pressed else "button_out"
            try:
                self.socket_client.send_game_event({"type": "sfx_trigger", "sfx": sfx})
            except: pass
            self.sound_manager.play(sfx) # 授權端也要播放本地音效

        # 只要有任何按鈕被踩下，就開啟地圖上所有的閘門
        should_open = set(self.gate_coords) if any_pressed else set()

        newly_open = should_open - self.open_gates
        newly_closed = self.open_gates - should_open

        if not newly_open and not newly_closed:
            return  # 無變化，省下廣播

        for gr, gc in newly_open:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = E
        for gr, gc in newly_closed:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = G
                self._push_players_off_gate(gr, gc)

        self.open_gates = set(should_open)

        try:
            self.socket_client.send_game_event({
                "type": "gate_state",
                "open_gates": [list(g) for g in self.open_gates],
            })
        except Exception as e:
            print(f"[ReversePacman] gate_state broadcast failed: {e}")

    def _push_players_off_gate(self, gr, gc):
        """閘門 (gr, gc) 剛關上，把站在這格上的玩家瞬移到相鄰空地，避免卡牆。"""
        gate_rect = pygame.Rect(gc * TILE_SIZE, gr * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        potential_neighbors = [(gr - 1, gc), (gr + 1, gc), (gr, gc - 1), (gr, gc + 1)]
        for p in self.players.values():
            if not p.is_alive:
                continue
            # 使用矩形碰撞偵測，只要身體任何部位重疊就觸發推擠
            if p.rect.colliderect(gate_rect):
                best_neighbor_tile = None
                min_distance_sq = float('inf')

                for nr, nc in potential_neighbors:
                    if 0 <= nr < ROWS and 0 <= nc < COLS and not is_wall(self.tile_map, nr, nc):
                        nx, ny = tile_center(nr, nc)
                        dist_sq = (p.x - nx)**2 + (p.y - ny)**2
                        if dist_sq < min_distance_sq:
                            min_distance_sq = dist_sq
                            best_neighbor_tile = (nr, nc)
                
                if best_neighbor_tile:
                    nx, ny = tile_center(*best_neighbor_tile)
                    p.x, p.y = float(nx), float(ny)
                    reset_sync_state(p.sync, p.x, p.y)
                else:
                    print(f"[ReversePacman] gate ({gr},{gc}) closed but no empty neighbor for {p.color_key}")

    def _catch_player(self, player: Ghost):
        """
        Pac-Man 抓到玩家的處理：將玩家標記為倒地並廣播 player_caught。
        （沒有永久死亡：倒地後永遠可被隊友救起。）
        """
        if not player.is_alive:
            return  # 已經倒地，不重複觸發

        player.is_alive = False
        player.visual_key = "dead"
        self.sound_manager.play("eat")
        player.rescue_progress = 0.0
        print(f"[ReversePacman] {player.color_key} caught! rescue_count={player.rescue_count}")

        try:
            self.socket_client.send_game_event({
                "type": "player_caught",
                "color": player.color_key,
            })
        except Exception as e:
            print(f"[ReversePacman] player_caught broadcast failed: {e}")

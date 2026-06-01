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

from games.base_game import BaseLogicInterface
from entities import Ghost, PLAYER_SPEED, ColorButton
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（已廢棄：地圖載入時一律轉成空地 E，保留常數僅為相容舊地圖）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）
F = 6   # Fog（迷霧陷阱，踩到後本地視野縮小數秒）

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

ROWS = len(_FALLBACK_MAP_LAYOUT)
COLS = len(_FALLBACK_MAP_LAYOUT[0])
TILE_SIZE = 60
AVATAR_SIZE = 24

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
RESCUE_RADIUS       = 70
RESCUE_HOLD_TIME    = 2.0
SPIKE_SLOW_DURATION = 3.0
PACMAN_BOOST_DURATION = 2.0 # 吃掉玩家後短暫加速秒數
PACMAN_AI_INTERVAL  = 0.05  # 提升廣播頻率至 20Hz 以對齊玩家同步

# 復活累積永久減速：每被救一次，移速永久降一階，趨近地板值（幾乎動不了但仍能爬）
REVIVE_SLOW_STEP    = 0.18  # 每次復活的減速階（移速 = base × (1 - count×step)）
REVIVE_SLOW_FLOOR   = 0.12  # 減速地板（最低保留 12% 移速）

# 蓄能機制數值
BUTTON_HOLD_TIME    = 5   # 照搬 dodge_knives：蓄滿需要的秒數

# 迷霧陷阱數值
FOG_DURATION        = 2.5   # 致盲持續秒數
FOG_VISION_RADIUS   = 50    # 致盲期間玩家周圍清晰圓的半徑（像素）

# Pac-Man 階段升級排程（取代倒數計時的壓力來源；僅 authority 依此排程）
PACMAN_SPEED_STAGE_INTERVAL = 1  # 每幾秒提升一階基礎速度
PACMAN_SPEED_STAGE_STEP     = 1  # 每階增加的速度
PACMAN_SPEED_CAP            = 250   # 基礎速度上限
PACMAN_DUPLICATE_INTERVAL   = 5000  # 每幾秒複製出一隻新 Pac-Man
PACMAN_MAX_COUNT            = 4     # Pac-Man 數量上限

# 失敗投票機制：四人同時倒地後，進入投票決定是否重玩本局
DEFEAT_VOTE_TIME    = 30.0  # 投票倒數秒數（逾時未投視為放棄）


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


def nearest_empty_tile(tile_map, row, col):
    """
    以 BFS 從 (row, col) 往外找最近的「空地(E)」格座標。
    用於把理想蓄能點吸附到可站立的格子，避免手填座標落在牆裡。
    找不到任何空地時回傳原座標（理論上不會發生）。
    """
    queue = deque([(row, col)])
    visited = {(row, col)}
    while queue:
        r, c = queue.popleft()
        if 0 <= r < ROWS and 0 <= c < COLS and tile_map[r][c] == E:
            return (r, c)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (nr, nc) not in visited and 0 <= nr < ROWS and 0 <= nc < COLS:
                visited.add((nr, nc))
                queue.append((nr, nc))
    return (row, col)


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
            if is_wall(tile_map, nr, nc) or (extra_walls and (nr, nc) in extra_walls):
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


class PlayerState(Ghost):
    """單一玩家在小遊戲中的所有狀態資料。"""

    def __init__(self, color, spawn_row, spawn_col):
        self.rescue_count = 0       # 已被救援次數（累積永久減速的依據）
        self.spike_timer = 0.0      # 踩到釘板後的緩速倒數
        self.fog_timer = 0.0        # 踩到迷霧後的致盲倒數（純本地視覺）
        self.rescue_progress = 0.0  # 隊友救援進度
        self.charge = 0.0           # 自己的蓄能進度（0~1），滿 1 表示這條完成
        # 是否正在被某人救援；所有 client 收到 rescue_progress_start 後設為 True，
        # 進入 update 後本地以 dt 累加 rescue_progress，讓畫面上的進度弧線在每台都會動。
        self.being_rescued = False

        super().__init__(color_key=color, avatar_size=AVATAR_SIZE)
        self.speed = PLAYER_SPEED  # 設定小遊戲專用的基礎速度（透過 setter 寫入 _base_speed）
        cx, cy = tile_center(spawn_row, spawn_col)
        self.x, self.y = float(cx), float(cy)
        # 遠端同步狀態（target + Dead Reckoning），本地玩家不使用
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    @property
    def speed(self):
        """根據當前狀態決定移動速度（復活累積減速 + 釘板額外減速 + 迷霧減速）。"""
        if not self.is_alive:
            return 0.0
        base = getattr(self, '_base_speed', PLAYER_SPEED)
        # 復活累積永久減速：每救一次更慢，趨近地板值
        revive_factor = max(REVIVE_SLOW_FLOOR, 1.0 - self.rescue_count * REVIVE_SLOW_STEP)
        base *= revive_factor
        # 踩到釘板時再額外砍半
        if self.spike_timer > 0:
            base *= 0.5
        # 迷霧期間移動速度 * 0.5
        if self.fog_timer > 0:
            base *= 0.5
        return base

    @speed.setter
    def speed(self, value):
        self._base_speed = value


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


class ReversePacman(BaseLogicInterface):
    """
    Reverse Pac-Man（蓄能版）小遊戲的完整邏輯實作。

    授權分配：
    - 顏色為 "blue" 的玩家所在客戶端負責執行 Pac-Man AI、升級排程、通關/失敗判定並廣播。
    - 其他客戶端接收廣播，只更新本地的渲染座標與自己的能量條。
    """

    def __init__(self, socket_client, player_id_list, sound_manager):
        super().__init__(socket_client, player_id_list, sound_manager)

        # 取得本地玩家資訊
        self.local_color = socket_client.player_color       # 本機玩家顏色
        self.local_pid = socket_client.player_id            # 本機玩家 Socket ID

        # 是否為 Pac-Man AI 授權客戶端：直接採用 network 的單一真值源（由 server 在
        # start_minigame roster 指定；DEBUG_MINIGAME 等無名單路徑由 engine 以顏色 fallback
        # 預先設好）。小遊戲不再自行用顏色硬猜，避免重連/缺色時授權錯配。
        self.is_authority = bool(getattr(socket_client, "is_authority", self.local_color == "blue"))

        # 地圖狀態：使用可修改的二維陣列（pellet 轉空地 + 灑上迷霧）
        self.tile_map = build_tile_map()
        
        self.gate_coords = list(GATE_COORDS)
        self.button_coords = list(BUTTON_COORDS)
        # 哪些閘門目前是開著的（格座標 set）
        self.open_gates = set()
        self._any_gate_pressed = False      # 記錄上一幀是否有閘門按鈕被踩著
        self.buttons = []

        # 所有玩家狀態字典 { color: PlayerState }，依 player_id_list 的順序對應顏色
        # 所有玩家狀態字典 { color: PlayerState }
        # 無論當前連線人數，預先建立所有顏色的實體，確保同步與渲染不中斷
        colors = ["blue", "green", "pink", "red"]
        self.players: dict[str, PlayerState] = {}
        for color in colors:
            sr, sc = SPAWN_TILES.get(color, (10, 1))
            self.players[color] = PlayerState(color, sr, sc)

        # 每位玩家的專屬蓄能點（由內建關卡的理想格 BFS 吸附而來）
        self.charge_stations = dict(_LEVEL["charge_stations"])

        # Pac-Man 清單（所有客戶端都持有；authority 計算，其餘接收）。起始一隻。
        self.pacmen: list[PacManState] = [
            PacManState(0, PACMAN_SPAWN_TILES[0]), 
            PacManState(1, PACMAN_SPAWN_TILES[1])
        ]

        # 計時器
        self._pacman_broadcast_timer = 0.0  # Pac-Man roster 廣播計時
        self._elapsed = 0.0                 # 進場後累積秒數（authority 用於升級排程）

        # 遊戲失敗旗標
        self._failed = False    # 已確定放棄（投票結果為 abort 後設下，避免重複送 surrender）

        # 失敗投票階段狀態（四人倒地後進入；只要有人投繼續就重玩本局）
        self._voting = False        # 是否處於失敗投票階段
        self._vote_timer = 0.0      # 投票倒數累加（達 DEFEAT_VOTE_TIME 即結算）
        self._votes = {}            # { color: True(繼續) / False(放棄) }，以 color 為鍵天然去重
        self._local_voted = False   # 本機是否已投票，避免重複廣播

        # 本地玩家輸入向量（由 handle_event 設定）
        self._input_dx = 0
        self._input_dy = 0
        
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0

    # ─────────────────────────────────────────────────────────────────────
    # BaseLogicInterface 生命週期方法
    # ─────────────────────────────────────────────────────────────────────

    def on_enter(self, params: dict = None):
        """重置所有遊戲狀態，準備開始（確保同一實例可重玩）。"""
        super().on_enter(params)
        # 重置地圖（恢復閘門、重新灑迷霧、pellet 已轉空地）
        self.tile_map = build_tile_map()
        self.open_gates.clear()
        self.charge_stations = dict(_LEVEL["charge_stations"])

        self.buttons.clear()
        for color, pos in self.charge_stations.items():
            rx, ry = tile_center(*pos)
            self.buttons.append(ColorButton(rx, ry, color))

        # 將所有顏色玩家重置至各自的出生點
        for color, p in self.players.items():
                sr, sc = SPAWN_TILES.get(color, (10, 1))
                cx, cy = tile_center(sr, sc)
                p.x, p.y = float(cx), float(cy)
                reset_sync_state(p.sync, float(cx), float(cy))
                p.is_alive = True
                p.visual_key = f"{color}_{p.direction}"
                p.rescue_count = 0
                p.spike_timer = 0.0
                p.fog_timer = 0.0
                p.rescue_progress = 0.0
                p.being_rescued = False
                p.charge = 0.0

        # 重置 Pac-Man 清單回單隻
        self.pacmen = [
            PacManState(0, PACMAN_SPAWN_TILES[0]), 
            PacManState(1, PACMAN_SPAWN_TILES[1])
        ]

        # 重置計時與旗標
        self._pacman_broadcast_timer = 0.0
        self._elapsed = 0.0
        self._failed = False
        # 重置失敗投票狀態（「繼續」會呼叫 on_enter，必須清乾淨以便下次失敗能重新投票）
        self._voting = False
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False
        self._input_dx = 0
        self._input_dy = 0
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0
        self.is_input_locked = True
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
            
            # 開場期間仍需更新動畫影格（讓角色不會卡在呆板的姿勢）
            for p in self.players.values():
                p.update(dt)
            return

        # 推進通關動畫狀態機
        self._update_clear_animation(dt)
        if super().is_cleared():
            return

        # 失敗投票階段：凍結遊戲邏輯（玩家/Pac-Man 不動），只推進投票倒數與判定。
        if self._voting:
            self._update_defeat_vote(dt)
            return

        self._elapsed += dt
        local = self.players.get(self.local_color)

        # 1. 更新本地玩家移動
        if local and local.is_alive and not self.is_input_locked:
            # 收集其他玩家的碰撞矩形（包含倒地者）
            other_rects = [p.rect for c, p in self.players.items() if c != self.local_color]
            local.move(
                self._input_dx, self._input_dy, dt,
                TILE_SIZE,
                lambda px, py: is_wall(self.tile_map, *pixel_to_tile(px, py)),
                others=other_rects,
            )
            # 移動後處理地圖互動（釘板、迷霧）
            self._handle_tile_interaction(local)

        # 2. 更新所有玩家的計時器（spike、fog）與動畫
        for p in self.players.values():
            p.update(dt)  # 驅動動畫影格
            if p.spike_timer > 0:
                p.spike_timer = max(0.0, p.spike_timer - dt)
            if p.fog_timer > 0:
                p.fog_timer = max(0.0, p.fog_timer - dt)

        # 2.5. 遠端實體位置同步：交由 sync_helpers 統一處理 Dead Reckoning + LERP
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE,
                      COLS * TILE_SIZE - AVATAR_SIZE,
                      ROWS * TILE_SIZE - AVATAR_SIZE)
        for color, p in self.players.items():
            if color == self.local_color:
                continue
            if not self.is_input_locked:
                tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

        # 非授權端的所有 Pac-Man：以同套 Dead Reckoning + LERP 更新（授權端用 AI 直接算）
        if not self.is_authority and self.clear_anim_stage == 0:
            for pm in self.pacmen:
                tick_remote_sync(pm, pm.sync, dt, pm.speed, bounds=map_bounds)

        # 3. 處理救援進度 (改為自動觸發)
        if not self.is_input_locked:
            self._update_rescue(dt, local)

        # 4. 蓄能邏輯 (完全照搬 dodge_knives)
        if self.clear_anim_stage == 0:
            for btn in self.buttons:
                if btn.is_triggered:
                    continue
                owner = self.players.get(btn.assigned_color)
                # 自動判斷：只要玩家活著且踩在按鈕上
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
                    btn.charge_timer = max(0.0, btn.charge_timer - dt * 0.25)

        # 3.5. 壓力板閘門：authority 每幀重新評估，狀態變化才廣播（放在 AI 前，確保用最新牆況）
        if self.is_authority:
            self._evaluate_gates()

        # 4. Pac-Man：authority 跑升級排程 + AI + 廣播；觀眾端不參與
        if self.is_authority and self.clear_anim_stage == 0:
            self._escalate_pacmen()
            for pm in self.pacmen:
                pm.update(dt)  # 授權端也要更新動畫計時
                self._update_pacman_ai(pm, dt)
            self._pacman_broadcast_timer += dt
            if self._pacman_broadcast_timer >= PACMAN_AI_INTERVAL:
                self._pacman_broadcast_timer = 0.0
                self._broadcast_pacman_roster()

        # 5. 更新所有 Pac-Man 的動畫計時與加速計時器（非授權端在此更新動畫）
        for pm in self.pacmen:
            if not self.is_authority:
                pm.update(dt)
            if pm.speed_boost_timer > 0:
                pm.speed_boost_timer = max(0.0, pm.speed_boost_timer - dt)

        # 6. 通關與失敗判定（皆由 authority 偵測並廣播，確保各 client 一致）
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
                if raw_dx > 0:
                    p.direction = "right"
                elif raw_dx < 0:
                    p.direction = "left"
                elif raw_dy != 0:
                    p.direction = "frontback"
                else:
                    p.direction = "idle"
                p.visual_key = f"{p.color_key}_{p.direction}"

                apply_server_update(p.sync,
                                    data.get("x", p.sync.target_x),
                                    data.get("y", p.sync.target_y),
                                    raw_dx, raw_dy)
                p.current_dx = data.get("dx", p.current_dx)
                p.current_dy = data.get("dy", p.current_dy)
                # 不直接覆寫 alive：alive 的權威來源是 player_caught / player_rescued 兩個事件。

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
            color = data.get("color")
            p = self.players.get(color)
            if p and p.is_alive:
                p.is_alive = False
                self.sound_manager.play("eat")
                p.rescue_progress = 0.0
                p.being_rescued = False
                # 倒地後能量會開始緩降，但那由該玩家本人的 update 計算後廣播，這裡不需動 charge。

        elif dtype == "player_rescued":
            # 由執行救援的 client 廣播：標記玩家復活，套用救援次數（→ 永久減速）
            color = data.get("color")
            p = self.players.get(color)
            if p and not p.is_alive:
                p.is_alive = True
                p.visual_key = f"{p.color_key}_{p.direction}"
                p.rescue_count = data.get("rescue_count", p.rescue_count + 1)
                p.rescue_progress = 0.0
                p.being_rescued = False

        elif dtype == "sfx_trigger":
            sfx = data.get("sfx")
            if sfx:
                self.sound_manager.play(sfx)

        elif dtype == "rescue_progress_start":
            color = data.get("color")
            p = self.players.get(color)
            if p:
                if not p.is_alive:
                    p.being_rescued = True
                p.rescue_progress = 0.0

        elif dtype == "rescue_progress_stop":
            color = data.get("color")
            p = self.players.get(color)
            if p:
                p.being_rescued = False
                p.rescue_progress = 0.0

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

    def _update_rescue(self, dt: float, local: PlayerState):
        """處理救援進度的累加、完成、中斷與旁觀端進度條動畫。"""
        if not local or not local.is_alive:
            return

        for color, target in self.players.items():
            if color == self.local_color or target.is_alive:
                continue
            
            # 自動偵測鄰近倒地隊友
            in_range = math.hypot(local.x - target.x, local.y - target.y) <= RESCUE_RADIUS
            if in_range:
                if not target.being_rescued:
                    target.being_rescued = True
                    self.socket_client.send_game_event({"type": "rescue_progress_start", "color": color})
                
                target.rescue_progress += dt
                if target.rescue_progress >= RESCUE_HOLD_TIME:
                    # 救援完成：復活目標玩家（rescue_count +1 → 永久減速更深）
                    target.is_alive = True
                    target.visual_key = f"{target.color_key}_{target.direction}"
                    target.rescue_count += 1
                    target.rescue_progress = 0.0
                    target.being_rescued = False
                    self.socket_client.send_game_event({
                        "type": "player_rescued", "color": color, "rescue_count": target.rescue_count
                    })
            # 關鍵修正：只有當本地確實在進行救援（進度 > 0）時，才在離開範圍後發送停止事件。
            # 這能防止遠端隊友因「距離目標太遠」而誤發停止封包，干擾真正的救援者。
            elif target.being_rescued and target.rescue_progress > 0:
                target.being_rescued = False
                target.rescue_progress = 0.0
                self.socket_client.send_game_event({"type": "rescue_progress_stop", "color": color})

    def _handle_tile_interaction(self, player: PlayerState):
        """
        玩家中心格發生的互動：
        - S (spike) → 觸發緩速
        - F (fog)   → 觸發本地致盲（純本地視覺，不需廣播）
        按鈕 (B) 是壓力板，由 authority 在 _evaluate_gates 每幀處理。
        （pellet 已移除，這裡不再處理 P。）
        """
        row, col = pixel_to_tile(player.x, player.y)
        if row < 0 or row >= ROWS or col < 0 or col >= COLS:
            return

        tile = self.tile_map[row][col]
        if tile == S:
            if player.spike_timer <= 0:
                player.spike_timer = SPIKE_SLOW_DURATION
        elif tile == F:
            # 踩在迷霧上：持續把致盲倒數刷新到滿，離開後才開始倒數
            if player.fog_timer <= 0:
                self.sound_manager.play("blind")
            player.fog_timer = FOG_DURATION

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

        # 結算：只要有人投「繼續」(True) 就重玩本局；否則（全放棄或逾時無人投）放棄。
        if any(self._votes.values()):
            print("[ReversePacman] defeat vote -> CONTINUE (someone voted to continue)")
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "continue"})
            except Exception as e:
                print(f"[ReversePacman] vote_result(continue) broadcast failed: {e}")
            self.on_enter()  # 完全重置本局
        else:
            print("[ReversePacman] defeat vote -> ABORT (all gave up / timed out)")
            self._failed = True
            self._voting = False
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "abort"})
                self.socket_client.send_surrender()
            except Exception as e:
                print(f"[ReversePacman] vote_result(abort)/surrender failed: {e}")

    def _apply_vote(self, color, value):
        """記錄某顏色玩家的投票（以 color 為鍵天然去重，重投以最後一次為準）。"""
        if color in self.players:
            self._votes[color] = bool(value)

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
        neighbors = [(gr - 1, gc), (gr + 1, gc), (gr, gc - 1), (gr, gc + 1)]
        for p in self.players.values():
            if not p.is_alive:
                continue
            pr, pc = pixel_to_tile(p.x, p.y)
            if (pr, pc) != (gr, gc):
                continue
            for nr, nc in neighbors:
                if 0 <= nr < ROWS and 0 <= nc < COLS and not is_wall(self.tile_map, nr, nc):
                    nx = nc * TILE_SIZE + TILE_SIZE // 2
                    ny = nr * TILE_SIZE + TILE_SIZE // 2
                    p.x, p.y = float(nx), float(ny)
                    break
            else:
                print(f"[ReversePacman] gate ({gr},{gc}) closed but no empty neighbor for {p.color_key}")
            reset_sync_state(p.sync, p.x, p.y)

    def _catch_player(self, player: PlayerState):
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

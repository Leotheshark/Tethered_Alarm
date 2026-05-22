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

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（飼料）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）

# ─── 地圖定義（21 行 × 33 列，TILE_SIZE=40px）────────────────────────────────
# 每格 40×40px，地圖左上角偏移 MAP_OFFSET_X=20, MAP_OFFSET_Y=60
# 按鈕與閘門的交叉配對設計：
#   Button A (row=3,col=5)  ↔ Gate A (row=3,col=25)  — 藍綠側踩 → 紅粉側閘門開
#   Button B (row=17,col=5) ↔ Gate B (row=17,col=25) — 紅粉側踩 → 藍綠側閘門開
#   Button C (row=3,col=27) ↔ Gate C (row=3,col=7)   — 紅粉側踩 → 藍綠側閘門開
#   Button D (row=17,col=27)↔ Gate D (row=17,col=7)  — 藍綠側踩 → 紅粉側閘門開
MAP_LAYOUT = [
    # 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 0
    [W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 1
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, P, W],  # 2
    [W, P, W, W, B, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, G, B, W, W, W, W, P, W],  # 3
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, P, W],  # 4
    [W, P, P, P, P, P, P, G, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 5
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, P, W],  # 6
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, P, W],  # 7
    [W, P, P, P, P, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W, P, P, P, P, W],  # 8
    [W, W, W, W, P, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, P, W, W, W, W, W, W],  # 9
    [W, P, P, P, P, P, P, P, P, P, P, P, P, W, W, W, W, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 10
    [W, W, W, W, P, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, W, W, W, W, P, W, P, W, W, W, W, W, W],  # 11
    [W, P, P, P, P, W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W, P, P, P, P, W],  # 12
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, P, W],  # 13
    [W, P, W, W, P, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, P, W, W, W, P, P, W],  # 14
    [W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 15
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, P, W],  # 16
    [W, P, W, W, B, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, G, B, W, W, W, W, P, W],  # 17
    [W, P, W, W, P, W, W, W, P, W, W, W, W, W, W, W, W, W, W, W, W, W, P, W, W, W, P, W, W, W, W, P, W],  # 18
    [W, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, W],  # 19
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 20
]

ROWS = len(MAP_LAYOUT)      # 21
COLS = len(MAP_LAYOUT[0])   # 33
TILE_SIZE = 40
MAP_OFFSET_X = 20
MAP_OFFSET_Y = 60

# ─── 玩家初始出生位置（格座標，依顏色）──────────────────────────────────────
SPAWN_TILES = {
    "blue":  (1, 1),    # 左上
    "green": (19, 31),  # 右下
    "pink":  (1, 31),   # 右上
    "red":   (19, 1),   # 左下
}

# Pac-Man 初始出生格
PACMAN_SPAWN_TILE = (10, 16)  # 地圖正中央

# ─── 遊戲數值常數 ─────────────────────────────────────────────────────────────
PLAYER_SPEED        = 120   # 像素 / 秒
PACMAN_BASE_SPEED   = 110   # 正常速度
PACMAN_FAST_SPEED   = 165   # 被獵食後暫時加速（1.5 倍）
CATCH_RADIUS        = 18    # 捕捉碰撞半徑（像素）
MAX_RESCUES         = 2     # 每位玩家被救援的上限次數
RESCUE_RADIUS       = 50    # 救援互動的有效距離（像素）
RESCUE_HOLD_TIME    = 2.0   # 按住 E 多少秒才完成救援
DEBUFF_DURATION     = 15.0  # 被抓後移速減半持續秒數
SPIKE_SLOW_DURATION = 3.0   # 釘板緩速持續秒數
PACMAN_BOOST_DURATION = 5.0 # 吃掉 pellet 後短暫加速秒數
PACMAN_AI_INTERVAL  = 0.10  # 授權客戶端廣播 Pac-Man 位置的時間間隔（秒）

# 按鈕 → 閘門 的映射（格座標對）
# 鍵：button (row, col)，值：gate (row, col)
BUTTON_GATE_MAP = {
    (3,  4):  (3,  25),   # Button A 開 Gate A
    (17, 4):  (17, 25),   # Button B 開 Gate B
    (3,  26): (3,  7),    # Button C 開 Gate C（右→左，交叉）
    (17, 26): (17, 7),    # Button D 開 Gate D（右→左，交叉）
}


def tile_center(row, col):
    """回傳指定格子中心點的像素座標 (x, y)。"""
    x = MAP_OFFSET_X + col * TILE_SIZE + TILE_SIZE // 2
    y = MAP_OFFSET_Y + row * TILE_SIZE + TILE_SIZE // 2
    return x, y


def pixel_to_tile(px, py):
    """將像素座標轉換為格座標 (row, col)，用於碰撞查詢。"""
    col = int((px - MAP_OFFSET_X) / TILE_SIZE)
    row = int((py - MAP_OFFSET_Y) / TILE_SIZE)
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


class PlayerState:
    """單一玩家在小遊戲中的所有狀態資料。"""

    def __init__(self, color, spawn_row, spawn_col):
        cx, cy = tile_center(spawn_row, spawn_col)
        self.color = color
        self.x = float(cx)          # 像素座標（浮點數，用於精確移動）
        self.y = float(cy)
        self.alive = True           # True = 正常行動，False = 被抓住等待救援
        self.rescue_count = 0       # 已被救援次數，達到 MAX_RESCUES 後永久無法動作
        self.debuff_timer = 0.0     # 被救援後的速度減半倒數計時
        self.spike_timer = 0.0      # 踩到釘板後的緩速倒數計時
        self.rescue_progress = 0.0  # 隊友按 E 救援的進度（秒），達到 RESCUE_HOLD_TIME 完成
        self.dx = 0.0               # 上一幀的移動方向，供渲染器判斷角色朝向
        self.dy = 0.0

    @property
    def speed(self):
        """根據當前狀態決定移動速度（釘板或被救後減半）。"""
        if not self.alive:
            return 0.0
        base = PLAYER_SPEED
        if self.debuff_timer > 0 or self.spike_timer > 0:
            base *= 0.5
        return base

    @property
    def permanently_down(self):
        """已達最大救援次數且再次倒下，無法再被救援。"""
        return not self.alive and self.rescue_count >= MAX_RESCUES


class PacManState:
    """Pac-Man 的位置、速度、目標玩家等狀態。"""

    def __init__(self):
        sr, sc = PACMAN_SPAWN_TILE
        cx, cy = tile_center(sr, sc)
        self.x = float(cx)
        self.y = float(cy)
        self.speed_boost_timer = 0.0    # 吃到 pellet 後短暫加速的倒數計時
        self.current_target_id = None   # 目前追蹤的玩家 ID（字串）

        # 格子對齊移動：鎖定下一個目標格的中心點，到達後再重新 BFS
        self.next_tile_x = float(cx)    # 目前正在朝向的格中心 X
        self.next_tile_y = float(cy)    # 目前正在朝向的格中心 Y

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

        # 判斷本機是否為 Pac-Man AI 授權客戶端
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
                p.alive = True
                p.rescue_count = 0
                p.debuff_timer = 0.0
                p.spike_timer = 0.0
                p.rescue_progress = 0.0

        # 重置 Pac-Man
        sr, sc = PACMAN_SPAWN_TILE
        cx, cy = tile_center(sr, sc)
        self.pacman.x, self.pacman.y = float(cx), float(cy)
        self.pacman.next_tile_x, self.pacman.next_tile_y = float(cx), float(cy)
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
        elif etype == "rescue_stop":
            # 玩家放開 E：取消救援進度
            if self._rescuing_target:
                target = self.players.get(self._rescuing_target)
                if target:
                    target.rescue_progress = 0.0
            self._rescuing_target = None

    def update(self, dt: float):
        """每幀更新所有玩家移動、Pac-Man AI、碰撞偵測、救援計時。"""
        if not self.is_active or self._cleared:
            return

        local = self.players.get(self.local_color)

        # 1. 更新本地玩家移動
        if local and local.alive and not local.permanently_down:
            self._move_player(local, self._input_dx, self._input_dy, dt)

        # 2. 更新所有玩家的計時器（debuff、spike）
        for p in self.players.values():
            if p.debuff_timer > 0:
                p.debuff_timer = max(0.0, p.debuff_timer - dt)
            if p.spike_timer > 0:
                p.spike_timer = max(0.0, p.spike_timer - dt)

        # 3. 處理救援進度
        if self._rescuing_target:
            target = self.players.get(self._rescuing_target)
            if target and not target.alive and not target.permanently_down:
                target.rescue_progress += dt
                if target.rescue_progress >= RESCUE_HOLD_TIME:
                    # 救援完成：復活目標玩家
                    target.alive = True
                    target.rescue_count += 1
                    target.debuff_timer = DEBUFF_DURATION  # 被救後速度減半
                    target.rescue_progress = 0.0
                    self._rescuing_target = None
                    print(f"[ReversePacman] {target.color} rescued (count={target.rescue_count})")
            else:
                # 目標已復活或消失，停止救援
                self._rescuing_target = None

        # 4. Pac-Man AI（僅授權客戶端執行）
        if self.is_pacman_authority:
            self._update_pacman_ai(dt)
            self._pacman_broadcast_timer += dt
            if self._pacman_broadcast_timer >= PACMAN_AI_INTERVAL:
                self._pacman_broadcast_timer = 0.0
                # 廣播 Pac-Man 最新位置給其他客戶端
                try:
                    self.socket_client.send_game_event({
                        "type": "pacman_pos",
                        "x": self.pacman.x,
                        "y": self.pacman.y,
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
            "open_gates":  list(self.open_gates),      # [(row, col), ...]
            "pellets_left": self.pellets_remaining,
            "pacman": {
                "x": self.pacman.x,
                "y": self.pacman.y,
            },
            "players": {
                color: {
                    "x":              p.x,
                    "y":              p.y,
                    "alive":          p.alive,
                    "permanently_down": p.permanently_down,
                    "rescue_progress": p.rescue_progress,
                    "rescue_count":   p.rescue_count,
                    "debuff":         p.debuff_timer > 0,
                    "spike":          p.spike_timer > 0,
                    "dx":             p.dx,
                    "dy":             p.dy,
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
            "dx":    local.dx,
            "dy":    local.dy,
            "alive": local.alive,
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
                p.x = data.get("x", p.x)
                p.y = data.get("y", p.y)
                p.dx = data.get("dx", p.dx)
                p.dy = data.get("dy", p.dy)
                p.alive = data.get("alive", p.alive)

        elif dtype == "pacman_pos" and not self.is_pacman_authority:
            # 非授權客戶端直接套用廣播位置（無需 LERP，由授權端保證平滑）
            self.pacman.x = data.get("x", self.pacman.x)
            self.pacman.y = data.get("y", self.pacman.y)

        elif dtype == "gate_open":
            rc = data.get("gate")  # [row, col]
            if rc:
                self.open_gates.add(tuple(rc))
                gr, gc = rc
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = E  # 閘門開啟後視為空地

        elif dtype == "pellet_eaten":
            rc = data.get("tile")  # [row, col]
            if rc:
                pr, pc = rc
                if 0 <= pr < ROWS and 0 <= pc < COLS:
                    if self.tile_map[pr][pc] == P:
                        self.tile_map[pr][pc] = E
                        self.pellets_remaining -= 1

    # ─────────────────────────────────────────────────────────────────────
    # 內部輔助方法
    # ─────────────────────────────────────────────────────────────────────

    def _move_player(self, player: PlayerState, dx: int, dy: int, dt: float):
        """
        像素精確移動 + 走廊吸附（corridor snapping）。

        走廊吸附：當玩家沿某軸移動時，若垂直軸偏離格子中心線不超過 SNAP_THRESHOLD，
        則自動將垂直軸吸回中心線。這讓玩家能順暢轉入走廊，不會卡在牆角。

        斜向輸入被拆成「優先水平」或「優先垂直」兩個分量分別試移，
        確保在 T 字路口等複雜地形下仍能正確滑行。
        """
        # 移動半徑：比格子小一點，讓角色能通過走廊
        PLAYER_RADIUS = TILE_SIZE // 2 - 6
        # 吸附容差：偏離中心線在此範圍內才自動對齊
        SNAP_THRESHOLD = TILE_SIZE * 0.35

        if dx == 0 and dy == 0:
            player.dx = 0.0
            player.dy = 0.0
            return

        move = player.speed * dt

        # 走廊吸附：沿 X 軸移動時，把 Y 吸回格子中心線（反之亦然）
        row, col = pixel_to_tile(player.x, player.y)
        center_x, center_y = tile_center(row, col)

        if dx != 0 and dy == 0:
            # 純水平移動：若 Y 偏離中心線不多則吸回
            offset_y = center_y - player.y
            if abs(offset_y) <= SNAP_THRESHOLD:
                snap_step = min(abs(offset_y), move * 0.8)
                player.y += math.copysign(snap_step, offset_y)

        elif dy != 0 and dx == 0:
            # 純垂直移動：若 X 偏離中心線不多則吸回
            offset_x = center_x - player.x
            if abs(offset_x) <= SNAP_THRESHOLD:
                snap_step = min(abs(offset_x), move * 0.8)
                player.x += math.copysign(snap_step, offset_x)

        # 嘗試 X 軸移動
        if dx != 0:
            new_x = player.x + math.copysign(move, dx)
            if not self._collides(new_x, player.y, PLAYER_RADIUS):
                player.x = new_x

        # 嘗試 Y 軸移動
        if dy != 0:
            new_y = player.y + math.copysign(move, dy)
            if not self._collides(player.x, new_y, PLAYER_RADIUS):
                player.y = new_y

        player.dx = float(dx)
        player.dy = float(dy)

        # 觸發互動邏輯
        self._handle_tile_interaction(player)

    def _collides(self, px: float, py: float, radius: int = None) -> bool:
        """
        以玩家中心點為基準，用四個邊緣點檢查是否碰牆。
        radius 預設為 TILE_SIZE // 2 - 6，比格子小讓走廊可以通行。
        """
        if radius is None:
            radius = TILE_SIZE // 2 - 6
        corners = [
            (px - radius, py - radius), (px + radius, py - radius),
            (px - radius, py + radius), (px + radius, py + radius),
        ]
        for cx, cy in corners:
            row, col = pixel_to_tile(cx, cy)
            if is_wall(self.tile_map, row, col):
                return True
        return False

    def _handle_tile_interaction(self, player: PlayerState):
        """
        玩家中心格發生的互動：
        - P (pellet)  → 吃掉，廣播 pellet_eaten
        - B (button)  → 開啟對應閘門，廣播 gate_open
        - S (spike)   → 觸發緩速
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

        elif tile == B:
            # 踩到按鈕：查表找對應閘門並開啟
            gate_rc = BUTTON_GATE_MAP.get((row, col))
            if gate_rc and gate_rc not in self.open_gates:
                gr, gc = gate_rc
                self.open_gates.add(gate_rc)
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = E  # 本地地圖開閘
                try:
                    self.socket_client.send_game_event({
                        "type": "gate_open",
                        "gate": list(gate_rc),
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
                if not p.alive:
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
            if not p.alive:
                continue
            if math.hypot(pm.x - p.x, pm.y - p.y) < CATCH_RADIUS:
                self._catch_player(p)

    def _catch_player(self, player: PlayerState):
        """
        Pac-Man 抓到玩家的處理邏輯：
        - 若未達最大救援次數：將玩家標記為倒地。
        - 若已達最大次數：玩家永久無法動作（不再計入存活）。
        - Pac-Man 獲得短暫加速。
        """
        if not player.alive:
            return  # 已經倒地，不重複觸發

        player.alive = False
        player.rescue_progress = 0.0
        self.pacman.speed_boost_timer = PACMAN_BOOST_DURATION
        print(f"[ReversePacman] {player.color} caught! rescue_count={player.rescue_count}")

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
            if p.alive or p.permanently_down:
                continue
            dist = math.hypot(local.x - p.x, local.y - p.y)
            if dist <= RESCUE_RADIUS:
                return color
        return None

"""
PlayerGameLogicInterface：所有支持多玩家互动的小遊戲的抽象基底類別。
提取通用的玩家-玩家、玩家-地圖互動邏輯，供各小遊戲類繼承使用。

包含的通用機制：
1. 玩家移動與碰撞（牆壁、地板陷阱、其他玩家）
2. 玩家救援邏輯（倒地、救起、復活懲罰）
3. 玩家與地圖物體互動（釘板、迷霧、門、按鈕）
4. 玩家位置重置與同步
5. 通用的地圖配置管理
"""
import pygame
import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from collections import deque

from games.base_game import BaseLogicInterface
from sync_helpers import apply_server_update, tick_remote_sync, reset_sync_state


# ──────────────────────────────────────────────────────────────────────────────
# 通用常數：地圖磁貼類型 & 地圖規格
# ──────────────────────────────────────────────────────────────────────────────
# 磁貼類型常數（所有多玩家遊戲共用）
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（已廢棄：地圖載入時通常轉成空地 E，保留常數僅為相容舊地圖）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半數秒）
F = 6   # Fog（迷霧陷阱，踩到後致盲）

# 地圖規格（固定）
TILE_SIZE = 60
ROWS = 18
COLS = 32

# 通用狀態效果持續時間（秒）
SPIKE_SLOW_DURATION = 3.0  # 釘板減速持續時間
FOG_DURATION = 2.5         # 迷霧致盲持續時間

# 通用遊戲常數
AVATAR_SIZE = 24
RESCUE_RADIUS = 70
FOG_VISION_RADIUS = 50
DEFEAT_VOTE_TIME = 30.0

REVIVE_SLOW_STEP = 0.18
REVIVE_SLOW_FLOOR = 0.12


# ──────────────────────────────────────────────────────────────────────────────
# 通用工具函數
# ──────────────────────────────────────────────────────────────────────────────

def tile_center(row: int, col: int, tile_size: int = TILE_SIZE):
    """回傳指定格子中心點的像素座標 (x, y)。"""
    x = col * tile_size + tile_size // 2
    y = row * tile_size + tile_size // 2
    return x, y


def pixel_to_tile(px: float, py: float, tile_size: int = TILE_SIZE):
    """將像素座標轉換為格座標 (row, col)，用於碰撞查詢。"""
    col = int(px / tile_size)
    row = int(py / tile_size)
    return row, col


def is_wall_tile(tile_type: int) -> bool:
    """判斷指定磁貼類型是否為不可通行（牆或閘門）。"""
    return tile_type == W or tile_type == G


def is_wall(tile_map: list, row: int, col: int, rows: int = ROWS, cols: int = COLS) -> bool:
    """判斷指定格座標是否為牆壁或閘門（不可通行）。"""
    if row < 0 or row >= rows or col < 0 or col >= cols:
        return True  # 超出邊界視為牆
    t = tile_map[row][col]
    return is_wall_tile(t)


def nearest_empty_tile(tile_map: list, row: int, col: int, rows: int = ROWS, cols: int = COLS) -> tuple:
    """
    以 BFS 從 (row, col) 往外找最近的「空地(E)」格座標。
    用於把理想位置吸附到可站立的格子。
    找不到任何空地時回傳原座標。
    """
    queue = deque([(row, col)])
    visited = {(row, col)}
    while queue:
        r, c = queue.popleft()
        if 0 <= r < rows and 0 <= c < cols and tile_map[r][c] == E:
            return (r, c)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (nr, nc) not in visited and 0 <= nr < rows and 0 <= nc < cols:
                visited.add((nr, nc))
                queue.append((nr, nc))
    return (row, col)


class PlayerGameLogicInterface(BaseLogicInterface, ABC):
    """
    多玩家小遊戲的共用基底：處理所有與「玩家間互動」與「玩家與地圖互動」相關的邏輯。
    
    子類需要：
    1. 實作 _get_player_dict() → { color: PlayerState }
    2. 實作 get_map_data() → 回傳包含地圖、出生點、蓄能站等的配置字典
    3. 實作 get_tile_at(x, y) → tile_type 
    4. 實作 on_player_move(player, dx, dy, dt) 用於自訂移動行為
    5. 實作 on_tile_interaction(player, tile_type) 用於自訂地圖物體邏輯
    6. 實作 on_player_caught(player) 用於自訂倒地邏輯
    7. 實作 on_player_rescued(player, rescuer) 用於自訂復活邏輯
    
    類別常數（所有遊戲共用）：
    - TILE_SIZE = 60
    - ROWS = 18
    - COLS = 32
    - 磁貼類型: W, E, P, G, B, S, F
    """
    
    # 類別常數：地圖規格與磁貼類型（所有多玩家遊戲共用）
    TILE_SIZE = TILE_SIZE
    ROWS = ROWS
    COLS = COLS
    SPIKE_SLOW_DURATION = SPIKE_SLOW_DURATION
    FOG_DURATION = FOG_DURATION
    
    # 磁貼類型常數
    WALL = W
    EMPTY = E
    PELLET = P
    GATE = G
    BUTTON = B
    SPIKE = S
    FOG = F

    def __init__(self, socket_client, player_id_list, sound_manager):
        super().__init__(socket_client, player_id_list, sound_manager)
        
        # 救援狀態跟蹤
        self._rescue_progress = {}  # { color: { "progress": float, "rescuer": color, "being_rescued": bool } }

    # ─────────────────────────────────────────────────────────────────────
    # 抽象方法：子類必須實作
    # ─────────────────────────────────────────────────────────────────────

    @abstractmethod
    def _get_player_dict(self) -> dict:
        """
        回傳該遊戲的所有玩家狀態字典 { color: PlayerState }。
        遊戲每次初始化時都會被呼叫。
        """
        pass

    @abstractmethod
    def get_map_data(self) -> dict:
        """
        回傳遊戲關卡的完整配置字典，包含：
        {
            "tile_map": [[int, ...], ...],      # 地圖磁貼類型
            "spawn_points": { color: (row, col), ... },  # 玩家出生格座標
            "charge_stations": { color: (row, col), ... } # 蓄能站格座標（若有）
        }
        
        可選欄位：
        - "gate_coords": [(row, col), ...] 
        - "button_coords": [(row, col), ...]
        - ... 其他遊戲特定資料
        """
        pass

    @abstractmethod
    def get_tile_at(self, x: float, y: float) -> int:
        """
        根據像素座標 (x, y) 回傳該位置的地圖磚片類型。
        子類應根據地圖佈局與 tile_size 實作此方法。
        :return: 磚片類型常數 (例如 W=牆, E=空地, S=釘板, F=迷霧等)
        """
        pass

    @abstractmethod
    def on_player_move(self, player: Any, dx: float, dy: float, dt: float):
        """
        玩家移動邏輯（子類可自訂）。
        預設實作呼叫 player.move() 並處理地圖互動。
        子類可覆蓋以實作遊戲特定的移動規則（例如特殊地板、傳送門等）。
        :param player: 要移動的玩家物件
        :param dx: 水平輸入 (-1, 0, 1)
        :param dy: 垂直輸入 (-1, 0, 1)
        :param dt: 時間差
        """
        pass

    @abstractmethod
    def on_tile_interaction(self, player: Any, tile_type: int):
        """
        玩家踩到特定磚片時的互動（子類可自訂）。
        基類實作會自動處理 SPIKE 和 FOG。
        子類可覆蓋以新增遊戲特定的磚片類型與行為。
        :param player: 踩到磚片的玩家
        :param tile_type: 磚片類型常數
        """
        pass

    @abstractmethod
    def on_player_caught(self, player: Any):
        """
        玩家被敵人抓到時的邏輯（倒地）。
        預設：標記倒地、播音效、廣播事件。
        子類可覆蓋以新增特定的倒地規則（例如失去物品、扣分等）。
        """
        pass

    @abstractmethod
    def on_player_rescued(self, player: Any, rescuer: Any):
        """
        玩家被隊友救起時的邏輯（復活）。
        預設：標記復活、套用救援計數（永久減速）、廣播事件。
        子類可覆蓋以新增特定的復活規則（例如賦予臨時保護、增益等）。
        :param player: 被救的玩家
        :param rescuer: 執行救援的玩家
        """
        pass

    @abstractmethod
    def get_rescue_radius(self) -> float:
        """回傳該遊戲的救援檢測半徑（像素）。"""
        pass

    @abstractmethod
    def get_rescue_hold_time(self) -> float:
        """回傳該遊戲救援需要的按住秒數。"""
        pass

    # ─────────────────────────────────────────────────────────────────────
    # 通用的玩家互動方法：子類可直接呼叫或覆蓋
    # ─────────────────────────────────────────────────────────────────────

    def update_player_movement(self, dt: float, local_player: Any,
                               input_dx: float, input_dy: float,
                               is_wall_cb, tile_size: int = 60):
        """
        通用玩家移動更新邏輯：處理輸入、碰撞、地圖互動。
        
        :param dt: 時間差
        :param local_player: 本地玩家物件
        :param input_dx: 水平輸入向量
        :param input_dy: 垂直輸入向量
        :param is_wall_cb: 碰撞檢查回呼函式 (x, y) → bool
        :param tile_size: 地圖磚片大小（像素）
        """
        if not local_player or not local_player.is_alive or self.is_input_locked:
            return

        # 收集其他玩家的碰撞矩形
        players_dict = self._get_player_dict()
        other_rects = [p.rect for c, p in players_dict.items() if c != local_player.color_key]

        # 執行基礎移動（含牆、陷阱碰撞）
        local_player.move(
            input_dx, input_dy, dt,
            tile_size,
            is_wall_cb,
            others=other_rects,
        )

        # 子類特定的移動邏輯
        self.on_player_move(local_player, input_dx, input_dy, dt)

        # 移動後處理地圖物體互動
        self._handle_map_interactions(local_player)

    def _handle_map_interactions(self, player: Any):
        """
        掃描玩家當前位置的磚片類型並呼叫對應的互動處理。
        自動處理通用的 SPIKE 和 FOG 效果。
        """
        tile_type = self.get_tile_at(player.x, player.y)
        if tile_type is None:
            return
        
        # 處理通用效果
        if tile_type == self.SPIKE:  # 釘板
            if hasattr(player, 'spike_timer'):
                if player.spike_timer <= 0:
                    player.spike_timer = self.SPIKE_SLOW_DURATION
        elif tile_type == self.FOG:  # 迷霧
            if hasattr(player, 'fog_timer'):
                if player.fog_timer <= 0:
                    if hasattr(self, 'sound_manager'):
                        self.sound_manager.play("blind")
                player.fog_timer = self.FOG_DURATION
        
        # 調用子類特定的磚片互動邏輯
        self.on_tile_interaction(player, tile_type)

    def update_rescues(self, dt: float, local_player: Any):
        """
        通用救援邏輯更新：自動偵測附近倒地隊友並推進救援進度。
        
        :param dt: 時間差
        :param local_player: 執行救援的玩家
        """
        if not local_player or not local_player.is_alive or self.is_input_locked:
            return

        players_dict = self._get_player_dict()
        rescue_radius = self.get_rescue_radius()
        rescue_hold_time = self.get_rescue_hold_time()

        for color, target in players_dict.items():
            if color == local_player.color_key or target.is_alive:
                continue

            # 初始化救援狀態追蹤
            if color not in self._rescue_progress:
                self._rescue_progress[color] = {
                    "progress": 0.0,
                    "rescuer": None,
                    "being_rescued": False,
                }

            state = self._rescue_progress[color]

            # 偵測鄰近倒地隊友
            dist = math.hypot(local_player.x - target.x, local_player.y - target.y)
            in_range = dist <= rescue_radius

            if in_range and not state["being_rescued"]:
                # 開始救援
                state["being_rescued"] = True
                state["rescuer"] = local_player.color_key
                state["progress"] = 0.0
                try:
                    self.socket_client.send_game_event({
                        "type": "rescue_progress_start", "color": color
                    })
                except Exception as e:
                    print(f"[PlayerGameLogicInterface] rescue_progress_start failed: {e}")

            if state["being_rescued"]:
                if in_range:
                    # 繼續救援
                    state["progress"] += dt
                    if state["progress"] >= rescue_hold_time:
                        # 救援完成
                        target.is_alive = True
                        target.visual_key = f"{target.color_key}_idle"
                        state["progress"] = 0.0
                        state["being_rescued"] = False
                        state["rescuer"] = None
                        self.on_player_rescued(target, local_player)
                        try:
                            self.socket_client.send_game_event({
                                "type": "player_rescued",
                                "color": color,
                                "rescuer": local_player.color_key
                            })
                        except Exception as e:
                            print(f"[PlayerGameLogicInterface] player_rescued broadcast failed: {e}")
                else:
                    # 離開救援範圍：中斷救援
                    if state["progress"] > 0:
                        state["being_rescued"] = False
                        state["progress"] = 0.0
                        try:
                            self.socket_client.send_game_event({
                                "type": "rescue_progress_stop", "color": color
                            })
                        except Exception as e:
                            print(f"[PlayerGameLogicInterface] rescue_progress_stop failed: {e}")

    def sync_remote_players(self, dt: float, player_speed: float, bounds: tuple = None):
        """
        通用遠端玩家同步：應用 Dead Reckoning + LERP 更新非本地玩家位置。
        
        :param dt: 時間差
        :param player_speed: 用於預測的玩家速度基準
        :param bounds: 可選的邊界限制 (x_min, y_min, x_max, y_max)
        """
        players_dict = self._get_player_dict()
        for color, p in players_dict.items():
            if color == self.socket_client.player_color:
                continue
            if not self.is_input_locked:
                tick_remote_sync(p, p.sync, dt, player_speed, bounds=bounds)

    def reset_player_position(self, player: Any, spawn_row: int, spawn_col: int, tile_size: int = 60):
        """
        重置玩家位置到指定格座標的中心。
        
        :param player: 要重置的玩家
        :param spawn_row: 出生格的行座標
        :param spawn_col: 出生格的列座標
        :param tile_size: 地圖磚片大小
        """
        cx = spawn_col * tile_size + tile_size // 2
        cy = spawn_row * tile_size + tile_size // 2
        player.x, player.y = float(cx), float(cy)
        reset_sync_state(player.sync, float(cx), float(cy))

    def handle_remote_player_update(self, data: dict):
        """
        處理來自遠端玩家位置的同步封包。
        
        :param data: 遠端玩家的 player_pos 封包
        """
        players_dict = self._get_player_dict()
        color = data.get("color")
        p = players_dict.get(color)

        if not p or color == self.socket_client.player_color:
            return

        # 正規化輸入向量（若為斜向）
        raw_dx = data.get("dx", 0.0)
        raw_dy = data.get("dy", 0.0)
        if raw_dx != 0 and raw_dy != 0:
            raw_dx *= 0.7071
            raw_dy *= 0.7071

        # 更新視覺朝向
        if raw_dx > 0:
            p.direction = "right"
        elif raw_dx < 0:
            p.direction = "left"
        elif raw_dy != 0:
            p.direction = "frontback"
        else:
            p.direction = "idle"
        p.visual_key = f"{p.color_key}_{p.direction}"

        # 套用遠端位置更新
        apply_server_update(
            p.sync,
            data.get("x", p.sync.target_x),
            data.get("y", p.sync.target_y),
            raw_dx, raw_dy
        )
        p.current_dx = data.get("dx", p.current_dx)
        p.current_dy = data.get("dy", p.current_dy)

    def handle_player_caught_event(self, data: dict):
        """
        處理遠端的 player_caught 事件（玩家被敵人抓到）。
        
        :param data: 事件封包
        """
        players_dict = self._get_player_dict()
        color = data.get("color")
        p = players_dict.get(color)

        if p and p.is_alive:
            p.is_alive = False
            self.sound_manager.play("eat")
            self.on_player_caught(p)

    def handle_player_rescued_event(self, data: dict):
        """
        處理遠端的 player_rescued 事件（玩家被救起）。
        
        :param data: 事件封包
        """
        players_dict = self._get_player_dict()
        color = data.get("color")
        p = players_dict.get(color)

        if p and not p.is_alive:
            p.is_alive = True
            p.visual_key = f"{p.color_key}_idle"
            # 子類應在 on_player_rescued 中處理救援計數等邏輯
            rescuer_color = data.get("rescuer")
            if rescuer_color:
                rescuer = players_dict.get(rescuer_color)
                if rescuer:
                    self.on_player_rescued(p, rescuer)

    def handle_rescue_progress_start(self, data: dict):
        """處理救援進度開始事件。"""
        color = data.get("color")
        if color not in self._rescue_progress:
            self._rescue_progress[color] = {
                "progress": 0.0,
                "rescuer": None,
                "being_rescued": False,
            }
        self._rescue_progress[color]["being_rescued"] = True
        self._rescue_progress[color]["progress"] = 0.0

    def handle_rescue_progress_stop(self, data: dict):
        """處理救援進度停止事件。"""
        color = data.get("color")
        if color in self._rescue_progress:
            self._rescue_progress[color]["being_rescued"] = False
            self._rescue_progress[color]["progress"] = 0.0

    # ─────────────────────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────────────────────

    def get_rescue_progress(self, color: str) -> float:
        """回傳指定玩家當前的救援進度 (0.0 ~ 1.0)。"""
        if color in self._rescue_progress:
            max_time = self.get_rescue_hold_time()
            if max_time > 0:
                return min(1.0, self._rescue_progress[color]["progress"] / max_time)
        return 0.0

    def is_player_being_rescued(self, color: str) -> bool:
        """回傳指定玩家是否正在被救援。"""
        return self._rescue_progress.get(color, {}).get("being_rescued", False)

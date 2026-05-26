# --- 實體與管理模組 ---
import pygame
import math

class Entity:
    """
    實體基礎類別 (Base Entity)
    
    職責：
    1. 定義所有遊戲物件的基礎物理屬性（座標、旋轉、縮放）。
    2. 持有 visual_key，作為與 VisualRegistry 溝通的橋樑。
    3. 提供統一的介面供 EntityManager 呼叫。
    """
    def __init__(self, x, y, visual_key=None):
        self.x = x
        self.y = y
        self.visual_key = visual_key # 對應 VisualRegistry 中的標籤
        self.active = True           # 物件是否還存在於世界上

    def update(self, dt):
        """
        每一幀的邏輯更新。
        由子類別實作移動、狀態切換等行為。
        """
        pass

class Ghost(Entity):
    """
    動態玩家類別 (Ghost/Actor)
    
    職責：
    1. 行為控制：處理移動座標計算。
    2. 動畫狀態機：根據移動速度或輸入，決定現在該換成哪一個 visual_key。
    3. 同步機制：預留接收伺服器資料的介面，實作 Week 3 的 LERP 插值平滑移動。
    """
    def __init__(self, color_key="blue", avatar_size=24):
        super().__init__(640, 360, visual_key=f"ghost_{color_key}_idle")
        self.color_key = color_key  # 保存顏色鍵以供 visual_key 更新與 fallback 繪製使用
        self.avatar_size = avatar_size # 統一使用實體的半徑屬性
        self.speed = 200
        self.state = "IDLE" # 基礎狀態機：IDLE, WALK, DEAD
        self.current_dx = 0  # 上一幀的原始輸入方向，供網路廣播使用
        self.current_dy = 0

    def move(self, dx, dy, dt):
        """
        計算位移並根據方向更新狀態（進而影響 visual_key）。
        dx/dy 為 0 時仍需呼叫，以便將狀態重設回 IDLE。
        """
        # 記錄原始輸入方向（正規化前），供網路位置廣播使用
        self.current_dx = dx
        self.current_dy = dy

        # 斜向移動時正規化，避免速度變成水平/垂直的 √2 倍
        if dx != 0 and dy != 0:
            dx *= 0.7071
            dy *= 0.7071

        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt

        # 邊界夾緊，確保角色不會跑出畫面
        self.x = max(self.avatar_size, min(1280 - self.avatar_size, self.x))
        self.y = max(self.avatar_size, min(720 - self.avatar_size, self.y))

        # 根據是否有移動更新狀態與對應的視覺鍵
        self.state = "WALK" if (dx != 0 or dy != 0) else "IDLE"
        self.visual_key = f"ghost_{self.color_key}_{self.state.lower()}"

    def move_in_maze(self, dx, dy, dt, tile_size, is_wall_cb):
        """
        執行迷宮物理移動，包含走廊吸附與碰撞偵測。
        :param is_wall_cb: 一個接收 (x, y) 並回傳 bool 的函式，判斷該點是否撞牆。
        """
        if dx == 0 and dy == 0:
            self.current_dx, self.current_dy = 0.0, 0.0
            return

        move_dist = self.speed * dt
        # 使用實體自身的半徑進行碰撞偵測
        radius = self.avatar_size
        # 吸附容差
        snap_threshold = tile_size * 0.35

        # 1. 走廊吸附邏輯 (Corridor Snapping)
        # 計算當前所在格子的中心點
        grid_col = int(self.x / tile_size)
        grid_row = int(self.y / tile_size)
        center_x = grid_col * tile_size + tile_size // 2
        center_y = grid_row * tile_size + tile_size // 2

        if dx != 0 and dy == 0: # 純水平移動，吸附 Y 軸
            offset_y = center_y - self.y
            if abs(offset_y) <= snap_threshold:
                self.y += math.copysign(min(abs(offset_y), move_dist * 0.8), offset_y)
        elif dy != 0 and dx == 0: # 純垂直移動，吸附 X 軸
            offset_x = center_x - self.x
            if abs(offset_x) <= snap_threshold:
                self.x += math.copysign(min(abs(offset_x), move_dist * 0.8), offset_x)

        # 2. 嘗試移動並檢查碰撞 (獨立處理 X 與 Y，實現滑牆效果)
        def check_collision(nx, ny):
            corners = [(nx-radius, ny-radius), (nx+radius, ny-radius),
                       (nx-radius, ny+radius), (nx+radius, ny+radius)]
            return any(is_wall_cb(cx, cy) for cx, cy in corners)

        if dx != 0:
            new_x = self.x + math.copysign(move_dist, dx)
            if not check_collision(new_x, self.y):
                self.x = new_x
        
        if dy != 0:
            new_y = self.y + math.copysign(move_dist, dy)
            if not check_collision(self.x, new_y):
                self.y = new_y

        self.current_dx = float(dx)
        self.current_dy = float(dy)
        # 更新動畫狀態
        self.state = "WALK"
        self.visual_key = f"ghost_{self.color_key}_{self.state.lower()}"

    def update(self, dt):
        """
        處理物理更新與動畫影格切換。
        """
        pass

class RemoteGhost(Entity):
    """
    遠端玩家實體：以 LERP 插值平滑渲染位置，Dead Reckoning 補償封包延遲。
    """
    LERP_SPEED = 12   # 越高越貼近目標（生硬），越低越平滑（但落後越多）
    DR_TIMEOUT = 0.2  # 超過此秒數未收到更新時啟動 Dead Reckoning
    SPEED = 200       # 與 Ghost 相同，供 Dead Reckoning 預測位移使用
    AVATAR_SIZE = 24

    def __init__(self, player_id, color_key="green"):
        super().__init__(640, 360, visual_key=f"ghost_{color_key}_idle")
        self.player_id = player_id
        self.color_key = color_key
        self.target_x = 640.0  # 伺服器權威位置（目標）
        self.target_y = 360.0
        self._dr_dx = 0.0      # Dead Reckoning 使用的上次速度方向
        self._dr_dy = 0.0
        self._stale_time = 0.0  # 距上次收到封包的秒數
        self.disconnected = False  # 隊友斷線標記，由 Engine 設定

    def apply_server_update(self, x, y, dx, dy):
        """收到伺服器轉發的封包時，更新目標位置與速度方向。"""
        self.target_x = x
        self.target_y = y
        self._dr_dx = dx
        self._dr_dy = dy
        self._stale_time = 0.0
        state = "walk" if (dx != 0 or dy != 0) else "idle"
        self.visual_key = f"ghost_{self.color_key}_{state}"

    def update(self, dt):
        """每幀：Dead Reckoning 預測目標，LERP 平滑逼近渲染位置。"""
        self._stale_time += dt

        # Dead Reckoning：封包過舊時以上次速度繼續預測目標位置
        if self._stale_time > self.DR_TIMEOUT and (self._dr_dx != 0 or self._dr_dy != 0):
            self.target_x += self._dr_dx * self.SPEED * dt
            self.target_y += self._dr_dy * self.SPEED * dt
            self.target_x = max(self.AVATAR_SIZE, min(1280 - self.AVATAR_SIZE, self.target_x))
            self.target_y = max(self.AVATAR_SIZE, min(720 - self.AVATAR_SIZE, self.target_y))

        # LERP：render 位置每幀平滑逼近 target 位置
        factor = min(1.0, self.LERP_SPEED * dt)
        self.x += (self.target_x - self.x) * factor
        self.y += (self.target_y - self.y) * factor


class StaticObject(Entity):
    """
    靜態環境物件 (Static Object)
    
    職責：
    1. 場景裝飾：如牆壁、背景、固定的障礙物。
    2. 效能節省：這些物件不具備 update 邏輯，Renderer 僅負責將其畫在固定位置。
    3. 碰撞框提供：提供靜態的矩形 (Rect) 給碰撞系統參考。
    """
    def __init__(self, x, y, visual_key):
        super().__init__(x, y, visual_key)
        self.collidable = True # 是否具備碰撞功能

class TestEntity(Entity):
    """
    測試用 5x5 精靈圖實體 (Test Entity)
    
    職責：
    1. 影格管理：管理 5x5 格式大圖的當前播放影格索引 (0-24)。
    2. 切割計算：根據 frame_index 計算在大圖上的矩形範圍 (Rect)。
    3. 自動播放：在 update 中根據時間自動循環切換影格。
    """
    def __init__(self, x, y, visual_key):
        super().__init__(x, y, visual_key)
        self.frame_index = 0
        self.animation_timer = 0
        self.animation_speed = 0.05  # 每 0.05 秒切換一次影格
        self.rows = 5
        self.cols = 5

    def update(self, dt):
        """更新動畫影格循環"""
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0
            # 在 25 個影格 (5x5) 之間循環播放
            self.frame_index = (self.frame_index + 1) % (self.rows * self.cols)

    def get_sprite_rect(self, surface):
        """計算並回傳當前影格在 spritesheet 上的 Rect 範圍，供 Renderer 呼叫"""
        frame_w = surface.get_width() // self.cols
        frame_h = surface.get_height() // self.rows
        
        col = self.frame_index % self.cols
        row = self.frame_index // self.cols
        
        return pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)

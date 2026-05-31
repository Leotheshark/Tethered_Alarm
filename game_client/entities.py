# --- 實體與管理模組 ---
import pygame
import math

from sync_helpers import RemoteSyncState, apply_server_update, tick_remote_sync

PLAYER_SPEED = 180  # Ghost 預設移動速度（像素/秒），小遊戲可 import 此常數共用

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
        self.width = 32              # 預設碰撞寬度
        self.height = 32             # 預設碰撞高度

    @property
    def rect(self):
        """取得實體的 AABB 碰撞矩形 (以 x, y 為中心)"""
        return pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)

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
        self.direction = "right" # 當前朝向：left, right
        super().__init__(960, 540, visual_key=f"{color_key}_{self.direction}")
        
        self.color_key = color_key  # 保存顏色鍵以供 visual_key 更新與 fallback 繪製使用
        self.avatar_size = avatar_size # 統一使用實體的半徑屬性
        self.width = avatar_size * 2    # 碰撞箱寬度 (直徑)
        self.height = avatar_size * 2   # 碰撞箱高度 (直徑)
        self.speed = PLAYER_SPEED
        self.is_alive = True            # 存活狀態
        
        self.current_dx = 0  # 上一幀的原始輸入方向，供網路廣播使用
        self.current_dy = 0

        # 1x2 動畫屬性
        self.frame_index = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.15  # 每 0.15 秒切換一次影格

    def move(self, dx, dy, dt, tile_size=32, is_wall_cb=None, others=None):
        """
        執行物理移動。統一整合斜向位移正規化、滑牆碰撞偵測與全域邊界限制。
        此演算法同時適用於迷宮（需傳入碰撞回呼）與大廳（使用預設值）。
        :param is_wall_cb: 一個接收 (x, y) 並回傳 bool 的函式，判斷該點是否撞牆。
        :param others: 一個包含其他實體 pygame.Rect 的清單，用於處理角色間碰撞。
        """
        self.current_dx, self.current_dy = float(dx), float(dy)

        # 根據輸入更新狀態：優先左右，次之上下，無輸入則 idle
        if dx > 0:
            self.direction = "right"
        elif dx < 0:
            self.direction = "left"
        elif dy != 0:
            self.direction = "frontback"
        else:
            self.direction = "idle"
            
        self.visual_key = f"{self.color_key}_{self.direction}"
        if dx == 0 and dy == 0: return

        # 1. 斜向移動正規化：確保斜著走的速度與水平/垂直一致 (1.0x 而非 1.414x)
        nx, ny = dx, dy
        if dx != 0 and dy != 0:
            nx, ny = dx * 0.7071, dy * 0.7071

        move_dist_x = abs(nx) * self.speed * dt
        move_dist_y = abs(ny) * self.speed * dt

        # 2. 準備碰撞與吸附參數 (以傳入的 tile_size 為準，大廳預設 32)
        radius = self.avatar_size
        snap_threshold = tile_size * 0.35  # 吸附閾值，輔助玩家對齊走廊中心
        grid_col, grid_row = int(self.x / tile_size), int(self.y / tile_size)
        center_x, center_y = grid_col * tile_size + tile_size // 2, grid_row * tile_size + tile_size // 2

        # 3. 定義內部碰撞檢查：檢查角色矩形四角，若無 callback 則視為不撞牆 (大廳模式)
        def check_collision(nx, ny):
            # A. 牆壁碰撞偵測
            if is_wall_cb:
                # 檢查角色 bounding box 的四個角落是否進入牆面
                corners = [(nx - radius, ny - radius), (nx + radius - 1, ny - radius),
                           (nx - radius, ny + radius - 1), (nx + radius - 1, ny + radius - 1)]
                if any(is_wall_cb(cx, cy) for cx, cy in corners):
                    return True
            
            # B. 實體間碰撞偵測 (AABB)
            if others:
                # 建立虛擬的新位置矩形，檢查是否與其他實體重疊
                new_rect = pygame.Rect(nx - radius, ny - radius, radius * 2, radius * 2)
                for other_rect in others:
                    if new_rect.colliderect(other_rect):
                        return True
            
            return False

        # 4. 走廊吸附 (Corridor Snapping)
        # 只有在「即將撞牆」的情況下才執行吸附，這能確保在空地不會有磁吸感。
        # 當玩家移動時蹭到牆邊，或者在轉角處被卡住時，吸附能幫助玩家對齊走廊中心以順利通過。
        if is_wall_cb:
            if dx != 0 and dy == 0:  # 純水平移動
                # 測試如果不吸附，直接前進是否會撞牆（包含因為 y 座標偏移而蹭到側邊的牆）
                if check_collision(self.x + math.copysign(move_dist_x, dx), self.y):
                    offset_y = center_y - self.y
                    if abs(offset_y) <= snap_threshold:
                        self.y += math.copysign(min(abs(offset_y), move_dist_x * 1.2), offset_y)
            elif dy != 0 and dx == 0:  # 純垂直移動
                # 測試如果不吸附，直接前進是否會撞牆
                if check_collision(self.x, self.y + math.copysign(move_dist_y, dy)):
                    offset_x = center_x - self.x
                    if abs(offset_x) <= snap_threshold:
                        self.x += math.copysign(min(abs(offset_x), move_dist_y * 1.2), offset_x)

        # 5. 分軸位移 (Sliding Physics)：分開處理 X 與 Y，達成流暢的「滑牆」效果
        if dx != 0:
            new_x = self.x + math.copysign(move_dist_x, dx)
            if not check_collision(new_x, self.y): self.x = new_x
        if dy != 0:
            new_y = self.y + math.copysign(move_dist_y, dy)
            if not check_collision(self.x, new_y): self.y = new_y

        # 6. 全域邊界限制 (Boundary Clamp)：確保角色不論在任何模式都不會跑出 1920x1080 視窗
        self.x = max(self.avatar_size, min(1920 - self.avatar_size, self.x))
        self.y = max(self.avatar_size, min(1080 - self.avatar_size, self.y))

    def update(self, dt):
        """
        處理物理更新與動畫影格切換。
        """
        # 若死亡，強制切換為 dead 精靈圖
        if not self.is_alive:
            self.visual_key = "dead"

        # 所有狀態（包含死亡時的 dead.png）皆執行動畫循環
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0
            # 根據視覺資源決定影格數：left/right 為 3 欄，其餘 (包含 dead) 為 2 欄
            cols = 3 if ("left" in self.visual_key or "right" in self.visual_key) else 2
            self.frame_index = (self.frame_index + 1) % cols

    def get_sprite_rect(self, surface):
        """水平切割：高度不變，寬度除以欄數 (3 或 2)"""
        w, h = surface.get_size()
        cols = 3 if ("left" in self.visual_key or "right" in self.visual_key) else 2
        frame_w = w // cols
        # 修正：加上 % cols 確保切換方向時索引不會越界導致角色消失
        return pygame.Rect((self.frame_index % cols) * frame_w, 0, frame_w, h)

class RemoteGhost(Entity):
    """
    遠端玩家實體：透過 sync_helpers 套用 LERP + Dead Reckoning，平滑渲染遠端位置。
    """
    SPEED = PLAYER_SPEED  # 與 Ghost 相同，供 Dead Reckoning 預測位移使用
    AVATAR_SIZE = 32
    # 大廳場景邊界（畫面 1920x1080 扣除頭像半徑）
    _BOUNDS = (AVATAR_SIZE, AVATAR_SIZE, 1920 - AVATAR_SIZE, 1080 - AVATAR_SIZE)
    _DR_TIMEOUT = 0.2  # 大廳對抖動容忍度較高，採用稍寬鬆的超時

    def __init__(self, player_id, color_key="green", avatar_size=28):
        self.direction = "idle"  # 修正為小寫，確保與 VisualRegistry 載入的 Key 匹配
        super().__init__(960, 540, visual_key=f"{color_key}_{self.direction}")
        
        self.avatar_size = avatar_size  # 與 Ghost 保持一致的尺寸屬性名稱
        self.width = self.avatar_size * 2
        self.height = self.avatar_size * 2
        self.player_id = player_id
        self.color_key = color_key
        self.sync = RemoteSyncState(target_x=960.0, target_y=540.0)
        self.disconnected = False  # 隊友斷線標記，由 Engine 設定
        self.is_alive = True
        self.frame_index = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.15

    def apply_server_update(self, x, y, dx, dy):
        """收到伺服器轉發的封包時，更新目標位置與速度方向，並切換動畫狀態。"""
        apply_server_update(self.sync, x, y, dx, dy)
        if dx > 0:
            self.direction = "right"
        elif dx < 0:
            self.direction = "left"
        elif dy != 0:
            self.direction = "frontback"
        else:
            self.direction = "idle"

        self.visual_key = f"{self.color_key}_{self.direction}"

    def update(self, dt):
        """每幀：Dead Reckoning 預測目標 + LERP 平滑逼近渲染位置。"""
        tick_remote_sync(self, self.sync, dt, self.SPEED,
                         bounds=self._BOUNDS, dr_timeout=self._DR_TIMEOUT)
        
        # 若死亡，強制切換為 dead 精靈圖
        if not self.is_alive:
            self.visual_key = "dead"

        # 更新遠端玩家動畫影格 (邏輯同 Ghost)
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0
            cols = 3 if ("left" in self.visual_key or "right" in self.visual_key) else 2
            self.frame_index = (self.frame_index + 1) % cols

    def get_sprite_rect(self, surface):
        w, h = surface.get_size()
        cols = 3 if ("left" in self.visual_key or "right" in self.visual_key) else 2
        frame_w = w // cols
        # 修正：加上 % cols 確保切換方向時索引不會越界
        return pygame.Rect((self.frame_index % cols) * frame_w, 0, frame_w, h)


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

class ColorButton(StaticObject):
    """
    身分驗證按鈕：僅特定顏色的玩家站在上面時會計時。
    """
    def __init__(self, x, y, color):
        # 暫時不使用精靈圖，視覺由渲染器根據狀態動態繪製
        super().__init__(x, y, visual_key=None)
        self.assigned_color = color
        self.charge_timer = 0.0
        self.is_triggered = False
        self.activated_time = 0  # 紀錄被點亮的精確時間 (ms)
        self.width = 60  # 與地圖格子大小一致
        self.height = 60

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

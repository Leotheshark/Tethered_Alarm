# --- 實體與管理模組 ---
import pygame

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
    def __init__(self, color_key="blue"):
        super().__init__(640, 360, visual_key=f"ghost_{color_key}_idle")
        self.speed = 200
        self.state = "IDLE" # 基礎狀態機：IDLE, WALK, DEAD

    def move(self, dx, dy, dt):
        """
        計算位移並根據方向更新狀態（進而影響 visual_key）。
        """
        pass

    def update(self, dt):
        """
        處理物理更新與動畫影格切換。
        """
        pass

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

class EntityManager:
    """
    實體管理員 (Entity Manager)
    
    職責：
    1. 容器功能：持有遊戲中所有的 Entity 實例。
    2. 批量操作：一鍵執行所有物件的 update。
    3. 渲染橋樑：提供 draw_all 所需的實體清單，並依據物件類型進行簡單排序。
    """
    def __init__(self):
        self.entities = []

    def add(self, entity):
        """
        將新的物件加入世界。
        可以根據 tag 決定加入哪一個層級的清單。
        """
        self.entities.append(entity)

    def update_all(self, dt):
        for entity in self.entities:
            entity.update(dt)

    def draw_all(self, screen):
        """
        注意：這裡不直接呼叫 entity.draw()。
        而是應該由 Renderer 負責，這裡僅提供資料。
        符合「視覺資源由註冊中心統一調度」的原則。
        """
        # TODO: 實作根據 Z-index 或 Y 座標排序繪製，確保物件遮擋關係正確
        pass

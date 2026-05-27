# --- 實體管理模組 ---

class EntityManager:
    """
    實體管理員 (Entity Manager)
    
    職責：
    1. 集中管理：持有遊戲世界中所有活著的實體 (Entities)。
    2. 批次處理：統一驅動所有實體的邏輯更新 (Update Loop)。
    3. 渲染橋樑：提供所有實體的清單給 Renderer 進行繪製，並可在此實作 Z-Order 排序。
    4. 生命週期管理：處理實體的加入與移除（例如：死亡或清理）。
    """
    def __init__(self):
        # 儲存所有實體的容器
        self.entities = []

    def add(self, entity):
        """
        將新的實體物件（如 Ghost 或 StaticObject）加入到管理清單。
        """
        if entity not in self.entities:
            self.entities.append(entity)

    def remove(self, entity):
        """
        手動將實體從世界中移除。
        """
        if entity in self.entities:
            self.entities.remove(entity)

    def update_all(self, dt):
        """
        每幀由 GameEngine 呼叫。
        遍歷所有實體並執行它們各自的 update 邏輯。
        """
        # 只更新處於啟動狀態 (Active) 的實體
        for entity in self.entities:
            if entity.active:
                entity.update(dt)

    def clear_all(self):
        """
        清空目前所有實體。
        用於遊戲重啟、切換關卡或回到大廳時。
        """
        self.entities.clear()

    def get_all_entities(self):
        """回傳目前所有的實體清單供渲染器使用"""
        return self.entities
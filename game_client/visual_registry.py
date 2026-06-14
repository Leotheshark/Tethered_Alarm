import pygame
import os

class VisualRegistry:
    """
    視覺資源註冊中心 (Visual Registry)
    
    職責：
    1. 資源快取：確保同一張圖片在記憶體中只存在一份，避免重複載入造成的效能損耗。
    2. 效能優化：載入時執行 convert_alpha()，優化 Pygame 的渲染速度。
    3. 視覺解耦：讓邏輯層只需透過 'Key' (例如 'player_idle') 存取資源，而不需要知道檔案路徑。
    4. 錯誤防禦：若找不到圖片，可回傳預留的錯誤圖樣，防止遊戲崩潰。
    """

    # 儲存載入後的 pygame.Surface 物件 { "key": Surface }
    _cache = {}

    # 儲存資源的分類標籤（選填，用於 Renderer 排序參考）
    _tags = {}

    @classmethod
    def load_image(cls, key, filename, tag="SPRITE"):
        """
        從 assets 夾載入圖片並進行優化處理。
        
        參數:
        - key: 資源的唯一識別標籤 (例: 'hero_walk')
        - filename: 檔案名稱 (例: 'hero.png')
        - tag: 資源類型，用於渲染層級參考 (例: 'BACKGROUND', 'SPRITE', 'UI')
        """
        if key in cls._cache:
            return cls._cache[key]

        # 取得 game_client 目錄路徑
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 嘗試可能的路徑 (相容單數 sprite 與複數 sprites 資料夾名稱)
        possible_paths = [
            os.path.join(base_path, "assets", "sprites", filename),
            os.path.join(base_path, "assets", "sprite", filename),
            os.path.join(base_path, "assets", "image", filename) # 新增搜尋路徑
        ]

        path = next((p for p in possible_paths if os.path.exists(p)), None)

        if path is None:
            print(f"[VisualRegistry] ❌ 錯誤: 找不到檔案 {filename}。請確認它存在於 assets/sprites/ 或 assets/image/ 中")
            return None

        image = pygame.image.load(path).convert_alpha()
        cls._cache[key] = image
        cls._tags[key] = tag
        # print(f"[VisualRegistry] ✅ 成功載入: {key} <- {path}")
        return image

    @classmethod
    def get_surface(cls, key):
        """
        根據 Key 獲取已載入的圖片資源。
        
        回傳: pygame.Surface 或 None (若找不到)
        """
        return cls._cache.get(key)

    @classmethod
    def clear_cache(cls):
        """
        清空所有已載入的資源，用於切換大關卡時釋放記憶體。
        """
        cls._cache.clear()
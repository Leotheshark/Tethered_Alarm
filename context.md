# Project Context: Tethered Alarm (Co-up Awakening)

## 程式碼生成規則
- **註解規則**：程式碼中要加上詳盡註解，讓每一步的目的清晰可見
- **生成程式碼前**：生成程式碼前一定要先看過整個專案的程式碼，並合理規劃資料夾及檔案路徑
  **生成程式碼時**：如果是創造新功能或新遊戲等等，先將完整的流程方案告訴使用者，再讓使用者決定是否生成；如果是修改原有的程式碼，根據使用者的要求做最小限度的修改就好。
- **核心架構規範**：
  - **狀態模式 (State Pattern)**：使用 StateManager 類別管理 `LOBBY`, `ALARM`, `GAME` 狀態切換，避免大型 if-else。
  - **數據標準化 (Dataclasses)**：所有網路同步封包應使用 `dataclasses` 定義，確保型別安全與 Key 名稱一致。
  - **系統層封裝**：Win32 API（防睡眠、視窗置頂）需統一封裝於 `SystemHelper` 工具類中。
  - **資源解耦**：音效與圖片資源由 `SoundManager` 或 `AssetLoader` 統一調度，不直接硬編碼於遊戲邏輯中。

##  專案目標與核心機制
- **核心概念**：一款網路連線、2~4人多人在線協作的解謎鬧鐘遊戲。遊戲會是類似bomber-man、pac-man的2D遊戲。
- **基本玩法**：所有玩家的鬧鐘會在約定的時間同時響起。玩家必須合作通關，才能關掉鬧鐘。
- **流程**：1.睡覺前(state 0):所有玩家到齊後，由房主設定起床時間，並進入睡覺state 2.起床時間，鬧鐘響起，出現ready按鈕，四個人都按下後，倒計時後遊戲開始 3.隨機抽取遊戲，四人合力嘗試通關 4. (a)通關成功，回到大廳，此時可以重新設定時鐘(回到 state 0) (b)通關失敗，可以選擇遭受開發者的嘲笑並投降，或者重新開始遊戲。

## 遊戲架構
### 【Python】= 核心邏輯與遊戲渲染 (The Core Engine & Game Renderer)
- 負責所有**遊戲邏輯、數學計算、狀態判定**。
- 負責管理所有遊戲狀態（State 0~3）、房間、玩家連線、鬧鐘定時器。
- 負責計算所有物件的座標 `(x, y)`、移動速度、碰撞偵測（Collision Detection）。
- **遊戲畫面渲染**：遊戲主體畫面由 Pygame 負責渲染，包含角色動畫與精靈圖處理。
- **音效播放控制**：由於封裝為 .exe，音效由 Python 端的原生驅動播放，不依賴瀏覽器 Audio API。
- **硬體監控**：實作 `hardware_monitor` 定期檢測預設輸出設備（喇叭/耳機），並即時推播狀態。

### 【HTML / JS】= 大廳介面與系統回饋 (Lobby Renderer)
- 負責**視覺呈現**：大廳 UI 由 HTML/JS 渲染，遊戲畫面則由 Pygame 渲染。
- 負責**系統狀態回饋**：顯示硬體設備警告（如耳機偵測）及提供音量測試按鈕。
- 負責**使用者輸入接收**：監聽大廳互動事件，並在進入遊戲後轉由 Pygame 接收鍵盤輸入。
- **邏輯被動性**：不計算物理碰撞或位移判定，專注於大廳流程引導。
- 使用 `pywebview` 載入 `server/static/` 下的頁面。

##  四週開發進度與微觀任務清單 (4-Week Micro-task Roadmap)

### Week 1: Foundation & Architecture (基礎建設與架構)
- **週目標**：建立穩定的網路連線，達成 4 個客戶端（Clients）與伺服器成功完成「握手連線（Handshake）」與房間綁定。
- **後端 (Backend)**：
  - [x] 實作基礎 Python-SocketIO 伺服器：完成 server/main.py 並從 eventlet 遷移至現代化 ASGI (Uvicorn) 架構。
  - [x] 定義核心同步協定：完成 `join_room` 與 `sync_game_data` 封包規格。
  - [x] 建立「房間管理記憶體結構」：實作 sid 追蹤與自動斷線清理邏輯。
- **前端 (Frontend)**：
  - [x] 設計大廳等待（LOBBY）、鬧鐘設定與房間輸入畫面的 Pygame UI 基礎線條與佈局。
  - [x] 建立 `SocketManager`：將測試指令封裝進類別，準備串接 Pygame 遊戲主迴圈。
- **系統層 (System)**：
  - [x] 引入 pywin32 調用邏輯（透過 ctypes 實作 Win32 API），防止電腦進入系統睡眠模式（Sleep Prevention）。

### Week 2: Core Awakening & Enforcement (核心喚醒與強制執行)
- **週目標**：鬧鐘在所有裝置上同時觸發，本地啟動最高強度防禦，確保使用者無法輕易繞過或關閉。
- **音效管理 (Audio)**：
    - [x] 實作 `SoundManager` 封裝音效邏輯，支援音量漸進式增強（Fade-in）與專屬頻道管理。
    - [x] 實作大廳音量測試按鈕與背景音樂 (BGM) 自動切換邏輯。
    - [x] 實作硬體偵測：當偵測到耳機而非喇叭時，在 Lobby 畫面顯示警告標語。
- **系統強化 (System Hardening)**：
    - [x] 使用 `SystemHelper` 調用 Win32 API 實作置頂視窗，鬧鐘響起時強制將視窗置頂並帶到前景。

### Week 3: Social Sync & Game Logic (社交同步與遊戲邏輯)
- **週目標**：實現核心的「連帶拉扯（Tethered）」感，讓每個人的即時進度實時影響整個團隊。
- **遊戲動態與交互 (Movement & Interaction)**：
  - [x] 實作 `VisualRegistry` 資源中心與 `EntityManager` 實體管理器，達成資源解耦。
  - [x] 實作 `TestEntity` 與 `Renderer` 支援 5x5 精靈圖自動切割與置中渲染，並通過 `sprite_test`。
  - [x] 實現使用 Win32 API `GetAsyncKeyState` 進行硬體級按鍵偵測，完全繞過輸入法 (IME) 干擾。
  - [ ] 製作遊戲角色及移動、待機動畫。
  - [ ] 實作碰撞箱等遊戲交互元素。
  - [x] 實現 WASD 對遊戲角色進行位移操控。
- **網路同步 (Sync)**：
  - [ ] 整合**推測航法（Dead Reckoning）**與線性插值（LERP），補償網路延遲，確保隊友角色的移動平滑、不抖動。
- **資料視覺化 (Monitor)**：
  - [ ] 實作伺服器數據監控面板（Visualizing server data），讓團隊能即時觀測四端連線的 Ping 值與房間狀態。
- **核心機制 (Mechanics)**：
  - [ ] 實作偵測隊友斷線，若斷線超過一分鐘則可以投降的機制。
  - [ ] 基於 `BaseGameInterface` 實作子遊戲（Game 1、Game 2 ...）的關卡邏輯與動態載入。
  - [ ] 製作噴漆、表情等社交元素。

### Week 4: Integration & Polishing (整合與打磨拋光)
- **週目標**：產出一款完整流暢、不可跳過且高度同步的多人聯動鬧鐘遊戲系統。
- **狀態機優化 (State Machine)**：
  - [ ] 微調與測試客戶端狀態機（Client State Machine），確保流程狀態無縫切換：`Setup (設定)` → `Alarm (鬧鐘響)` → `Game (遊戲中)` → `Success (通關成功) / Surrender (認輸懲罰)`。
  - [ ] 實作斷線容錯：若隊友超時未連線，系統動態調降難度，避免「賴床死結」。
- **壓力測試 (Stress Testing)**：
  - [ ] 進行 4 人同時在線並行測試，模擬高延遲與極端網路環境（Edge Cases），優化封包傳輸效率。
- **體驗精煉 (UX Refinement)**：
  - [ ] 導入最終視覺素材、通關/失敗動畫、以及鬧鐘關閉時的漸暗回饋（Feedback）。

  ## 共用遊戲介面 (Common Game Interface)
為了確保所有子遊戲（Mini-games）能夠被主程式動態載入、切換，所有遊戲必須繼承並實作相同的基礎介面類別 `BaseGameInterface`。AI 在撰寫新遊戲時必須嚴格遵守此結構：

```python
class BaseLogicInterface:
    def __init__(self, socket_client, player_id_list):
        """初始化遊戲邏輯，傳入 Socket 連線實例以及所有玩家 ID"""
        pass

    def on_enter(self, params: dict = None):
        """當進入此遊戲時執行，可用於初始化計時器或重置分數，避免重複實作 __init__"""
        self.is_active = True

    def on_exit(self):
        """當遊戲結束或切換時執行，用於停止音效、清除暫存資料"""
        self.is_active = False

    def handle_event(self, event_data: dict):
        """處理來自前端的輸入事件（例如鍵盤按鍵、滑鼠點擊等），這些事件會透過 Socket.IO 傳遞"""
        pass

    def update(self, dt):
        """更新遊戲邏輯與狀態（物理碰撞、計時器、網路同步位置）"""
        pass

    def get_render_data(self) -> dict:
        """
        回傳當前所有需要渲染的物件資訊（座標、方向、狀態、特效）。
        前端 JS 將根據此字典繪製 Canvas 內容。
        """
        return {}

    def is_cleared(self) -> bool:
        """回傳當前小遊戲是否已被 2~4 人合作通關"""
        return False

    def get_sync_data(self) -> dict:
        """打包當前遊戲需要透過 Socket 廣播給其他玩家的封包資料"""
        return {}

    def receive_sync_data(self, data: dict):
        """接收並即時更新來自其他玩家/伺服器的遊戲狀態資料"""
        pass

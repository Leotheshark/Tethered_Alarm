# Project Context: Tethered Alarm (Co-up Awakening)

## 程式碼生成規則
- **註解規則**：程式碼中要加上註解，讓每一步的目的清晰可見
- **生成程式碼前**：生成程式碼前一定要先看過整個專案的程式碼，並合理規劃資料夾及檔案路徑

##  專案目標與核心機制
- **核心概念**：一款網路連線、2~4人多人在線協作的解謎鬧鐘遊戲。
- **基本玩法**：所有玩家的鬧鐘會在約定的時間同時響起。玩家必須合作通關，才能關掉鬧鐘。

##  四週開發進度與微觀任務清單 (4-Week Micro-task Roadmap)

### Week 1: Foundation & Architecture (基礎建設與架構)
- **週目標**：建立穩定的網路連線，達成 4 個客戶端（Clients）與伺服器成功完成「握手連線（Handshake）」與房間綁定。
- **後端 (Backend)**：
  - [x] 實作基礎 Python-SocketIO 伺服器：完成 server/main.py 並從 eventlet 遷移至現代化 ASGI (Uvicorn) 架構。
  - [x] 定義核心同步協定：完成 `join_room` 與 `sync_game_data` 封包規格。
  - [x] 建立「房間管理記憶體結構」：實作 sid 追蹤與自動斷線清理邏輯。
- **前端 (Frontend)**：
  - [X] 設計大廳等待（LOBBY）、鬧鐘設定與房間輸入畫面的 Pygame UI 基礎線條與佈局。
  - [ ] 建立 `SocketManager`：將測試指令封裝進類別，準備串接 Pygame 遊戲主迴圈。
- **系統層 (System)**：
  - [x] 引入 pywin32 調用邏輯（透過 ctypes 實作 Win32 API），防止電腦進入系統睡眠模式（Sleep Prevention）。

### Week 2: Core Awakening & Enforcement (核心喚醒與強制執行)
- **週目標**：鬧鐘在所有裝置上同時觸發，本地啟動最高強度防禦，確保使用者無法輕易繞過或關閉。
- **音效管理 (Audio)**：
  - [ ] 標準化 `.ogg` 音效引擎（使用 `pygame.mixer`），確保全體玩家達到高音量、完全同步的警報播放。
- **系統強化 (System Hardening)**：
  - [ ] 開發「反任務殺手邏輯（Anti-Task-Kill logic）」：捕捉並阻擋 `pygame.QUIT` 事件，防止直接點 [X] 關閉。
  - [ ] 使用 Win32 API 實作 `SetForegroundWindow`，時間到時強制將遊戲視窗彈出至系統最上層並鎖定焦點。
- **遊戲動態 (Movement)**：
  - [ ] 在 Pygame 中初始化基礎遊戲環境地圖，實作鍵盤（WASD）控制並即時對應/映射玩家的二維座標。

### Week 3: Social Sync & Game Logic (社交同步與遊戲邏輯)
- **週目標**：實現核心的「連帶拉扯（Tethered）」感，讓每個人的即時進度實時影響整個團隊。
- **網路同步 (Sync)**：
  - [ ] 整合**推測航法（Dead Reckoning）**與線性插值（LERP），補償網路延遲，確保隊友角色的移動平滑、不抖動。
- **資料視覺化 (Monitor)**：
  - [ ] 實作伺服器數據監控面板（Visualizing server data），讓團隊能即時觀測四端連線的 Ping 值與房間狀態。
- **核心機制 (Mechanics)**：
  - [ ] 實作「死重懲罰（Dead Weight Penalty）」：偵測尚未起床移動的隊友，將其重力加倍或變成阻礙，拖慢全體通關速度。
  - [ ] 基於 `BaseGameInterface` 實作子遊戲（Game 1、Game 2 ...）的關卡邏輯與動態載入。

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
class BaseGameInterface:
    def __init__(self, screen, socket_client, player_id_list):
        """初始化遊戲，傳入 Pygame 畫布、Socket 連線實例以及所有玩家 ID"""
        pass

    def handle_event(self, event):
        """處理 Pygame 的視窗與輸入事件（鍵盤、滑鼠）"""
        pass

    def update(self, dt):
        """更新遊戲邏輯與狀態（物理碰撞、計時器、網路同步位置）"""
        pass

    def draw(self):
        """負責畫面渲染繪製"""
        pass

    def is_cleared(self) -> bool:
        """回傳當前小遊戲是否已被 2~4 人合作通關"""
        return False

    def get_sync_data(self) -> dict:
        """打包當前遊戲需要透過 Socket 廣播給其他玩家的封包資料"""
        return {}

    def receive_sync_data(self, data: dict):
        """接收並即時更新來自其他玩家/伺服器的遊戲狀態資料"""
        pass

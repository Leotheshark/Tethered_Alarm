"""
BaseLogicInterface：所有小遊戲的抽象基底類別。
所有遊戲必須實作全部 8 個方法，確保主引擎能動態載入與切換遊戲。
"""
import renderer


class BaseLogicInterface:
    """小遊戲的共用介面契約，定義主引擎呼叫的 8 個生命週期方法。"""

    def __init__(self, socket_client, player_id_list):
        """
        初始化遊戲邏輯。
        :param socket_client: GameNetwork 實例，供遊戲廣播封包使用。
        :param player_id_list: 房間內所有玩家 ID 的清單，順序即顏色順序。
        """
        self.socket_client = socket_client
        self.player_id_list = player_id_list
        self.is_active = False

        # 通關動畫狀態機
        self.clear_anim_stage = 0  # 0:None, 1:PrePause, 2:SlideIn, 3:ShowText, 4:SlideOut, 5:Finished
        self.clear_anim_timer = 0.0
        self.is_input_locked = False

        # 動畫階段長度定義 (秒)
        self.ANIM_TIME_PRE = renderer.CLEAR_PRE_PAUSE_TIME
        self.ANIM_TIME_IN = renderer.CLEAR_IN_TIME
        self.ANIM_TIME_TEXT = renderer.CLEAR_TEXT_TIME
        self.ANIM_TIME_OUT = renderer.CLEAR_OUT_TIME

    def on_enter(self, params: dict = None):
        """
        進入此遊戲時執行。
        可用於初始化計時器、重置分數、佈置初始棋盤狀態。
        避免在 __init__ 中重複做這些事，確保同一個實例可多次重用（例如重試）。
        """
        self.is_active = True
        self.clear_anim_stage = 0
        self.clear_anim_timer = 0.0
        self.is_input_locked = False

    def on_exit(self):
        """
        遊戲結束或切換至其他遊戲時執行。
        應停止音效、清除計時器、釋放暫存資料。
        """
        self.is_active = False

    def handle_event(self, event_data: dict):
        """
        處理來自玩家的輸入事件（鍵盤、滑鼠等）。
        這些事件由主引擎從 Pygame 事件佇列取得後傳入。
        :param event_data: 包含 'type'（事件類型）與附加資訊的字典。
        """
        pass

    def trigger_clear_sequence(self):
        """啟動通關動畫流程，由子類別在勝利時呼叫。"""
        if self.clear_anim_stage == 0:
            self.clear_anim_stage = 1
            self.clear_anim_timer = 0.0
            self.is_input_locked = True
            print("[BaseGame] Clear animation triggered.")

    def _update_clear_animation(self, dt: float):
        """更新動畫計時與階段切換。"""
        if self.clear_anim_stage == 0 or self.clear_anim_stage == 5:
            return

        self.clear_anim_timer += dt

        if self.clear_anim_stage == 1:  # Pre Pause
            if self.clear_anim_timer >= self.ANIM_TIME_PRE:
                self.clear_anim_stage = 2
                self.clear_anim_timer = 0.0
        elif self.clear_anim_stage == 2:  # Slide In
            if self.clear_anim_timer >= self.ANIM_TIME_IN:
                self.clear_anim_stage = 3
                self.clear_anim_timer = 0.0
        elif self.clear_anim_stage == 3:  # Show Text
            if self.clear_anim_timer >= self.ANIM_TIME_TEXT:
                self.clear_anim_stage = 4
                self.clear_anim_timer = 0.0
        elif self.clear_anim_stage == 4:  # Slide Out
            if self.clear_anim_timer >= self.ANIM_TIME_OUT:
                self.clear_anim_stage = 5
                self.clear_anim_timer = 0.0

    def _get_clear_anim_data(self) -> dict:
        """封裝動畫資料供渲染器使用。"""
        return {
            "stage": self.clear_anim_stage,
            "timer": self.clear_anim_timer
        }

    def update(self, dt: float):
        """
        每幀更新遊戲狀態：物理模擬、AI 行為、計時器、勝負判定。
        :param dt: 距上一幀的時間差（秒），用於幀率無關的運算。
        """
        pass

    def get_render_data(self) -> dict:
        """
        回傳渲染器需要的所有物件資訊（座標、方向、狀態、特效）。
        Renderer 根據此字典決定每幀要畫什麼，達成邏輯與渲染解耦。
        """
        return {}

    def is_cleared(self) -> bool:
        """
        回傳此小遊戲是否已被玩家合作通關。
        主引擎在每幀的 update 後呼叫此方法，若回傳 True 則切換至下一個流程。
        """
        return self.clear_anim_stage == 5

    def get_sync_data(self) -> dict:
        """
        打包需要透過 Socket.IO 廣播給其他玩家的遊戲狀態封包。
        主引擎在固定時間間隔呼叫，將回傳值送往伺服器再轉發給其他客戶端。
        """
        return {}

    def receive_sync_data(self, data: dict):
        """
        接收並套用來自其他玩家或伺服器的遊戲狀態同步資料。
        :param data: 由對端 get_sync_data 產生的封包字典。
        """
        pass

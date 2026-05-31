# 房間管理類別：負責儲存與管理單一房間內的玩家資訊
class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}       # 存放玩家的字典。結構為 { socket_id: 玩家資料 }
        self.alarm_time = None  # 鬧鐘設定的時間 (例如 "08:30")
        self.max_players = 4    # 房間上限
        self.host_sid = None    # 房長的 Socket ID (第一位進來的玩家)
        self.game_client_count = 0      # 已訂閱的 game_client 數量，用於依序指派顏色
        self.game_client_sids = {}      # { sid: color }，追蹤在線的 game_client
        self.is_triggered = False       # 鬧鐘是否已響起（處於準備階段）
        self.current_minigame = None    # 本局要載入的小遊戲名稱；start_game 時設定。
        self.minigame_dispatched = False  # 本局是否已對全房派發過 start_minigame（含權威名單）。
                                        # 待 4 個 game_client 都訂閱後才派發一次，避免名單殘缺或重複廣播。

    def add_player(self, sid):
        """嘗試將玩家加入房間"""
        if len(self.players) >= self.max_players:
            return False # 房間已滿
        
        # 根據加入順序固定分配顏色 (blue, green, pink, red)
        colors = ["blue", "green", "pink", "red"]
        assigned_color = colors[len(self.players)]
        self.players[sid] = {"ready": False, "color": assigned_color}

        # 如果房間目前沒人，該玩家自動成為房長
        if self.host_sid is None: self.host_sid = sid
        return True

    def remove_player(self, sid):
        """將玩家從房間移除"""
        if sid in self.players:
            self.players.pop(sid)
            # 重新分配顏色，實現「向左替補」邏輯
            colors = ["blue", "green", "pink", "red"]
            for i, p_sid in enumerate(self.players):
                self.players[p_sid]["color"] = colors[i]

    def reset_for_lobby(self):
        """遊戲結束後重置房間回大廳可重玩狀態：
        - 清掉鬧鐘時間（讓前端 isBusy 解除，房主能重新設鬧鐘）。
        - 所有玩家 ready 歸 False（回到等待 ready 的乾淨狀態）。
        - 清掉本局小遊戲標記與 game_client 訂閱（下一局重新湊滿、重新派發）。
        玩家本身（players/host_sid）保留，因為他們仍在大廳房間內。"""
        self.is_triggered = False
        self.alarm_time = None
        for p in self.players.values():
            p["ready"] = False
        self.current_minigame = None
        self.minigame_dispatched = False
        self.game_client_sids = {}
        self.game_client_count = 0

    def get_state(self):
        """整理並回傳目前房間的完整資訊，用於同步給所有客戶端"""
        return {
            "room_id": self.room_id,
            "players": self.players,
            "alarm_time": self.alarm_time,
            "count": len(self.players),
            "host_sid": self.host_sid,
            "is_triggered": self.is_triggered
        }
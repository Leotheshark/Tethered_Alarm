# 房間管理類別：負責儲存與管理單一房間內的玩家資訊
class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}       # 存放玩家的字典。結構為 { socket_id: 玩家資料 }
        self.alarm_time = None  # 鬧鐘設定的時間 (例如 "08:30")
        self.max_players = 4    # 房間上限
        self.host_sid = None    # 房長的 Socket ID (第一位進來的玩家)

    def add_player(self, sid, color):
        """嘗試將玩家加入房間"""
        if len(self.players) >= self.max_players:
            return False # 房間已滿
        self.players[sid] = {"color": color, "ready": False}
        # 如果房間目前沒人，該玩家自動成為房長
        if self.host_sid is None: self.host_sid = sid
        return True

    def remove_player(self, sid):
        """將玩家從房間移除"""
        self.players.pop(sid, None) # 刪除 sid 對應的資料，若不存在則忽略

    def get_state(self):
        """整理並回傳目前房間的完整資訊，用於同步給所有客戶端"""
        return {
            "room_id": self.room_id,
            "players": self.players,
            "alarm_time": self.alarm_time,
            "count": len(self.players),
            "host_sid": self.host_sid
        }
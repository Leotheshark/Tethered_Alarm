class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}       # socket_id -> player info
        self.alarm_time = None  # UTC Unix timestamp
        self.max_players = 4

    def add_player(self, sid, color):
        if len(self.players) >= self.max_players:
            return False
        self.players[sid] = {"color": color, "ready": False}
        return True

    def remove_player(self, sid):
        self.players.pop(sid, None)

    def get_state(self):
        return {
            "room_id": self.room_id,
            "players": self.players,
            "alarm_time": self.alarm_time,
            "count": len(self.players)
        }
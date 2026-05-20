"""
Game network client
負責讓 Pygame 遊戲進程和 server/main.py 的 Socket.IO 事件對接。

設計重點：
- lobby 的 4 位玩家仍由瀏覽器 UI 加入 join_room 管理。
- game_client 不是第 5 位玩家，只訂閱已滿員的房間。
- 當 server 廣播 alarm_triggered / game_started 時，這裡再轉交給 GameEngine 處理音效與視窗。
"""

import threading
import time
import socketio


class GameNetwork:
    """管理遊戲端與伺服器之間的即時同步。"""

    def __init__(self, engine, server_url="http://127.0.0.1:5000", room_id="default"):
        # engine 是 GameEngine；網路事件收到後會回呼 engine 的方法。
        self.engine = engine
        self.server_url = server_url
        self.room_id = room_id

        # 建立可自動重連的 Socket.IO client，避免 server 比 game_client 晚啟動時直接失敗。
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=10,
            reconnection_delay=1,
            reconnection_delay_max=5,
        )

        # --- Socket.IO 事件註冊 ---
        # connect/disconnect：維護連線狀態。
        # assign_room/game_room_subscribed：讓 game_client 綁定正確房間，但不佔玩家名額。
        # alarm_triggered/game_started：真正驅動鬧鐘聲與遊戲畫面的事件。
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.on("alarm_triggered", self._on_alarm_triggered)
        self.sio.on("game_started", self._on_game_started)
        self.sio.on("assign_room", self._on_assign_room)
        self.sio.on("game_room_subscribed", self._on_game_room_subscribed)

        # 網路連線放在背景執行緒，避免阻塞 Pygame 主迴圈。
        self.thread = threading.Thread(target=self._start, daemon=True)
        self.thread.start()

    def _start(self):
        """持續嘗試連線到 server；成功後交給 socketio.wait() 接收事件。"""
        while True:
            try:
                self.sio.connect(self.server_url, wait=True, wait_timeout=10)
                self.sio.wait()
            except Exception as e:
                print(f"[GameNetwork] connection error: {e}; retrying...")
                time.sleep(2)
                continue
            break

    def _on_connect(self):
        """連上 server 後，請求綁定目前可用的滿員房間。"""
        print("[GameNetwork] connected, SID:", self.sio.sid)
        try:
            # 若啟動時已由環境變數指定 ROOM_ID，直接訂閱該房間。
            if self.room_id != "default":
                self.sio.emit("subscribe_game_room", {"room_id": self.room_id})
                print(f"[GameNetwork] subscribing to configured room: {self.room_id}")

            # 若沒有指定房間，請 server 指派一個已滿員、等待鬧鐘流程的房間。
            self.sio.emit("request_game_room", {})
            print("[GameNetwork] requested an active game room")
        except Exception as e:
            print(f"[GameNetwork] room subscription error: {e}")

    def _on_disconnect(self):
        """連線中斷時只記錄狀態；socketio client 會依設定自動重連。"""
        print("[GameNetwork] disconnected")

    def _on_assign_room(self, data):
        """server 指派房間後，正式訂閱該 room 的廣播事件。"""
        room_id = data.get("room_id")
        print(f"[GameNetwork] received assign_room: {room_id}")
        if room_id:
            self.change_room(room_id)

    def _on_game_room_subscribed(self, data):
        """server 確認訂閱完成；同步本地 room_id 狀態。"""
        room_id = data.get("room_id")
        if room_id:
            self.room_id = room_id
        print(f"[GameNetwork] subscribed to game room: {room_id}")

    def change_room(self, room_id):
        """切換 game_client 目前監聽的房間。"""
        try:
            self.sio.emit("subscribe_game_room", {"room_id": room_id})
            self.room_id = room_id
            print(f"[GameNetwork] subscribing to game room: {room_id}")
        except Exception as e:
            print(f"[GameNetwork] change room error: {e}")

    def _on_alarm_triggered(self, data):
        """收到 server 的鬧鐘觸發訊號，交給 GameEngine 播放 alarm 並顯示遊戲視窗。"""
        print(f"[GameNetwork] received alarm_triggered: {data}")
        try:
            if hasattr(self.engine, "on_alarm_triggered"):
                self.engine.on_alarm_triggered(data)
            elif hasattr(self.engine, "trigger_alarm_sound"):
                self.engine.trigger_alarm_sound()
        except Exception as e:
            print(f"[GameNetwork] alarm callback error: {e}")

    def _on_game_started(self, data):
        """收到正式開始遊戲的訊號，交給 GameEngine 停止鬧鐘並進入遊戲畫面。"""
        print(f"[GameNetwork] received game_started: {data}")
        try:
            if hasattr(self.engine, "on_game_started"):
                self.engine.on_game_started(data)
            elif hasattr(self.engine, "sound_manager"):
                self.engine.sound_manager.stop(channel_name="alarm", fade_ms=500)
        except Exception as e:
            print(f"[GameNetwork] game_started callback error: {e}")

    def send_ready(self, is_ready=True):
        """保留給未來 Pygame 端直接送出 ready/unready 狀態時使用。"""
        try:
            event = "player_ready" if is_ready else "player_unready"
            self.sio.emit(event, {"room_id": self.room_id})
        except Exception as e:
            print(f"[GameNetwork] ready event error: {e}")

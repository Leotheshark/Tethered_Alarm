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

    def __init__(self, engine, server_url="http://127.0.0.1:5555", room_id="default", player_color="blue"):
        # engine 是 GameEngine；網路事件收到後會回呼 engine 的方法。
        self.engine = engine
        self.server_url = server_url
        self.room_id = room_id
        self.player_id = None    # 連線後由 socket SID 決定
        self.player_color = player_color # 從 Lobby 繼承而來的顏色
        # 是否為本局權威端（Pac-Man AI / 通關判定）。由 server 在 start_minigame 的 roster
        # 指定，engine 收到後寫入；小遊戲讀此值，不再各自用顏色硬猜。
        self.is_authority = False

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
        self.sio.on("player_move", self._on_player_move)
        self.sio.on("teammate_disconnected", self._on_teammate_disconnected)
        self.sio.on("teammate_timeout", self._on_teammate_timeout)
        self.sio.on("game_over", self._on_game_over)
        self.sio.on("start_minigame", self._on_start_minigame)
        self.sio.on("game_event", self._on_game_event)

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
        """連上 server 後，記錄自身 player_id 並請求綁定房間。"""
        self.player_id = self.sio.sid
        print("[GameNetwork] connected, SID:", self.sio.sid)
        # 通知 engine 清除「連線中斷」提示（涵蓋首次連線與自動重連成功）
        if hasattr(self.engine, "on_connection_changed"):
            self.engine.on_connection_changed(True)
        try:
            # 若啟動時已由環境變數指定 ROOM_ID（正式流程的常態），直接帶著大廳繼承的
            # 顏色訂閱該房間即可。此時「不」再發 request_game_room——否則 server 會回
            # assign_room 觸發 change_room 再訂閱一次，而那次沒帶顏色，導致 server 走
            # fallback 計數器重發顏色，造成同一 client 拿到兩個顏色、顏色錯亂。
            if self.room_id != "default":
                self.sio.emit("subscribe_game_room", {"room_id": self.room_id, "player_color": self.player_color})
                print(f"[GameNetwork] subscribing to configured room: {self.room_id}")
            else:
                # 沒指定房間（debug 直連）：請 server 指派一個已滿員、等待鬧鐘流程的房間。
                self.sio.emit("request_game_room", {})
                print("[GameNetwork] requested an active game room")
        except Exception as e:
            print(f"[GameNetwork] room subscription error: {e}")

    def _on_disconnect(self):
        """連線中斷時記錄狀態並通知 engine 顯示提示；socketio client 會依設定自動重連。"""
        print("[GameNetwork] disconnected")
        # 通知 engine 顯示「連線中斷」提示，讓玩家知道畫面停止同步是斷線而非當機
        if hasattr(self.engine, "on_connection_changed"):
            self.engine.on_connection_changed(False)

    def _on_assign_room(self, data):
        """server 指派房間後，正式訂閱該 room 的廣播事件。"""
        room_id = data.get("room_id")
        print(f"[GameNetwork] received assign_room: {room_id}")
        if room_id:
            self.change_room(room_id)

    def _on_game_room_subscribed(self, data):
        """server 確認訂閱完成；同步 room_id 與伺服器指派的角色顏色。"""
        room_id = data.get("room_id")
        if room_id:
            self.room_id = room_id
        color = data.get("player_color")
        if color:
            self.player_color = color
            if hasattr(self.engine, "on_color_assigned"):
                self.engine.on_color_assigned(color)
        print(f"[GameNetwork] subscribed to game room: {room_id}, color: {self.player_color}")

    def change_room(self, room_id):
        """切換 game_client 目前監聽的房間。"""
        try:
            # 一律帶上目前顏色：否則 server 收到無色訂閱會走計數器 fallback 重新指派，
            # 造成同一 client 拿到兩個顏色、座位與權威判定分歧。
            self.sio.emit("subscribe_game_room", {"room_id": room_id, "player_color": self.player_color})
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

    def send_position(self, x, y, dx, dy):
        """廣播本地玩家的當前位置與移動方向給同房其他人。"""
        # 未連線時直接略過：斷線後 Pygame 主迴圈仍每幀呼叫此方法，
        # 若硬送會對已斷的 namespace 不斷拋錯洗版 log。
        if not self.sio.connected or not self.player_id or not self.room_id:
            return
        try:
            self.sio.emit("player_move", {
                "room_id": self.room_id,
                "player_id": self.player_id,
                "color": self.player_color,
                "x": x, "y": y, "dx": dx, "dy": dy,
            })
        except Exception as e:
            print(f"[GameNetwork] send_position error: {e}")

    def _on_player_move(self, data):
        """收到其他玩家的位置封包，轉交給 GameEngine 更新遠端角色。"""
        if hasattr(self.engine, "on_player_moved"):
            self.engine.on_player_moved(data)

    def _on_teammate_disconnected(self, data):
        if hasattr(self.engine, "on_teammate_disconnected"):
            self.engine.on_teammate_disconnected(data)

    def _on_teammate_timeout(self, data):
        if hasattr(self.engine, "on_teammate_timeout"):
            self.engine.on_teammate_timeout(data)

    def _on_game_over(self, data):
        if hasattr(self.engine, "on_game_over"):
            self.engine.on_game_over(data)

    def _on_start_minigame(self, data):
        """伺服器通知要載入哪個小遊戲（背景執行緒）。"""
        if hasattr(self.engine, "on_start_minigame"):
            self.engine.on_start_minigame(data)

    def _on_game_event(self, data):
        """接收同房其他客戶端廣播的小遊戲即時事件（背景執行緒）。"""
        if hasattr(self.engine, "on_game_event"):
            self.engine.on_game_event(data)

    def send_game_event(self, payload: dict):
        """廣播小遊戲內的即時事件封包給同房其他人。"""
        # 未連線時略過，理由同 send_position（避免斷線後洗版式拋錯）。
        if not self.sio.connected or not self.room_id:
            return
        try:
            self.sio.emit("game_event", {**payload, "room_id": self.room_id})
        except Exception as e:
            print(f"[GameNetwork] send_game_event error: {e}")

    def send_surrender(self):
        """發送投降事件給伺服器。"""
        if not self.sio.connected:
            return
        try:
            self.sio.emit("surrender", {"room_id": self.room_id})
        except Exception as e:
            print(f"[GameNetwork] send_surrender error: {e}")

    def send_ready(self, is_ready=True):
        """保留給未來 Pygame 端直接送出 ready/unready 狀態時使用。"""
        if not self.sio.connected:
            return
        try:
            event = "player_ready" if is_ready else "player_unready"
            self.sio.emit(event, {"room_id": self.room_id})
        except Exception as e:
            print(f"[GameNetwork] ready event error: {e}")

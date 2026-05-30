"""
Game Engine Core
負責處理每秒 60 幀的遊戲循環
"""
import pygame
import os
import sys
import time
from input_handler import InputHandler
from states import StateMachine
from renderer import Renderer
from entities import Ghost, RemoteGhost
from visual_registry import VisualRegistry
from entity_manager import EntityManager
from sound_manager import SoundManager
from network import GameNetwork

# 小遊戲模組：自動掃描 games/ 資料夾，載入所有繼承 BaseLogicInterface 的類別。
# 組員只需在 games/ 新增一個模組，引擎就能自動發現，不需要修改此檔案。
import importlib
import pkgutil
import inspect
from games.base_game import BaseLogicInterface

_MINIGAME_CLASSES: dict[str, type] = {}

_games_pkg_path = os.path.join(os.path.dirname(__file__), "games")
for _finder, _module_name, _ispkg in pkgutil.iter_modules([_games_pkg_path]):
    if _module_name.startswith("_"):
        continue  # 跳過 __init__ 等私有模組
    try:
        _mod = importlib.import_module(f"games.{_module_name}")
        for _name, _cls in inspect.getmembers(_mod, inspect.isclass):
            if issubclass(_cls, BaseLogicInterface) and _cls is not BaseLogicInterface:
                # 以模組名稱（snake_case）作為遊戲 key，對應 server 廣播的 "game" 欄位
                _MINIGAME_CLASSES[_module_name] = _cls
                print(f"[Engine] registered minigame: {_module_name} -> {_cls.__name__}")
    except Exception as _e:
        print(f"[Engine] failed to load games.{_module_name}: {_e}")

class GameEngine:
    def __init__(self):
        # 0. 解決 Windows 高 DPI 縮放問題，確保 1920x1080 視窗不會被系統自動放大
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        # 1. 僅初始化音訊與基礎模組，暫不啟動顯示模組
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()

        self.clock = pygame.time.Clock()
        self.screen = None  # 初始狀態沒有視窗

        # 2. 實例化各個模組組件
        self.input_handler = InputHandler()
        self.entity_manager = EntityManager()
        self.state_machine = StateMachine()

        # 2.6. 建立音效管理器，負責統一載入、頻道、音量與淡入行為
        self.sound_manager = SoundManager()
        self.sound_manager.load_sound("alarm", "Alarm_1.ogg", volume=0.5)
        self.sound_manager.load_sound("bgm", "bgm_loop.ogg", volume=0.5)
        self.sound_manager.set_master_volume(0.5)

        self.renderer = None  # 視窗建立後才初始化渲染器
        self.network = None   # 關鍵修正：先定義屬性為 None，防止背景執行緒回呼時噴出 AttributeError
        self.game_window_shown = False
        
        # Socket.IO 回呼在背景執行緒觸發，用旗標讓主迴圈在主執行緒安全執行 Pygame 操作
        self._pending_show_window = False
        self._pending_stop_alarm = False
        self._pending_play_alarm = False
        self._pending_remote_updates = []  # 遠端位置封包佇列（背景執行緒寫入，主迴圈消費）
        self._pending_caption_update = False # 標題更新旗標，確保執行緒安全

        # 優先讀取環境變數中的顏色（由 Lobby 傳入），否則預設藍色
        initial_color = os.environ.get('PLAYER_COLOR', 'blue')

        # 遠端玩家管理
        self.remote_ghosts = {}   # { player_id: RemoteGhost }
        self._sync_timer = 0.0    # 位置廣播計時器
        self._SYNC_INTERVAL = 0.05  # 每 50ms 廣播一次（20fps）

        # 斷線與投降狀態
        self._disconnected_colors = set()  # 目前斷線的隊友顏色
        self._show_surrender_ui = False    # 是否顯示投降按鈕
        self._game_over = False
        self._pending_teammate_events = [] # 來自背景執行緒的斷線事件佇列

        # 小遊戲狀態
        self.active_game = None            # 目前正在運行的 BaseLogicInterface 實例
        self._pending_minigame = None      # 背景執行緒設定的待啟動遊戲名稱
        self._pending_game_events = []     # 來自背景執行緒的小遊戲事件佇列
        self._game_sync_timer = 0.0        # 玩家位置同步至小遊戲的計時器
        self._GAME_SYNC_INTERVAL = 0.05    # 每 50ms 廣播一次小遊戲玩家位置

        # 處理強制啟動邏輯：解決大廳啟動遊戲時錯過 game_started 事件的問題
        if os.environ.get('DEBUG_MODE') == '1' or os.environ.get('FORCE_START') == '1':
            print("[Engine] 啟動即進入遊戲視窗")
            self._pending_show_window = True

        # DEBUG_MINIGAME=1：跳過 server 廣播，等湊滿人數後啟動指定的小遊戲
        self._debug_minigame_pending = os.environ.get('DEBUG_MINIGAME') == '1'
        self._debug_minigame_name = os.environ.get('DEBUG_MINIGAME_NAME', 'dodge_knives')
        self._debug_required_players = int(os.environ.get('DEBUG_PLAYERS', '1'))
        self._debug_wait_log_timer = 0.0
        if self._debug_minigame_pending:
            print(f"[Engine] DEBUG_MINIGAME: 等湊滿 {self._debug_required_players} 人後啟動 {self._debug_minigame_name}")

        # 2.7. 建立網路客戶端，連接到伺服器並監聽 alarm/game 事件
        # room id 可由環境變數 ROOM_ID 覆蓋，否則使用預設 "default"
        room_id = os.environ.get('ROOM_ID', 'default')
        self.network = GameNetwork(self, server_url=os.environ.get('SERVER_URL', 'http://127.0.0.1:5555'), room_id=room_id, player_color=initial_color)

        # 3. 建立玩家角色
        self.player = Ghost(initial_color)
        self.entity_manager.add(self.player)

    def on_color_assigned(self, color):
        """伺服器指派顏色後，更新本地玩家角色的顏色。"""
        self.player.color_key = color
        self.player.visual_key = f"{color}_{self.player.direction}"
        print(f"[Engine] player color assigned: {color}")
        # 僅設定旗標，由主執行緒在 _flush_pending 中更新 UI，防止背景執行緒操作 Pygame 導致崩潰
        self._pending_caption_update = True

    def on_player_moved(self, data):
        """由 GameNetwork 回呼（背景執行緒）：將遠端封包放入佇列，交主迴圈處理。"""
        self._pending_remote_updates.append(data)

    def on_teammate_disconnected(self, data):
        """隊友斷線通知（背景執行緒）。"""
        self._pending_teammate_events.append(("disconnected", data))

    def on_teammate_timeout(self, data):
        """隊友斷線超過 60 秒，可投降（背景執行緒）。"""
        self._pending_teammate_events.append(("timeout", data))

    def on_game_over(self, data):
        """遊戲結束（背景執行緒）。"""
        self._pending_teammate_events.append(("game_over", data))

    def on_start_minigame(self, data):
        """伺服器通知要載入哪個小遊戲（背景執行緒）。"""
        self._pending_minigame = data.get("game")
        game_name = data.get("game")
        print(f"[Debug] 收到小遊戲啟動通知: {game_name}")
        self._pending_minigame = game_name

    def on_game_event(self, data):
        """接收小遊戲即時事件（背景執行緒）。"""
        self._pending_game_events.append(data)

    def on_alarm_triggered(self, data):
        """由 GameNetwork 回呼（背景執行緒）：設旗標，讓主迴圈播放鬧鐘聲（不開視窗）。"""
        print(f"[Engine] on_alarm_triggered: {data}")
        self._pending_play_alarm = True

    def on_game_started(self, data):
        """由 GameNetwork 回呼（背景執行緒）：設旗標，讓主迴圈停止鬧鐘並進入遊戲畫面。"""
        print(f"[Engine] on_game_started: {data}")
        self._pending_stop_alarm = True
        self._pending_show_window = True

    def show_game_window(self):
        """建立 Pygame 視窗，必須在主執行緒呼叫。"""
        if self.game_window_shown:
            return

        print("[Engine] 正在建立遊戲視窗...")
        # DEBUG_WINDOWED=1：以視窗模式建立，方便同時開多個 client 排列在螢幕上
        if os.environ.get('DEBUG_WINDOWED') == '1':
            # 解析度提升至 1920x1080
            self.screen = pygame.display.set_mode((1920, 1080), pygame.SCALED)
            # 視窗建立後再移動到指定位置（由 DEBUG_WINDOW_POS=x,y 指定）
            pos = os.environ.get('DEBUG_WINDOW_POS')
            if pos:
                try:
                    x, y = (int(v) for v in pos.split(','))
                    from ctypes import windll
                    hwnd = pygame.display.get_wm_info()['window']
                    windll.user32.MoveWindow(hwnd, x, y, 1920, 1080, True)
                except Exception as _e:
                    print(f"[Engine] DEBUG_WINDOW_POS 失敗：{_e}")
        else:
            self.screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN | pygame.SCALED)
        caption = os.environ.get('DEBUG_TITLE', 'Co-up: Tethered Alarm')
        # 若已指派顏色則顯示在標題
        if self.network and self.network.player_color: # 增加安全檢查，確保 network 已實例化
            caption = f"{caption} (Init: {self.network.player_color})"
        pygame.display.set_caption(caption)
        self.renderer = Renderer(self.screen)
        self.game_window_shown = True

        # 批次載入玩家精靈圖 (現在視窗已開啟，可以安全地執行 convert_alpha)
        _colors = ["blue", "red", "pink", "green"]
        _states = ["left", "right", "frontback", "idle"]
        for c in _colors:
            for s in _states:
                VisualRegistry.load_image(f"{c}_{s}", f"{c}_{s}.png")
        VisualRegistry.load_image("dead", "dead.png")

    def _build_ordered_player_id_list(self):
        """所有 client 對 player_id_list 達成共識：按 server 指派的顏色順序排序，
        缺顏色的（還沒收到 game_room_subscribed）排在最後並依 sid 排序。"""
        color_order = {"blue": 0, "green": 1, "pink": 2, "red": 3}
        entries = []
        # 本地玩家
        if self.network.player_id:
            entries.append((self.player.color_key, self.network.player_id))
        else:
            print("[Debug] 建立名單失敗: network.player_id 為空")
        # 遠端玩家
        for pid, ghost in self.remote_ghosts.items():
            entries.append((ghost.color_key, pid))

        def sort_key(item):
            color, pid = item
            rank = color_order.get(color, 99)
            return (rank, pid or "")

        entries.sort(key=sort_key)
        return [pid for _color, pid in entries]

    def _flush_pending(self):
        """在主迴圈中處理來自背景執行緒的旗標請求。"""
        # DEBUG_MINIGAME：輪詢人數，湊滿才設旗標進入小遊戲
        if self._debug_minigame_pending and self.game_window_shown:
            present = len(self.remote_ghosts) + 1
            if present >= self._debug_required_players:
                print(f"[Engine] DEBUG_MINIGAME: 人數已達 {present}/{self._debug_required_players}，啟動 {self._debug_minigame_name}")
                self._pending_minigame = self._debug_minigame_name
                self._debug_minigame_pending = False
            else:
                self._debug_wait_log_timer += 1
                if self._debug_wait_log_timer >= 60:  # 約每秒印一次（主迴圈 60fps）
                    self._debug_wait_log_timer = 0
                    print(f"[Engine] DEBUG_MINIGAME 等待玩家 ({present}/{self._debug_required_players})...")

        if self._pending_play_alarm:
            self._pending_play_alarm = False
            self.sound_manager.set_master_volume(0.5)
            self.sound_manager.play_alarm(fade_ms=10000)

        if self._pending_show_window:
            self._pending_show_window = False
            self.show_game_window()

        if self._pending_stop_alarm:
            self._pending_stop_alarm = False
            self.sound_manager.stop(channel_name='alarm', fade_ms=500)

        # 消費標題更新請求 (執行緒安全更新)
        if self._pending_caption_update and self.game_window_shown:
            self._pending_caption_update = False
            base_title = os.environ.get('DEBUG_TITLE', 'Player')
            color = self.network.player_color if self.network else "unknown"
            pygame.display.set_caption(f"{base_title} (Assigned: {color})")

        # 消費斷線事件佇列
        while self._pending_teammate_events:
            event_type, data = self._pending_teammate_events.pop(0)
            color = data.get("color")
            player_id = data.get("player_id")

            if event_type == "disconnected":
                self._disconnected_colors.add(color)
                # 將對應的 RemoteGhost 標記為斷線（灰化）
                for ghost in self.remote_ghosts.values():
                    if ghost.color_key == color:
                        ghost.disconnected = True
                print(f"[Engine] teammate disconnected: {color}")

            elif event_type == "timeout":
                self._show_surrender_ui = True
                print(f"[Engine] teammate timeout: {color}, surrender available")

            elif event_type == "game_over":
                self._game_over = True
                print(f"[Engine] game over: {data.get('reason')}")

        # 消費小遊戲啟動請求：在主執行緒安全地實例化並啟動遊戲
        if self._pending_minigame:
            game_name = self._pending_minigame
            # 若尚未取得伺服器分配的顏色，延後啟動，防止 is_authority 判定錯誤
            if self.network.player_color is None:
                print(f"[Engine] 等待顏色指派中，暫緩啟動 {game_name}...")
                return

            self._pending_minigame = None
            game_cls = _MINIGAME_CLASSES.get(game_name)
            if game_cls:
                # 所有 client 必須產出相同順序的 player_id_list，否則顏色分配與 authority 會分歧
                player_id_list = self._build_ordered_player_id_list()
                print(f"[Engine] minigame player_id_list: {player_id_list}")
                self.active_game = game_cls(self.network, player_id_list)
                self.active_game.on_enter()
                print(f"[Engine] minigame started: {game_name}")
            else:
                print(f"[Engine] unknown minigame: {game_name}")

        # 消費小遊戲事件佇列：轉發給活躍的小遊戲實例
        while self._pending_game_events:
            event = self._pending_game_events.pop(0)
            if self.active_game:
                self.active_game.receive_sync_data(event)

        # 消費遠端位置佇列：新增或更新 RemoteGhost
        while self._pending_remote_updates:
            data = self._pending_remote_updates.pop(0)
            pid = data.get("player_id")
            if not pid or pid == self.network.player_id:
                continue  # 忽略自己的封包（理論上 server 已 skip_sid，雙重保險）
            if pid not in self.remote_ghosts:
                color = data.get("color", "green")
                ghost = RemoteGhost(pid, color)
                self.remote_ghosts[pid] = ghost
                self.entity_manager.add(ghost)
            self.remote_ghosts[pid].apply_server_update(
                data["x"], data["y"], data["dx"], data["dy"]
            )

    def run(self):
        """啟動遊戲主迴圈"""
        running = True
        while running:
            # 每次迴圈都先處理旗標，確保視窗在主執行緒建立
            self._flush_pending()

            if not self.game_window_shown:
                # 視窗尚未建立時，保持低頻率運作，監聽網路事件即可
                time.sleep(0.1)
                continue

            # 視窗已建立，開始正常的 60 FPS 渲染循環
            dt = self.clock.tick(60) / 1000.0

            if self._game_over:
                running = False

            # A. 處理輸入與事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    # F11：切換全螢幕
                    if event.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                    if event.key == pygame.K_s and self._show_surrender_ui:
                        self.network.send_surrender()

            # E 鍵改用 GetAsyncKeyState 邊緣偵測，與 WASD 一致，避免多視窗 / IME 攔截造成 KEYDOWN 漏接
            rescue_edge = self.input_handler.poll_rescue_edge()
            if rescue_edge and self.active_game:
                if rescue_edge == "press":
                    self.active_game.handle_event({"type": "rescue_start"})
                elif rescue_edge == "release":
                    self.active_game.handle_event({"type": "rescue_stop"})

            dx, dy = self.input_handler.get_movement_input()

            # B. 處理邏輯
            if self.active_game:
                # 小遊戲運行中：將輸入傳給遊戲邏輯，玩家移動由遊戲管理
                self.active_game.handle_event({"type": "move", "dx": dx, "dy": dy})
                self.active_game.update(dt)

                # 定期廣播本地玩家在小遊戲中的位置（讓隊友看到自己）
                self._game_sync_timer += dt
                if self._game_sync_timer >= self._GAME_SYNC_INTERVAL:
                    self._game_sync_timer = 0.0
                    sync_data = self.active_game.get_sync_data()
                    if sync_data:
                        try:
                            self.network.send_game_event(sync_data)
                        except Exception:
                            pass

                # 通關判定
                if self.active_game.is_cleared():
                    self.active_game.on_exit()
                    self.active_game = None
                    print("[Engine] minigame cleared!")
                    # 廣播通關訊息給伺服器，讓大廳視窗恢復
                    self.network.sio.emit("game_cleared", {"room_id": self.network.room_id})
            else:
                # 遊戲大廳/等待模式：使用一般角色移動
                # 大廳中收集所有遠端玩家的 rect
                other_rects = [g.rect for g in self.remote_ghosts.values() if not g.disconnected]
                self.player.move(dx, dy, dt, others=other_rects)
                self.entity_manager.update_all(dt)

            # 定期廣播基礎位置 (Presence Heartbeat)
            # 即使在小遊戲中也要發送，讓後進的 Debug Client 能看見所有人並啟動遊戲
            self._sync_timer += dt
            if self._sync_timer >= self._SYNC_INTERVAL:
                self._sync_timer = 0.0
                # 優先使用小遊戲中的實際座標，否則使用大廳座標
                send_x, send_y = self.player.x, self.player.y
                send_dx, send_dy = self.player.current_dx, self.player.current_dy

                if self.active_game:
                    # 若在小遊戲中，同步小遊戲內的實際座標與當前輸入
                    send_dx, send_dy = float(dx), float(dy)
                    lp = self.active_game.players.get(self.active_game.local_color)
                    if lp: send_x, send_y = lp.x, lp.y
                
                self.network.send_position(send_x, send_y, send_dx, send_dy)

            # C. 處理渲染
            self.renderer.clear()
            if self.active_game:
                # 小遊戲模式：繪製遊戲世界（地圖、玩家、Pac-Man 等）
                render_data = self.active_game.get_render_data()
                self.renderer.draw_game(render_data, self.active_game.local_color)
            else:
                # 一般模式：繪製角色實體
                self.renderer.draw_world(self.entity_manager)
            self.renderer.draw_ui(self.clock)
            self.renderer.draw_status_ui(self._disconnected_colors, self._show_surrender_ui)
            self.renderer.display()

        pygame.quit()

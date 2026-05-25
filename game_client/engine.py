"""
Game Engine Core
負責處理每秒 60 幀的遊戲循環
"""
import pygame
import os
import sys
import time
import ctypes
from input_handler import InputHandler
from states import StateMachine
from renderer import Renderer
from entities import Ghost, RemoteGhost
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

# 將 server 目錄加入搜尋路徑，以便匯入 SystemHelper
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if server_dir not in sys.path:
    sys.path.append(server_dir)

from system_helper import SystemHelper  # type: ignore

class GameEngine:
    def __init__(self):
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
        self.game_window_shown = False

        # Socket.IO 回呼在背景執行緒觸發，用旗標讓主迴圈在主執行緒安全執行 Pygame 操作
        self._pending_show_window = False
        self._pending_stop_alarm = False
        self._pending_play_alarm = False
        self._pending_remote_updates = []  # 遠端位置封包佇列（背景執行緒寫入，主迴圈消費）

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

        # DEBUG_MODE=1：跳過大廳流程，直接開啟遊戲視窗，方便單人測試
        if os.environ.get('DEBUG_MODE') == '1':
            print("[Engine] DEBUG_MODE: 跳過大廳，直接開啟遊戲視窗")
            self._pending_show_window = True

        # DEBUG_MINIGAME=1：視窗開啟後立即載入 reverse_pacman，不等伺服器廣播
        if os.environ.get('DEBUG_MINIGAME') == '1':
            print("[Engine] DEBUG_MINIGAME: 直接載入 reverse_pacman")
            self._pending_minigame = "reverse_pacman"

        # 2.7. 建立網路客戶端，連接到伺服器並監聽 alarm/game 事件
        # room id 可由環境變數 ROOM_ID 覆蓋，否則使用預設 "default"
        room_id = os.environ.get('ROOM_ID', 'default')
        self.network = GameNetwork(self, server_url=os.environ.get('SERVER_URL', 'http://127.0.0.1:5000'), room_id=room_id)

        # 3. 建立玩家角色
        self.player = Ghost("blue")
        self.entity_manager.add(self.player)

    def on_color_assigned(self, color):
        """伺服器指派顏色後，更新本地玩家角色的顏色。"""
        self.player.color_key = color
        self.player.visual_key = f"ghost_{color}_idle"
        print(f"[Engine] player color assigned: {color}")

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
        self.screen = pygame.display.set_mode((1280, 720), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("Co-up: Tethered Alarm")
        self.renderer = Renderer(self.screen)
        self.game_window_shown = True

    def _flush_pending(self):
        """在主迴圈中處理來自背景執行緒的旗標請求。"""
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
            self._pending_minigame = None
            game_cls = _MINIGAME_CLASSES.get(game_name)
            if game_cls:
                # 以房間內所有玩家 ID 的清單初始化小遊戲
                player_id_list = list(self.remote_ghosts.keys())
                player_id_list.insert(0, self.network.player_id)  # 本地玩家排第一
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
                    if event.key == pygame.K_s and self._show_surrender_ui:
                        self.network.send_surrender()
                    # E 鍵：開始救援隊友（小遊戲進行中時有效）
                    elif event.key == pygame.K_e and self.active_game:
                        self.active_game.handle_event({"type": "rescue_start"})
                elif event.type == pygame.KEYUP:
                    # 放開 E 鍵：取消救援
                    if event.key == pygame.K_e and self.active_game:
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
                    # TODO: 廣播通關訊息，回到大廳流程
            else:
                # 遊戲大廳/等待模式：使用一般角色移動
                self.player.move(dx, dy, dt)
                self.entity_manager.update_all(dt)

                # 每 50ms 廣播一次本地玩家位置
                self._sync_timer += dt
                if self._sync_timer >= self._SYNC_INTERVAL:
                    self._sync_timer = 0.0
                    self.network.send_position(
                        self.player.x, self.player.y,
                        self.player.current_dx, self.player.current_dy,
                    )

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

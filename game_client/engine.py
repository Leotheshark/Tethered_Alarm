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
from entities import Ghost, EntityManager
from sound_manager import SoundManager
from network import GameNetwork

# 將 server 目錄加入搜尋路徑，以便匯入 SystemHelper
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if server_dir not in sys.path:
    sys.path.append(server_dir)

from system_helper import SystemHelper

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

        self.renderer = None # 視窗建立後才初始化渲染器
        self.game_window_shown = False

        # 2.7. 建立網路客戶端，連接到伺服器並監聽 alarm/game 事件
        # room id 可由環境變數 ROOM_ID 覆蓋，否則使用預設 "default"
        room_id = os.environ.get('ROOM_ID', 'default')
        self.network = GameNetwork(self, server_url=os.environ.get('SERVER_URL', 'http://127.0.0.1:5000'), room_id=room_id)

        # 3. 建立玩家角色
        self.player = Ghost("blue")
        self.entity_manager.add(self.player)

    def trigger_alarm_sound(self):
        """當鬧鐘事件到達時，由外部呼叫此方法播放鬧鐘音效。"""
        # 設定遊戲內部主音量為最大 (100% of current system volume)
        self.sound_manager.set_master_volume(0.5)

        # 使用 alarm 頻道漸入播放，loops=-1 表示無限循環直到停止
        # 鬧鐘響起時，立刻顯示視窗讓使用者有感
        self.show_game_window()
        self.sound_manager.play_alarm(fade_ms=10000)

    def on_alarm_triggered(self, data):
        """由 GameNetwork 回呼：處理伺服器發來的 alarm_triggered 事件。

        預期行為：將音量限制為 50%，以漸入方式在 alarm 頻道播放 Alarm_1。
        如果未載入音效，會顯示錯誤訊息。
        """
        print(f"[Engine] on_alarm_triggered: {data}")
        try:
            # 嘗試以更保守方式觸發鬧鐘
            self.trigger_alarm_sound()
        except Exception as e:
            print(f"[Engine] 觸發鬧鐘失敗: {e}")

    def show_game_window(self):
        """在接收到 game_started 後，將隱藏畫面切換成正式遊戲畫面。"""
        if self.game_window_shown:
            return

        print("[Engine] 鬧鐘觸發，正在建立遊戲視窗...")
        self.screen = pygame.display.set_mode((1280, 720))
        pygame.display.set_caption("Co-up: Tethered Alarm")
        
        # 初始化或更新渲染器
        self.renderer = Renderer(self.screen)
        self.game_window_shown = True

    def on_game_started(self, data):
        """由 GameNetwork 回呼：處理伺服器發來的 game_started 事件。

        預期行為：停止 alarm 頻道的播放（淡出），並在此時顯示遊戲畫面。
        """
        print(f"[Engine] on_game_started: {data}")
        try:
            self.sound_manager.stop(channel_name='alarm', fade_ms=500)
            self.show_game_window()
        except Exception as e:
            print(f"[Engine] 停止鬧鐘失敗: {e}")

    def run(self):
        """啟動遊戲主迴圈"""
        running = True
        while running:
            if not self.game_window_shown:
                # 視窗尚未建立時，保持低頻率運作，監聽網路事件即可
                time.sleep(0.1)
            else:
                # 視窗已建立，開始正常的 60 FPS 渲染循環
                dt = self.clock.tick(60) / 1000.0

                # A. 處理輸入與事件
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                
                dx, dy = self.input_handler.get_movement_input()

                # B. 處理邏輯
                if dx != 0 or dy != 0:
                    self.player.move(dx, dy, dt)
                self.entity_manager.update_all(dt)

                # C. 處理渲染
                if self.renderer:
                    self.renderer.clear()
                    self.renderer.draw_world(self.entity_manager)
                    self.renderer.draw_ui(self.clock)
                    self.renderer.display()

        pygame.quit()

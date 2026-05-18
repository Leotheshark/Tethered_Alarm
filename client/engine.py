"""
Game Engine Core
負責處理每秒 60 幀的遊戲循環
"""
import pygame
from input_handler import InputHandler
from states import StateMachine
from renderer import Renderer
from entities import Ghost, EntityManager

class GameEngine:
    def __init__(self):
        # 1. 初始化 Pygame 基礎引擎
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 720))
        pygame.display.set_caption("Co-up: Tethered Alarm")
        self.clock = pygame.time.Clock()

        # 2. 實例化各個模組組件
        self.input_handler = InputHandler()
        self.renderer = Renderer(self.screen)
        self.entity_manager = EntityManager()
        self.state_machine = StateMachine()

        # 3. 建立玩家角色
        self.player = Ghost("blue")
        self.entity_manager.add(self.player)

    def run(self):
        """啟動遊戲主迴圈"""
        running = True
        while running:
            # 計算時差 (dt)
            dt = self.clock.tick(60) / 1000.0

            # A. 處理輸入與事件
            # 獲取事件列表，處理 QUIT 事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            dx, dy = self.input_handler.get_movement_input()

            # B. 處理邏輯
            if dx != 0 or dy != 0:
                self.player.move(dx, dy, dt)
            self.entity_manager.update_all(dt)

            # C. 處理渲染
            self.renderer.clear()
            self.renderer.draw_world(self.entity_manager)
            self.renderer.draw_ui(self.clock)
            self.renderer.display()

        pygame.quit()

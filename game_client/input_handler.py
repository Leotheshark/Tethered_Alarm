# --- 輸入處理模組 ---
import pygame
import sys

class InputHandler:
    def handle_events(self):
        """監聽系統事件 (如關閉視窗)"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

    def get_movement_input(self):
        """偵測 WASD 按鍵並回傳移動向量 (dx, dy)"""
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0
        
        if keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_s]: dy += 1
        if keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_d]: dx += 1
        
        return dx, dy

# --- 渲染模組 ---
import pygame

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont(None, 24) # 初始化字體

    def clear(self):
        """用深藍色背景清空畫面"""
        self.screen.fill((20, 20, 30))

    def draw_ui(self, clock):
        """繪製介面資訊 (如 FPS)"""
        fps = int(clock.get_fps())
        fps_text = self.font.render(f"FPS: {fps}", True, (180, 180, 180))
        self.screen.blit(fps_text, (10, 10))

    def draw_world(self, entity_manager):
        """繪製所有遊戲世界的物體"""
        entity_manager.draw_all(self.screen)

    def display(self):
        """將繪製內容更新到螢幕上"""
        pygame.display.flip()
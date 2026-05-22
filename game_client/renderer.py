# --- 渲染模組 ---
import pygame
from visual_registry import VisualRegistry

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
        # 取得所有實體並根據 Y 座標排序 (簡單的遮擋處理：下方的物體擋住上方的物體)
        sorted_entities = sorted(entity_manager.entities, key=lambda e: e.y)

        for entity in sorted_entities:
            if not entity.active:
                continue

            surface = VisualRegistry.get_surface(entity.visual_key)
            if surface:
                # 處理 5x5 精靈圖切割 (如果實體定義了 frame_index)
                area = None
                if hasattr(entity, 'get_sprite_rect'):
                    area = entity.get_sprite_rect(surface)
                    # 計算中心偏移：使用切割後的 Rect 寬高
                    draw_x = entity.x - area.width // 2
                    draw_y = entity.y - area.height // 2
                else:
                    # 如果是普通圖片，使用整張圖的寬高置中
                    draw_x = entity.x - surface.get_width() // 2
                    draw_y = entity.y - surface.get_height() // 2
                
                # 執行繪製
                self.screen.blit(surface, (draw_x, draw_y), area)
            else:
                # 如果找不到資源，畫一個置中的佔位方塊
                size = 32
                pygame.draw.rect(
                    self.screen, 
                    (255, 0, 255), 
                    (entity.x - size // 2, entity.y - size // 2, size, size)
                )

    def display(self):
        """將繪製內容更新到螢幕上"""
        pygame.display.flip()
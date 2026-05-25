import sys
import os
import pygame

# 確保測試腳本能正確匯入 game_client 內的模組
client_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "game_client"))
if client_dir not in sys.path:
    sys.path.append(client_dir)

from visual_registry import VisualRegistry
from entity_manager import EntityManager
from entities import TestEntity
from input_handler import InputHandler
from renderer import Renderer

def main():
    """
    精靈圖渲染整合測試
    目的：驗證 5x5 Spritesheet 切割與自動動畫播放功能
    """
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.FULLSCREEN | pygame.SCALED)
    pygame.display.set_caption("Tethered Alarm - Sprite Rendering Test")
    clock = pygame.time.Clock()

    # 1. 初始化管理系統
    entity_manager = EntityManager()
    renderer = Renderer(screen)
    input_handler = InputHandler()

    # 2. 載入 5x5 精靈圖
    # 請確保 assets/sprites/ 目錄下有這張圖，若檔名不同請自行修改
    sprite_key = "test_hero"
    sprite_filename = "hero.png" 
    move_speed = 300  # 測試移動速度
    
    print(f"[測試] 正在載入資源: {sprite_filename}")
    VisualRegistry.load_image(sprite_key, sprite_filename)

    # 3. 建立 5x5 測試實體並加入管理
    # 放在畫面中間 (640, 360)
    test_actor = TestEntity(640, 360, sprite_key)
    entity_manager.add(test_actor)

    print("[測試] 啟動測試迴圈。控制方式：WASD 移動，觀察動畫與位移...")
    
    running = True
    while running:
        dt = clock.tick(60) / 1000.0  # 限制 60 FPS 並取得每幀間隔

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # 處理 WASD 移動輸入
        dx, dy = input_handler.get_movement_input()
        test_actor.x += dx * move_speed * dt
        test_actor.y += dy * move_speed * dt

        # 執行更新與渲染
        entity_manager.update_all(dt)
        renderer.clear()
        renderer.draw_world(entity_manager)
        renderer.draw_ui(clock)  # 順便觀察 FPS 是否穩定
        renderer.display()

    pygame.quit()

if __name__ == "__main__":
    main()

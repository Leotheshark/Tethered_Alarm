# --- 實體與管理模組 ---
import pygame
from constants import COLORS  # 從統一的常數檔讀取顏色

# 實體基礎類別：所有遊戲物件的「祖先」
class Entity:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color

    def update(self, dt):
        """每一幀更新邏輯 (由子類別實作)"""
        pass

    def draw(self, screen):
        """繪製自己 (由子類別實作)"""
        pass

# 鬼魂類別：繼承自 Entity，代表玩家
class Ghost(Entity):
    def __init__(self, color="blue"):
        # 呼叫父類別 Entity 的初始化
        super().__init__(640, 360, COLORS.get(color, (200, 200, 200)))
        self.speed = 200  # 移動速度 (像素/秒)

    def move(self, dx, dy, dt):
        """根據輸入移動座標"""
        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt

    def draw(self, screen):
        """在螢幕上畫出圓形鬼魂"""
        pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), 24)

# 實體管理員：負責管理畫面上所有的物體
class EntityManager:
    def __init__(self):
        self.entities = []

    def add(self, entity):
        self.entities.append(entity)

    def update_all(self, dt):
        for entity in self.entities:
            entity.update(dt)

    def draw_all(self, screen):
        for entity in self.entities:
            entity.draw(screen)

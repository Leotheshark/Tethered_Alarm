import pygame
import sys

COLORS = {
    "blue":  (100, 180, 255),
    "green": (100, 255, 150),
    "pink":  (255, 150, 200),
    "red":   (255, 100, 100),
}

class Ghost:
    def __init__(self, color="blue"):
        self.x = 640
        self.y = 360
        self.speed = 200  # px/s
        self.color = COLORS.get(color, (200, 200, 200))

    def handle_input(self, keys, dt):
        if keys[pygame.K_w]: self.y -= self.speed * dt
        if keys[pygame.K_s]: self.y += self.speed * dt
        if keys[pygame.K_a]: self.x -= self.speed * dt
        if keys[pygame.K_d]: self.x += self.speed * dt

    def draw(self, screen):
        pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), 24)

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 720))
        pygame.display.set_caption("Co-up: Tethered Alarm")
        self.clock = pygame.time.Clock()
        self.ghost = Ghost("blue")

    def run(self):
        while True:
            dt = self.clock.tick(60) / 1000.0  # 秒

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            keys = pygame.key.get_pressed()
            self.ghost.handle_input(keys, dt)

            self.screen.fill((20, 20, 30))
            self.ghost.draw(self.screen)

            # FPS 顯示
            font = pygame.font.SysFont(None, 24)
            fps_text = font.render(f"FPS: {int(self.clock.get_fps())}", True, (180, 180, 180))
            self.screen.blit(fps_text, (10, 10))

            pygame.display.flip()

if __name__ == "__main__":
    Game().run()
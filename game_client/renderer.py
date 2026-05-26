# --- 渲染模組 ---
import pygame
import math
from visual_registry import VisualRegistry
from constants import COLORS

# 磚片類型 → 顏色對照
_TILE_COLORS = {
    0: (0, 0, 100),       # W 牆壁：深藍色
    1: (255, 230, 210),   # E 空地：背景色
    2: (255, 230, 210),   # P pellet：空地底色（pellet 另外畫圓點）
    3: (180, 60, 60),     # G 閘門（關閉）：紅色
    4: (60, 180, 60),     # B 按鈕：綠色
    5: (180, 100, 40),    # S 釘板：橘棕色
}

# 玩家顏色 → RGB 從 constants.COLORS 對照表轉換而來，確保一致性。
_PLAYER_COLORS = COLORS

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont(None, 24)
        self.font_large = pygame.font.SysFont(None, 52)

    def clear(self):
        """用背景色清空畫面"""
        self.screen.fill(_TILE_COLORS[1])

    def draw_ui(self, clock):
        """繪製介面資訊"""
        pass
    
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
                # fallback：若斷線則灰色，否則洋紅佔位方塊
                if getattr(entity, 'disconnected', False):
                    color = (80, 80, 80)
                else:
                    color = (255, 0, 255)
                size = 32
                pygame.draw.rect(
                    self.screen,
                    color,
                    (entity.x - size // 2, entity.y - size // 2, size, size)
                )
                # 斷線時在角色上方顯示「OFFLINE」標籤
                if getattr(entity, 'disconnected', False):
                    label = self.font.render("OFFLINE", True, (200, 80, 80))
                    self.screen.blit(label, (entity.x - label.get_width() // 2, entity.y - 36))

    def draw_status_ui(self, disconnected_colors, show_surrender):
        """繪製斷線提示與投降按鈕。"""
        y = 40
        for color in disconnected_colors:
            msg = self.font.render(f"[{color.upper()}] TEAMMATE OFFLINE", True, (220, 100, 100))
            self.screen.blit(msg, (10, y))
            y += 22

        if show_surrender:
            # 半透明底板
            overlay = pygame.Surface((400, 80), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (440, 320))
            text = self.font_large.render("Press [S] to SURRENDER", True, (255, 80, 80))
            self.screen.blit(text, (640 - text.get_width() // 2, 340))

    def draw_game(self, render_data: dict, local_color: str):
        """
        繪製 Reverse Pac-Man 小遊戲畫面。相機鎖定在本地玩家身上，超出地圖邊界時鎖在邊緣。
        render_data 由 ReversePacman.get_render_data()
        """
        tile_map = render_data.get("tile_map", [])
        tile_size = render_data.get("tile_size", 40)
        tile_colors = render_data.get("tile_colors", _TILE_COLORS)
        players  = render_data.get("players", {})
        pacman   = render_data.get("pacman", {})

        rows = len(tile_map)
        cols = len(tile_map[0]) if rows > 0 else 0

        # 相機跟隨：以本地玩家為中心；玩家不存在/未存活時退回地圖中心
        sw, sh = self.screen.get_size()
        map_w = cols * tile_size
        map_h = rows * tile_size
        local_p = players.get(local_color)
        if local_p:
            target_x = local_p.get("x", map_w / 2)
            target_y = local_p.get("y", map_h / 2)
        else:
            target_x, target_y = map_w / 2, map_h / 2
        cam_x = target_x - sw / 2
        cam_y = target_y - sh / 2
        # 鎖邊緣：地圖小於視窗時置中，否則限制在 [0, map - screen]
        if map_w <= sw:
            cam_x = (map_w - sw) / 2
        else:
            cam_x = max(0, min(cam_x, map_w - sw))
        if map_h <= sh:
            cam_y = (map_h - sh) / 2
        else:
            cam_y = max(0, min(cam_y, map_h - sh))
        ox, oy = int(cam_x), int(cam_y)

        # 1. 繪製地圖磚片（只畫視窗範圍內的，省渲染）
        c_start = max(0, ox // tile_size)
        c_end = min(cols, (ox + sw) // tile_size + 1)
        r_start = max(0, oy // tile_size)
        r_end = min(rows, (oy + sh) // tile_size + 1)
        for r in range(r_start, r_end):
            for c in range(c_start, c_end):
                tile = tile_map[r][c]
                tx = c * tile_size - ox
                ty = r * tile_size - oy
                color = tile_colors.get(tile, _TILE_COLORS[2])
                pygame.draw.rect(self.screen, color, (tx, ty, tile_size, tile_size))

                # 磚片細節：pellet 畫白色小圓點，按鈕畫亮綠正方形，釘板畫斜線
                if tile == 2:  # P
                    cx = tx + tile_size // 2
                    cy = ty + tile_size // 2
                    pygame.draw.circle(self.screen, (0, 255 , 255), (cx, cy), 4)
                elif tile == 4:  # B 按鈕：中央畫小方塊提示
                    inner = 10
                    pygame.draw.rect(
                        self.screen, (120, 255, 120),
                        (tx + inner, ty + inner, tile_size - inner * 2, tile_size - inner * 2)
                    )

        # 2. 繪製玩家（依 Y 座標從上到下，避免重疊遮擋問題）
        sorted_players = sorted(players.items(), key=lambda kv: kv[1].get("y", 0))
        for color, pdata in sorted_players:
            px = int(pdata.get("x", 0)) - ox
            py = int(pdata.get("y", 0)) - oy
            alive = pdata.get("alive", True)
            perm_down = pdata.get("permanently_down", False)
            rescue_prog = pdata.get("rescue_progress", 0.0)
            rgb = _PLAYER_COLORS.get(color, (200, 200, 200))
            radius = pdata.get("avatar_size", 15)


            if perm_down:
                # 永久倒地：灰色 X 符號
                pygame.draw.line(self.screen, (80, 80, 80), (px - 12, py - 12), (px + 12, py + 12), 3)
                pygame.draw.line(self.screen, (80, 80, 80), (px + 12, py - 12), (px - 12, py + 12), 3)
            elif not alive:
                # 暫時倒地：半透明灰圈 + 救援進度弧線
                pygame.draw.circle(self.screen, (80, 80, 80), (px, py), 16, 3)
                if rescue_prog > 0:
                    # 進度弧線：順時針從 12 點開始
                    frac = min(rescue_prog / 2.0, 1.0)  # RESCUE_HOLD_TIME=2.0
                    end_angle = -math.pi / 2 + frac * 2 * math.pi
                    pygame.draw.arc(
                        self.screen, (255, 220, 50),
                        (px - 18, py - 18, 36, 36),
                        -math.pi / 2, end_angle, 4
                    )
            else:
                # 正常：填色圓形
                pygame.draw.circle(self.screen, rgb, (px, py), radius)
                # 速度減益提示：外圈閃紫色
                if pdata.get("debuff") or pdata.get("spike"):
                    pygame.draw.circle(self.screen, (200, 100, 255), (px, py), radius, 2)

            # 玩家顏色標籤（顯示在角色下方）
            label = self.font.render(color[:1].upper(), True, rgb)
            self.screen.blit(label, (px - label.get_width() // 2, py + radius + 2))

        # 3. 繪製 Pac-Man（黃色圓形）
        if pacman:
            pmx = int(pacman.get("x", 0)) - ox
            pmy = int(pacman.get("y", 0)) - oy
            pm_radius = pacman.get("avatar_size", 15)
            pygame.draw.circle(self.screen, (255, 220, 0), (pmx, pmy), pm_radius)
            pygame.draw.circle(self.screen, (200, 160, 0), (pmx, pmy), pm_radius, 2)

        # 4. HUD：剩餘 pellet 數量
        pellets_left = render_data.get("pellets_left", 0)
        hud = self.font.render(f"Pellets: {pellets_left}", True, (200, 200, 200))
        sw, sh = self.screen.get_size()
        self.screen.blit(hud, (sw - hud.get_width() - 20, sh - hud.get_height() - 20))

    def display(self):
        """將繪製內容更新到螢幕上"""
        pygame.display.flip()
# --- 渲染模組 ---
import pygame
import math
from visual_registry import VisualRegistry
from constants import COLORS

# 磚片類型 → 顏色對照
_TILE_COLORS = {
    0: (0, 0, 100),       # W 牆壁：深藍色
    1: (255, 230, 210),   # E 空地：背景色
    2: (255, 230, 210),   # P（已廢棄，地圖載入時轉為空地；保留色避免舊地圖殘留索引出錯）
    3: (180, 60, 60),     # G 閘門（關閉）：紅色
    4: (60, 180, 60),     # B 按鈕：綠色
    5: (180, 100, 40),    # S 釘板：橘棕色
    6: (120, 90, 160),    # F 迷霧陷阱：紫灰色
}

# 玩家顏色 → RGB 從 constants.COLORS 對照表轉換而來，確保一致性。
_PLAYER_COLORS = COLORS

# 通關動畫時長常數 (需與 BaseLogicInterface 同步)
CLEAR_PRE_PAUSE_TIME = 1.0  # 布條滑入前的空白停頓
CLEAR_IN_TIME        = 0.3  # 白色布條滑入時間
CLEAR_TEXT_PAUSE_TIME = 0.4  # 文字進場前的停頓時間
CLEAR_TEXT_TIME      = 1.5  # 文字停留總時間 (含停頓、進場動畫與持續時間)
CLEAR_TEXT_ANIM_TIME = 0.3  # 文字縮放與透明度漸變的持續時間
CLEAR_OUT_TIME       = 0.3  # 布條帶著文字滑出時間

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont(None, 24)
        self.font_large = pygame.font.SysFont(None, 52)
        self.font_clear = pygame.font.SysFont(None, 300, bold=True)

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
        pacmen   = render_data.get("pacmen", [])
        buttons  = render_data.get("buttons", [])
        clear_anim = render_data.get("clear_anim", {"stage": 0, "timer": 0.0})

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

        # 修正垂直對齊：若地圖高度小於視窗，將相機 y 設為 0 以便讓地圖貼頂，留白集中在下方
        cam_y = 0 if map_h <= sh else max(0, min(cam_y, map_h - sh))

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

                # 磚片細節：按鈕畫亮綠正方形，迷霧陷阱畫霧點提示
                if tile == 4:  # B 按鈕：中央畫小方塊提示
                    inner = 10
                    pygame.draw.rect(
                        self.screen, (120, 255, 120),
                        (tx + inner, ty + inner, tile_size - inner * 2, tile_size - inner * 2)
                    )
                elif tile == 6:  # F 迷霧陷阱：畫幾個霧點提示腳下有陷阱
                    cy = ty + tile_size // 2
                    for off in (-12, 0, 12):
                        pygame.draw.circle(self.screen, (180, 160, 210), (tx + tile_size // 2 + off, cy), 4)

        # 1.5. 繪製互動按鈕 (原生 Pygame 繪圖實作發光)
        for btn in buttons:
            bx, by = int(btn["x"]) - ox, int(btn["y"]) - oy

            color_rgb = _PLAYER_COLORS.get(btn["color"], (200, 200, 200))

            # 能量填滿瞬間的單次閃光特效 (播放一次)
            act_t = btn.get("activated_time", 0)
            if act_t > 0:
                elapsed = pygame.time.get_ticks() - act_t
                if 0 < elapsed < 400:  # 特效持續 0.4 秒
                    f_prog = elapsed / 400.0
                    f_size = int(50 + f_prog * 250)    # 從 50px 迅速擴張到 300px
                    f_alpha = int(30 * (1.0 - f_prog ** 2)) # 隨著擴張逐漸變透明
                    f_surf = pygame.Surface((f_size, f_size), pygame.SRCALPHA)
                    pygame.draw.rect(f_surf, (*color_rgb, f_alpha), (0, 0, f_size, f_size), border_radius=25)
                    self.screen.blit(f_surf, (bx - f_size // 2, by - f_size // 2))

            size = 60
            
            if btn["triggered"]:
                # 繪製發光效果：多層半透明擴散
                for i in range(3):
                    glow_size = size + (i + 1) * 10
                    # 建立暫時的透明表面
                    s = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                    alpha = 100 - (i * 30)
                    pygame.draw.rect(s, (*color_rgb, alpha), (0, 0, glow_size, glow_size), border_radius=10)
                    self.screen.blit(s, (bx - glow_size // 2, by - glow_size // 2))

                # 繪製動態水波擴散效果 (Pulse Ripple)
                curr_t = pygame.time.get_ticks() / 1000.0
                for i in range(4):  # 使用兩層交替的擴散波紋，營造層次感
                    # prog 介於 0.0 ~ 1.0 之間，控制單次波紋的擴張進度
                    prog = ((curr_t + i * 0.4) % 1.6) / 1.6
                    ripple_size = int(size + prog * 50)  # 波紋從 50px 擴散到 100px
                    alpha = int(160 * (1.0 - prog))      # 越往外擴散，顏色越淡
                    
                    # 建立帶 Alpha 通道的透明 Surface
                    s = pygame.Surface((ripple_size, ripple_size), pygame.SRCALPHA)
                    # 繪製空心的圓角矩形框，寬度2
                    line_w = 2
                    pygame.draw.rect(s, (*color_rgb, alpha), (0, 0, ripple_size, ripple_size), line_w, border_radius=10)
                    self.screen.blit(s, (bx - ripple_size // 2, by - ripple_size // 2))

                # 實心中心
                pygame.draw.rect(self.screen, color_rgb, (bx - size // 2, by - size // 2, size, size), border_radius=10)
                pygame.draw.rect(self.screen, color_rgb, (bx - size // 2, by - size // 2, size, size), 3, border_radius=10)
            else:
                # 未觸發狀態：外框直接使用 constants.py 定義的對應顏色
                pygame.draw.rect(self.screen, color_rgb, (bx - size // 2, by - size // 2, size, size), 3, border_radius=10)
                
                # 繪製充能進度條
                prog = btn["progress"]
                if prog > 0:
                    prog_h = int((size - 4) * prog)
                    pygame.draw.rect(
                        self.screen, 
                        color_rgb, 
                        (bx - size // 2 + 2, by + size // 2 - 2 - prog_h, size - 4, prog_h),
                    )

        # 2. 繪製玩家（依 Y 座標從上到下，避免重疊遮擋問題）
        sorted_players = sorted(players.items(), key=lambda kv: kv[1].get("y", 0))
        for color, pdata in sorted_players:
            px = int(pdata.get("x", 0)) - ox
            py = int(pdata.get("y", 0)) - oy
            is_alive = pdata.get("is_alive", True)
            rescue_prog = pdata.get("rescue_progress", 0.0)
            rescue_count = pdata.get("rescue_count", 0)
            rgb = _PLAYER_COLORS.get(color, (200, 200, 200))
            radius = pdata.get("avatar_size", 28) # 預設為 32，配合 64x64px 角色

            # 一律嘗試繪製精靈圖（已無永久倒地的灰 X；倒地者也照常畫，另疊上救援弧線）
            vkey = pdata.get("visual_key")
            surface = VisualRegistry.get_surface(vkey) if vkey else None
            if surface:
                # 同步水平切割邏輯：left/right 3 欄，其餘 2 欄
                cols = 3 if (vkey and ("left" in vkey or "right" in vkey)) else 2
                # 修正：加上 % cols 確保索引安全，防止角色在切換狀態時瞬間消失
                frame_idx = pdata.get("frame_index", 0) % cols
                w, h = surface.get_size()
                frame_w = w // cols
                area = pygame.Rect(frame_idx * frame_w, 0, frame_w, h)
                self.screen.blit(surface, (px - frame_w // 2, py - h // 2), area)
            else:
                # 資源未載入時的備援：繪製填色圓形
                pygame.draw.circle(self.screen, rgb, (px, py), radius)

            # 暫時倒地時繪製救援進度弧線
            if not is_alive and rescue_prog > 0:
                pygame.draw.circle(self.screen, (80, 80, 80), (px, py), radius + 2, 3) # 繪製外圈
                frac = min(rescue_prog / 2.0, 1.0)  # RESCUE_HOLD_TIME=2.0
                end_angle = -math.pi / 2 + frac * 2 * math.pi
                pygame.draw.arc(
                    self.screen, (255, 220, 50),
                    (px - radius - 4, py - radius - 4, (radius + 4) * 2, (radius + 4) * 2), # 弧線的繪製範圍
                    -math.pi / 2, end_angle, 4
                )

            # 減速指示：踩釘板或已被救過（rescue_count>0）→ 疊紫色緩速環
            if pdata.get("spike") or rescue_count > 0:
                pygame.draw.circle(self.screen, (200, 100, 255), (px, py), radius + 2, 2)
            # rescue_count 用紅色小圓點顯示「被救過幾次 / 有多慢」
            for i in range(rescue_count):
                pygame.draw.circle(self.screen, (255, 80, 80), (px - 12 + i * 8, py - radius - 12), 3)

        # 3. 繪製所有 Pac-Man（黃色圓形；數量會隨時間複製增加）
        for pm in pacmen:
            pmx = int(pm.get("x", 0)) - ox
            pmy = int(pm.get("y", 0)) - oy
            pm_radius = pm.get("avatar_size", 15)
            pygame.draw.circle(self.screen, (255, 220, 0), (pmx, pmy), pm_radius)
            pygame.draw.circle(self.screen, (200, 160, 0), (pmx, pmy), pm_radius, 2)

        # 3.5. 致盲迷霧：本地玩家踩到迷霧時，蓋暗幕並在其周圍留一個清晰圓
        if render_data.get("fog_active"):
            self._draw_fog(render_data, players, local_color, ox, oy)

        # 4. HUD：四色蓄能進度條 + 隊伍總進度（取代原本的剩餘 pellet 數）
        self._draw_charge_hud(render_data)

        # 5. 通關過場動畫 (Clear Animation Overlay)
        #    新版以 _cleared/_failed 旗標結束，暫時不送 clear_anim 資料 → stage 0 靜默不畫；
        #    待結束流程接上 clear_anim 排程後即可自動顯示。
        self._draw_clear_overlay(clear_anim)

    def _draw_clear_overlay(self, anim):
        stage = anim.get("stage", 0)
        if stage == 0 or stage == 5:
            return

        sw, sh = self.screen.get_size()
        timer = anim.get("timer", 0.0)

        banner_color = (250, 250, 250)
        text_color = (255, 50, 50)

        banner_x = 0
        banner_w = sw

        # 準備文字 Surface (300px 粗體)
        text_str = "C L E A R !"
        base_text_surf = self.font_clear.render(text_str, True, text_color)
        current_alpha = 255
        current_scale = 1.0
        text_offset_x = 0

        if stage == 1:  # Pre Pause: 通關瞬間的空白停頓 (不畫任何東西)
            banner_w = 0
            current_alpha = 0

        elif stage == 2:  # Slide In: 從左滑向右
            progress = min(1.0, timer / CLEAR_IN_TIME)
            # Ease Out: 1 - (1-x)^2
            ease_prog = 1 - (1 - progress) ** 2
            banner_w = sw * ease_prog
            banner_x = 0
            current_alpha = 0 # 進入階段暫不顯示文字

        elif stage == 3:  # Show Text: 縮放進場與停留
            banner_x = 0
            banner_w = sw

            if timer < CLEAR_TEXT_PAUSE_TIME:
                # 第一階段：停頓期 (文字隱藏)
                current_alpha = 0
                current_scale = 2.5
            elif timer < (CLEAR_TEXT_PAUSE_TIME + CLEAR_TEXT_ANIM_TIME):
                # 第二階段：縮放進場動畫
                anim_timer = timer - CLEAR_TEXT_PAUSE_TIME
                anim_prog = anim_timer / CLEAR_TEXT_ANIM_TIME
                current_scale = 2.5 - 1.5 * anim_prog
                current_alpha = int(255 * anim_prog)
            else:
                # 第三階段：穩定停留期
                current_scale = 1.0
                current_alpha = 255

        elif stage == 4:  # Slide Out: 帶著文字向右收走
            progress = min(1.0, timer / CLEAR_OUT_TIME)
            # Ease In: x^2
            ease_prog = progress ** 2
            banner_x = sw * ease_prog
            banner_w = sw - banner_x
            text_offset_x = banner_x
            current_alpha = 255

        # 繪製布條
        if banner_w > 0:
            bh = 300
            pygame.draw.rect(self.screen, banner_color, (banner_x, (sh - bh) // 2, banner_w, bh))

        # 繪製文字
        if stage >= 3:
            # 縮放處理
            if current_scale != 1.0:
                w, h = base_text_surf.get_size()
                draw_surf = pygame.transform.smoothscale(base_text_surf, (int(w * current_scale), int(h * current_scale)))
            else:
                draw_surf = base_text_surf

            draw_surf.set_alpha(current_alpha)
            text_rect = draw_surf.get_rect(center=(sw // 2 + text_offset_x, sh // 2))
            self.screen.blit(draw_surf, text_rect)

    def _draw_fog(self, render_data, players, local_color, ox, oy):
        """
        致盲迷霧：以半透明暗幕蓋住整個畫面，只在本地玩家周圍留一個帶柔邊的清晰圓。
        清晰圓中心採用本地玩家的「螢幕座標」實算（相機在地圖邊緣會夾邊，玩家未必置中）。
        """
        sw, sh = self.screen.get_size()
        radius = render_data.get("fog_radius", 150)

        local_p = players.get(local_color)
        if local_p:
            cx = int(local_p.get("x", 0)) - ox
            cy = int(local_p.get("y", 0)) - oy
        else:
            cx, cy = sw // 2, sh // 2

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        # 完全不透明的黑幕：圓外「完全看不見」，視野只剩角色周圍一圈（而非單純變暗）
        overlay.fill((0, 0, 0, 255))
        # 由大到小畫多層遞減 alpha 的圓（pygame.draw 直接覆寫像素，非混色），
        # 在角色周圍挖出一個帶柔邊的透明洞：洞內全亮、邊緣漸暗、洞外純黑。
        for alpha, extra in ((210, 55), (160, 40), (100, 25), (45, 12), (0, 0)):
            pygame.draw.circle(overlay, (0, 0, 0, alpha), (cx, cy), radius + extra)
        self.screen.blit(overlay, (0, 0))

    def _draw_charge_hud(self, render_data):
        """畫面下方顯示四色蓄能條與隊伍總進度（幾人已蓄滿）。"""
        players = render_data.get("players", {})
        sw, sh = self.screen.get_size()
        order = ["blue", "green", "pink", "red"]
        present = [c for c in order if c in players]
        if not present:
            return

        bar_w, bar_h, gap = 160, 18, 16
        total_w = len(present) * bar_w + (len(present) - 1) * gap
        x0 = (sw - total_w) // 2
        y0 = sh - 60
        filled = 0
        for idx, color in enumerate(present):
            charge = max(0.0, min(1.0, players[color].get("charge", 0.0)))
            if charge >= 1.0:
                filled += 1
            rgb = _PLAYER_COLORS.get(color, (200, 200, 200))
            bx = x0 + idx * (bar_w + gap)
            # 底框
            pygame.draw.rect(self.screen, (40, 40, 40), (bx, y0, bar_w, bar_h), border_radius=4)
            # 進度填滿
            if charge > 0:
                pygame.draw.rect(self.screen, rgb, (bx, y0, int(bar_w * charge), bar_h), border_radius=4)
            # 外框：蓄滿時亮白，否則用該玩家顏色
            border = (255, 255, 255) if charge >= 1.0 else rgb
            pygame.draw.rect(self.screen, border, (bx, y0, bar_w, bar_h), 2, border_radius=4)

        # 隊伍總進度文字
        label = self.font.render(f"CHARGED {filled}/{len(present)}", True, (230, 230, 230))
        self.screen.blit(label, ((sw - label.get_width()) // 2, y0 - 26))

    def display(self):
        """將繪製內容更新到螢幕上"""
        pygame.display.flip()
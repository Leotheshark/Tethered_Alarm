# --- 渲染模組 ---
import pygame
import math
import os
from visual_registry import VisualRegistry
from constants import COLORS

# 磚片類型 → 顏色對照
_TILE_COLORS = {
    0: (0, 0, 100),       # W 牆壁：深藍色
    1: (220, 170, 140),   # E 空地：背景色
    2: (220, 170, 140),   # P（已廢棄，地圖載入時轉為空地；保留色避免舊地圖殘留索引出錯）
    3: (180, 60, 60),     # G 閘門（關閉）：紅色
    4: (60, 180, 60),     # B 按鈕：綠色
    5: (180, 100, 40),    # S 釘板：橘棕色
    6: (120, 90, 160),    # F 迷霧陷阱：紫灰色
}

# 玩家顏色 → RGB 從 constants.COLORS 對照表轉換而來，確保一致性。
_PLAYER_COLORS = COLORS

# 失敗投票畫面配色：直接取自地圖磚片色盤（_TILE_COLORS），讓投票覆蓋層與遊戲世界風格一致。
# 語意同地圖：綠=前進/好(按鈕色)、紅=停止/壞(閘門色)、深藍=牆、暖棕=地板。
# 暖色米白：統一給中性文字（標題/倒數/提示/按鈕文字）使用，整體更暖、更一致。
_VOTE_CREAM = (238, 230, 215)
_VOTE_COLORS = {
    # 背景遮罩：地板暖棕半透明。暖棕比深藍亮，故壓深底色 (90,60,40) 再給中高透明度，
    # 像一層暖色濾鏡蓋在遊戲畫面上——夠暖、夠暗以看清按鈕與文字。
    "overlay":     (90, 60, 40, 210),
    "panel_edge":  (220, 170, 140),    # 點綴邊框/分隔：地板暖棕
    "title":       _VOTE_CREAM,        # 標題「ALL DOWN!」：米白（中性文字）
    "countdown":   _VOTE_CREAM,        # 倒數秒數：米白
    "tip":         _VOTE_CREAM,        # 提示文字：米白
    # CONTINUE：地圖按鈕綠 (60,180,60)；已投票後變暗版
    "continue":      (60, 180, 60),
    "continue_dim":  (38, 110, 40),
    # GIVE UP：地圖閘門紅 (180,60,60)；已投票後變暗版
    "giveup":        (180, 60, 60),
    "giveup_dim":    (110, 40, 40),
    "btn_border":  (220, 170, 140),    # 按鈕邊框：地板暖棕（取代原本死白）
    "btn_text":    _VOTE_CREAM,        # 按鈕文字：米白（中性文字）
    # 四色明細保留紅綠語意（看得出誰投了什麼），未投票為暖灰
    "detail_continue": (140, 220, 140),
    "detail_giveup":   (220, 130, 130),
    "detail_waiting":  (170, 155, 140),
}

# 通關動畫時長常數 (需與 BaseLogicInterface 同步)
CLEAR_PRE_PAUSE_TIME = 2.0  # 布條滑入前的空白停頓
CLEAR_IN_TIME        = 0.3  # 白色布條進入時間
CLEAR_TEXT_PAUSE_TIME = 0.4  # 文字進場前的停頓時間
CLEAR_TEXT_TIME      = 1.5  # 文字停留總時間 (含停頓、進場動畫與持續時間)
CLEAR_TEXT_ANIM_TIME = 0.3  # 文字縮放與透明度漸變的持續時間
CLEAR_OUT_TIME       = 0.3  # 布條帶著文字滑出時間

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        base_path = os.path.dirname(os.path.abspath(__file__))

        # 內文與一般 UI 文字用 VT323（復古 CRT/終端機感）；大標題另用 Pixelify Sans
        # （較有份量的像素字），兩者分工讓標題更醒目、內文更耐讀。
        # VT323 等寬偏細，同 px 渲染比預設 SysFont 略小，故各級尺寸略放大以維持原本份量。
        # 找不到字體檔時 fallback 回 pygame 內建字型，確保未帶字體檔的環境也能正常顯示。
        font_path = os.path.join(base_path, "assets", "fonts", "VT323-Regular.ttf")
        title_path = os.path.join(base_path, "assets", "fonts", "Letter Magic.ttf")
        self.font = self._load_font(font_path, 28)        # 一般文字（明細/提示）
        self.font_large = self._load_font(font_path, 58)  # 倒數等 UI 文字
        self.font_button = self._load_font(font_path, 48) # 投票按鈕文字（較小，避免長字貼邊框）
        # 大標題（START! / CLEAR! / ALL DOWN!）統一用 Pixelify Sans
        self.font_title = self._load_font(title_path, 72)              # ALL DOWN! 等中型標題
        self.font_warning = self._load_font(title_path, 120) # 飛刀預警倒數
        self.font_clear = self._load_font(title_path, 240, fallback_bold=True)  # START! / CLEAR! 動畫大字

        # 失敗投票按鈕的點擊區域（由 _draw_defeat_vote 每幀更新；engine 讀此做滑鼠命中測試）
        self.vote_continue_rect = None
        self.vote_giveup_rect = None

        # 載入牆壁圖片：使用 assets/image/wall.png (原始尺寸已符合 60x60px)
        wall_path = os.path.join(base_path, "assets", "image", "wall.png")
        try:
            self.wall_img = pygame.image.load(wall_path).convert_alpha()
            print(f"[Renderer] Successfully loaded wall texture: {wall_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load wall image at {wall_path}: {e}")
            self.wall_img = None

        # 載入地板圖片：使用 assets/image/ground.png (原始尺寸已符合 60x60px)
        ground_path = os.path.join(base_path, "assets", "image", "ground.png")
        try:
            self.ground_img = pygame.image.load(ground_path).convert_alpha()
            print(f"[Renderer] Successfully loaded ground texture: {ground_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load ground image at {ground_path}: {e}")
            self.ground_img = None

        # 載入閘門圖片：使用 assets/image/gate.png (原始尺寸已符合 60x60px)
        gate_path = os.path.join(base_path, "assets", "image", "gate.png")
        try:
            self.gate_img = pygame.image.load(gate_path).convert_alpha()
            print(f"[Renderer] Successfully loaded gate texture: {gate_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load gate image at {gate_path}: {e}")
            self.gate_img = None

        # 載入迷霧圖片：使用 assets/image/fog.png
        fog_path = os.path.join(base_path, "assets", "image", "fog.png")
        try:
            self.fog_img = pygame.image.load(fog_path).convert_alpha()
            print(f"[Renderer] Successfully loaded fog texture: {fog_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load fog image at {fog_path}: {e}")
            self.fog_img = None

        # 載入按鈕圖片
        untriggerd_path = os.path.join(base_path, "assets", "image", "button_untriggerd.png")
        try:
            self.btn_untriggerd_img = pygame.image.load(untriggerd_path).convert_alpha()
            print(f"[Renderer] Successfully loaded untriggered button texture: {untriggerd_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load untriggered button image at {untriggerd_path}: {e}")
            self.btn_untriggerd_img = None

        triggerd_path = os.path.join(base_path, "assets", "image", "button_triggerd.png")
        try:
            self.btn_triggerd_img = pygame.image.load(triggerd_path).convert_alpha()
            print(f"[Renderer] Successfully loaded triggered button texture: {triggerd_path}")
        except Exception as e:
            print(f"[Renderer] Failed to load triggered button image at {triggerd_path}: {e}")
            self.btn_triggerd_img = None

    def _load_font(self, path, size, fallback_bold=False):
        """載入指定 .ttf 字體；失敗時 fallback 回 pygame 內建字型，確保缺檔也能運作。
        fallback_bold：fallback 時是否用粗體（給通關大字維持份量）。"""
        try:
            font = pygame.font.Font(path, size)
            return font
        except Exception as e:
            print(f"[Renderer] Failed to load font {path} (size {size}): {e}; using default")
            return pygame.font.SysFont(None, size, bold=fallback_bold)

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

    def draw_status_ui(self, disconnected_colors, show_surrender, local_disconnected=False):
        """繪製斷線提示與投降按鈕。"""
        # 本機自己斷線：頂部置中顯示醒目橫幅，讓玩家知道「不是卡住，是連線斷了」，
        # 而非畫面照常運行卻悄悄不再同步（隊友會誤以為你掛機）。
        # 用英文以配合 SysFont(None) 內建字型（不含中文字符，中文會渲染成方塊）。
        if local_disconnected:
            banner = self.font_large.render("CONNECTION LOST - RECONNECTING...", True, (255, 220, 80))
            sw = self.screen.get_width()
            bg = pygame.Surface((banner.get_width() + 40, banner.get_height() + 16), pygame.SRCALPHA)
            bg.fill((120, 0, 0, 180))
            self.screen.blit(bg, (sw // 2 - bg.get_width() // 2, 8))
            self.screen.blit(banner, (sw // 2 - banner.get_width() // 2, 16))

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
        knives   = render_data.get("knives", [])
        buttons  = render_data.get("buttons", [])
        warning  = render_data.get("warning", {"active": False})
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

                if tile == 0 and self.wall_img:
                    self.screen.blit(self.wall_img, (tx, ty))
                elif (tile == 1 or tile == 2) and self.ground_img:
                    self.screen.blit(self.ground_img, (tx, ty))
                elif tile == 3 and self.gate_img:
                    self.screen.blit(self.gate_img, (tx, ty))
                elif tile == 4:
                    # 根據是否有按鈕被踩下切換圖片
                    btn_img = self.btn_triggerd_img if render_data.get("any_gate_pressed") else self.btn_untriggerd_img
                    if btn_img:
                        self.screen.blit(btn_img, (tx, ty))
                    else:
                        # 圖片載入失敗時的備援繪圖
                        color = tile_colors.get(tile, _TILE_COLORS[2])
                        pygame.draw.rect(self.screen, color, (tx, ty, tile_size, tile_size))
                        inner = 10
                        pygame.draw.rect(
                            self.screen, (120, 255, 120),
                            (tx + inner, ty + inner, tile_size - inner * 2, tile_size - inner * 2)
                        )
                elif tile == 6 and self.fog_img:
                    self.screen.blit(self.fog_img, (tx, ty))
                else:
                    color = tile_colors.get(tile, _TILE_COLORS[2])
                    pygame.draw.rect(self.screen, color, (tx, ty, tile_size, tile_size))

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
                # 充能點沒滿時的脈衝發光特效 (強效多層漸層邊框)
                curr_t = pygame.time.get_ticks() / 1000.0
                # 加快脈衝頻率 (4.0 -> 5.0)
                pulse = (math.sin(curr_t * 2.0) + 1.0) / 2.0 
                
                # 裡面不發光，透過 10 層邊框疊加營造向外擴散的強烈漸層
                for i in range(10):
                    # 每一層的擴張距離與透明度遞減，初始透明度從 50 提升至 140
                    layer_expand = int(pulse * (i + 1) * 2)
                    glow_size = size + layer_expand
                    glow_alpha = int((100 - i * 10) * pulse)
                    
                    if glow_alpha > 0:
                        glow_surf = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                        # 變動線寬：越靠近中心越厚 (4px -> 1px)
                        glow_w = max(1, 4 - i // 3)
                        pygame.draw.rect(glow_surf, (*color_rgb, glow_alpha), (0, 0, glow_size, glow_size), glow_w, border_radius=10 + layer_expand // 4)
                        self.screen.blit(glow_surf, (bx - glow_size // 2, by - glow_size // 2))

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
                frac = min(rescue_prog, 1.0)
                end_angle = -math.pi / 2 + frac * 2 * math.pi
                pygame.draw.arc(
                    self.screen, (255, 220, 50),
                    (px - radius - 4, py - radius - 4, (radius + 4) * 2, (radius + 4) * 2), # 弧線的繪製範圍
                    -math.pi / 2, end_angle, 4
                )

            # rescue_count 用紅色小圓點顯示「被救過幾次 / 有多慢」
            for i in range(rescue_count):
                pygame.draw.circle(self.screen, (255, 80, 80), (px - 12 + i * 8, py - radius - 12), 3)

        # 3. 繪製所有 Pac-Man
        for pm in pacmen:
            pmx = int(pm.get("x", 0)) - ox
            pmy = int(pm.get("y", 0)) - oy
            vkey = pm.get("visual_key")
            surface = VisualRegistry.get_surface(vkey) if vkey else None

            if surface:
                # 處理 1x2 影格切割 (Pac-Man 在 ReversePacman 中定義為 2 欄動畫)
                cols = 2
                frame_idx = pm.get("frame_index", 0) % cols
                w, h = surface.get_size()
                frame_w = w // cols
                area = pygame.Rect(frame_idx * frame_w, 0, frame_w, h)
                self.screen.blit(surface, (pmx - frame_w // 2, pmy - h // 2), area)
            else:
                # Fallback: 若圖片尚未載入或遺失，繪製原本的黃色圓形
                pm_radius = pm.get("avatar_size", 15)
                pygame.draw.circle(self.screen, (255, 220, 0), (pmx, pmy), pm_radius)
                pygame.draw.circle(self.screen, (200, 160, 0), (pmx, pmy), pm_radius, 2)

        # 3.2 繪製飛刀
        for kn in knives:
            kx, ky = int(kn["x"]) - ox, int(kn["y"]) - oy
            surface = VisualRegistry.get_surface(kn["visual_key"])
            if surface:
                # 如果飛刀正在淡出 (fade_timer > 0)，設定透明度
                if not kn["is_active"] and kn["fade_timer"] > 0:
                    # 假設淡出時長為 1.0 秒
                    alpha = int(255 * kn["fade_timer"])
                    surface = surface.copy()
                    surface.set_alpha(alpha)
                
                self.screen.blit(surface, (kx - surface.get_width() // 2, ky - surface.get_height() // 2))
            else:
                # Fallback: 繪製小灰色矩形
                pygame.draw.rect(self.screen, (150, 150, 150), (kx - 15, ky - 15, 30, 30))

        # 3.5. 致盲迷霧：本地玩家踩到迷霧時，蓋暗幕並在其周圍留一個清晰圓
        if render_data.get("fog_active"):
            self._draw_fog(render_data, players, local_color, ox, oy)

        # 3.3 繪製飛刀預警 (移至迷霧後繪製，確保預警文字不被致盲黑幕遮擋)
        self._draw_knife_warning(warning)

        # 4. HUD：原本用於顯示玩家個人蓄能條，現已廢棄（改由地圖上的 ColorButton 顯示）
        # self._draw_charge_hud(render_data)

        # 5. 通關過場動畫 (Clear Animation Overlay)
        clear_stage = clear_anim.get("stage", 0)
        if 0 < clear_stage < 5:
            clear_timer = clear_anim.get("timer", 0.0)
            alpha = 128
            if clear_stage == 1:
                # 階段 1 (Pre Pause)，讓黑底根據時間慢慢變暗 (Fade-in)
                progress = min(1.0, clear_timer / CLEAR_PRE_PAUSE_TIME)
                alpha = int(128 * progress)
                
            if alpha > 0:
                dim_overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
                dim_overlay.fill((0, 0, 0, alpha))
                self.screen.blit(dim_overlay, (0, 0))
        self._draw_anim_overlay(clear_anim, "C L E A R !")

        # 開場動畫
        start_anim = render_data.get("start_anim", {"stage": 0, "timer": 0.0})
        start_stage = start_anim.get("stage", 0)
        if 0 < start_stage < 5:
            start_timer = start_anim.get("timer", 0.0)
            alpha = 128
            if start_stage == 4:
                # 階段 4 (布條滑出時)，讓黑底根據時間慢慢變淡，營造開燈感
                progress = min(1.0, start_timer / CLEAR_OUT_TIME)
                alpha = int(128 * (1.0 - progress))
                
            if alpha > 0:
                # 在動畫期間繪製全畫面半透明黑底，讓背景變暗
                dim_overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
                dim_overlay.fill((0, 0, 0, alpha))
                self.screen.blit(dim_overlay, (0, 0))
        self._draw_anim_overlay(start_anim, "S T A R T !", text_color=(84, 160, 255))

        # 失敗投票覆蓋層（四人倒地後出現，蓋在最上層）
        self._draw_defeat_vote(render_data.get("defeat_vote"))

    def _draw_knife_warning(self, warning):
        """在飛刀生成的方向邊緣繪製預警文字與倒數"""
        if not warning or not warning.get("active"):
            return
            
        sw, sh = self.screen.get_size()
        # warning["direction"] 是飛刀移動的方向
        move_dir = str(warning.get("direction", "")).lower()
        timer = max(0.0, warning.get("timer", 0.0))
        
        margin = 100
        pos_kwargs = {}

        if move_dir == "right": # 從左方生成往右飛
            from_side = "LEFT"
            pos_kwargs = {"midleft": (margin, sh // 2)}
        elif move_dir == "left": # 從右方生成往左飛
            from_side = "RIGHT"
            pos_kwargs = {"midright": (sw - margin, sh // 2)}
        elif move_dir == "down": # 從上方生成往下飛
            from_side = "TOP"
            pos_kwargs = {"midtop": (sw // 2, margin)}
        elif move_dir == "up": # 從下方生成往上飛
            from_side = "BOTTOM"
            pos_kwargs = {"midbottom": (sw // 2, sh - margin)}
        else:
            pos_kwargs = {"center": (sw // 2, 200)}

        msg = str(int(timer) + 1)
        text_surf = self.font_warning.render(msg, True, (255, 50, 50))
        text_surf.set_alpha(150) # 增加一點不透明度使其更醒目
        
        rect = text_surf.get_rect(**pos_kwargs)
        self.screen.blit(text_surf, rect)

    def _draw_defeat_vote(self, vote):
        """繪製失敗投票畫面：半透明黑底 + 標題/倒數 + 兩個可點按鈕（含票數）+ 四色投票明細。
        按鈕的點擊區域存入 self.vote_*_rect 供 engine 做滑鼠命中測試。
        文字皆用英文以配合 SysFont(None) 內建字型（中文會渲染成方塊）。"""
        if not vote or not vote.get("active"):
            # 非投票階段：清掉按鈕區域，避免 engine 誤判殘留的點擊區
            self.vote_continue_rect = None
            self.vote_giveup_rect = None
            return

        sw, sh = self.screen.get_size()
        # 半透明遮罩覆蓋全畫面：用地圖牆的深藍（取代純黑），讓投票層與遊戲世界融為一體
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(_VOTE_COLORS["overlay"])
        self.screen.blit(overlay, (0, 0))

        cx = sw // 2

        # 標題（Pixelify Sans 大標題字）
        title = self.font_title.render("ALL DOWN!", True, _VOTE_COLORS["title"])
        self.screen.blit(title, (cx - title.get_width() // 2, sh // 2 - 250))

        # 倒數（暖米白）
        secs = int(vote.get("time_left", 0)) + 1  # 向上取整，顯示較直覺
        countdown = self.font_large.render(f"{secs}s", True, _VOTE_COLORS["countdown"])
        self.screen.blit(countdown, (cx - countdown.get_width() // 2, sh // 2 - 120))

        # 統計票數
        votes = vote.get("votes", {})
        local_color = vote.get("local_color")
        local_voted = vote.get("local_voted", False)
        continue_count = sum(1 for v in votes.values() if v)
        giveup_count = sum(1 for v in votes.values() if not v)

        # 兩個並排按鈕（可點）：CONTINUE(地圖按鈕綠) / GIVE UP(地圖閘門紅)，按鈕上標票數
        btn_w, btn_h, gap = 300, 90, 60
        by = sh // 2 - 40
        self.vote_continue_rect = pygame.Rect(cx - btn_w - gap // 2, by, btn_w, btn_h)
        self.vote_giveup_rect = pygame.Rect(cx + gap // 2, by, btn_w, btn_h)
        # 本機已投票後按鈕變暗，提示已不可再點
        cont_bg = _VOTE_COLORS["continue_dim"] if local_voted else _VOTE_COLORS["continue"]
        give_bg = _VOTE_COLORS["giveup_dim"] if local_voted else _VOTE_COLORS["giveup"]
        self._draw_vote_button(self.vote_continue_rect, "CONTINUE", continue_count, cont_bg)
        self._draw_vote_button(self.vote_giveup_rect, "GIVE UP", giveup_count, give_bg)

        # 提示文字（滑鼠點擊）
        tip_txt = "Voted - waiting for others..." if local_voted else "Click to vote"
        tip = self.font.render(tip_txt, True, _VOTE_COLORS["tip"])
        self.screen.blit(tip, (cx - tip.get_width() // 2, by + btn_h + 25))

        # 四色投票明細：CONTINUE(綠) / GIVE UP(紅) / 未投(暖灰)
        y = by + btn_h + 70
        for color in ("blue", "green", "pink", "red"):
            if color in votes:
                if votes[color]:
                    label, c = "CONTINUE", _VOTE_COLORS["detail_continue"]
                else:
                    label, c = "GIVE UP", _VOTE_COLORS["detail_giveup"]
            else:
                label, c = "waiting...", _VOTE_COLORS["detail_waiting"]
            me = " (you)" if color == local_color else ""
            line = self.font.render(f"{color.upper()}{me}: {label}", True, c)
            self.screen.blit(line, (cx - line.get_width() // 2, y))
            y += 28

    def _draw_vote_button(self, rect, label, count, bg_color):
        """繪製單一投票按鈕：底色矩形 + 暖棕邊框 + 「LABEL (count)」暖白文字置中。
        邊框/文字色取自地圖地板暖棕色系，與遊戲世界風格一致。"""
        pygame.draw.rect(self.screen, bg_color, rect, border_radius=8)
        pygame.draw.rect(self.screen, _VOTE_COLORS["btn_border"], rect, width=3, border_radius=8)
        text = self.font_button.render(f"{label}  ({count})", True, _VOTE_COLORS["btn_text"])
        self.screen.blit(text, (rect.centerx - text.get_width() // 2,
                                rect.centery - text.get_height() // 2))

    def _draw_anim_overlay(self, anim, text_str, text_color=(255, 50, 50)):
        stage = anim.get("stage", 0)
        if stage == 0 or stage == 5:
            return

        sw, sh = self.screen.get_size()
        timer = anim.get("timer", 0.0)

        banner_color = (255, 255, 255)

        banner_x = 0
        banner_w = sw

        # 準備文字 Surface (300px 粗體)
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
        inner_radius = render_data.get("fog_radius", 100) # 核心全亮區半徑

        local_p = players.get(local_color)
        if local_p:
            cx = int(local_p.get("x", 0)) - ox
            cy = int(local_p.get("y", 0)) - oy
        else:
            cx, cy = sw // 2, sh // 2

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))

        # 精緻化：透過高密度循環建立平滑的徑向漸變
        fade_width = 120  # 漸變帶的寬度
        steps = 32        # 使用 32 層渲染來消除階梯感
        for i in range(steps, 0, -1):
            # 使用平方曲線讓漸變更自然（Near clear in the center, rapidly darkening at edge）
            progress = i / steps
            alpha = int(255 * (progress ** 1.5))
            curr_radius = inner_radius + (fade_width * progress)
            pygame.draw.circle(overlay, (0, 0, 0, alpha), (cx, cy), int(curr_radius))

        # 確保最核心區域完全清晰
        pygame.draw.circle(overlay, (0, 0, 0, 0), (cx, cy), inner_radius)
        self.screen.blit(overlay, (0, 0))

    def _draw_charge_hud(self, render_data):
        """畫面下方顯示四色蓄能條與隊伍總進度（幾人已蓄滿）。"""
        # 目前充能邏輯已遷移至地圖物件，此處 HUD 暫不渲染以保持畫面簡潔。
        pass
        # players = render_data.get("players", {})
        # sw, sh = self.screen.get_size()
        # order = ["blue", "green", "pink", "red"]
        # present = [c for c in order if c in players]
        # if not present:
        #     return
        #
        # bar_w, bar_h, gap = 160, 18, 16
        # total_w = len(present) * bar_w + (len(present) - 1) * gap
        # x0 = (sw - total_w) // 2
        # y0 = sh - 60
        # filled = 0
        # for idx, color in enumerate(present):
        #     charge = max(0.0, min(1.0, players[color].get("charge", 0.0)))
        #     if charge >= 1.0:
        #         filled += 1
        #     rgb = _PLAYER_COLORS.get(color, (200, 200, 200))
        #     bx = x0 + idx * (bar_w + gap)
        #     # 底框
        #     pygame.draw.rect(self.screen, (40, 40, 40), (bx, y0, bar_w, bar_h), border_radius=4)
        #     # 進度填滿
        #     if charge > 0:
        #         pygame.draw.rect(self.screen, rgb, (bx, y0, int(bar_w * charge), bar_h), border_radius=4)
        #     # 外框：蓄滿時亮白，否則用該玩家顏色
        #     border = (255, 255, 255) if charge >= 1.0 else rgb
        #     pygame.draw.rect(self.screen, border, (bx, y0, bar_w, bar_h), 2, border_radius=4)
        #
        # # 隊伍總進度文字
        # label = self.font.render(f"CHARGED {filled}/{len(present)}", True, (230, 230, 230))
        # self.screen.blit(label, ((sw - label.get_width()) // 2, y0 - 26))

    def display(self):
        """將繪製內容更新到螢幕上"""
        pygame.display.flip()
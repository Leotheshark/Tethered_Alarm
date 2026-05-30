"""
Reverse Pac-Man 關卡編輯器。

執行方式：
    python tools/map_editor.py

或指定關卡檔（不含副檔名）：
    python tools/map_editor.py level_2

操作：
- 左側工具列點選磚片或出生點工具
- 點擊地圖格子套用工具
- 配對工具：依序點 button 與 gate 建立配對
- Ctrl+S 儲存（存回目前檔名）；F2 另存新檔（輸入新名稱 → 產生新檔，不動原檔）；Ctrl+Z 復原；Ctrl+N 新關卡（清空）

輸出檔位於 repo_root/maps/<name>.json，可直接被 reverse_pacman.py 載入。
"""

import json
import os
import sys
from copy import deepcopy

import pygame


# ─── 路徑與常數 ───────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MAPS_DIR  = os.path.abspath(os.path.join(_THIS_DIR, "..", "maps"))

# 磚片字元 ↔ 顏色 / 顯示文字。與 reverse_pacman.py 的 _CHAR_TO_TILE 對齊。
# 註：pellet(P) 已從玩法移除，編輯器不再提供 P 筆刷（載入舊圖時 P 會被遊戲視為空地）。
TILES = [
    ("W", "Wall",   (40, 40, 110)),
    (".", "Empty",  (200, 200, 200)),
    ("G", "Gate",   (180, 60, 60)),
    ("B", "Button", (60, 180, 60)),
    ("S", "Spike",  (180, 100, 40)),
    ("F", "Fog",    (120, 90, 160)),
]
TILE_CHARS = {t[0] for t in TILES}

SPAWN_KEYS = ["blue", "green", "pink", "red", "pacman"]
# 蓄能站：每色一個專屬點（玩家在此長按 E 蓄能）；顏色沿用 SPAWN_COLORS。
STATION_KEYS = ["blue", "green", "pink", "red"]
SPAWN_COLORS = {
    "blue":   (80, 140, 255),
    "green":  (80, 220, 120),
    "pink":   (255, 140, 200),
    "red":    (240, 80, 80),
    "pacman": (255, 220, 0),
}

# 4 對配對的視覺化線條配色
PAIR_COLORS = [
    (255, 100, 100),
    (255, 180, 60),
    (100, 180, 255),
    (180, 100, 255),
]

# 視窗版面
WINDOW_W, WINDOW_H = 1400, 800
SIDEBAR_W = 220
MAP_AREA_X = SIDEBAR_W + 10
MAP_AREA_Y = 50
MAP_AREA_W = WINDOW_W - MAP_AREA_X - 10
MAP_AREA_H = WINDOW_H - MAP_AREA_Y - 80  # 底部留 80px 給 status bar


# ─── 資料結構 ─────────────────────────────────────────────────────────────────
def empty_map(rows=18, cols=32):
    """產生一張全空地（外圈牆）的預設關卡。"""
    tiles = []
    for r in range(rows):
        if r == 0 or r == rows - 1:
            tiles.append("W" * cols)
        else:
            tiles.append("W" + "." * (cols - 2) + "W")
    return {
        "name": "untitled",
        "tile_size": 60,
        "rows": rows,
        "cols": cols,
        "tiles": tiles,
        "spawns": {
            "blue":   [1, 1],
            "green":  [rows - 2, cols - 2],
            "pink":   [1, cols - 2],
            "red":    [rows - 2, 1],
            "pacman": [rows // 2, cols // 2],
        },
        "charge_stations": {
            "blue":   [rows // 2 - 2, cols // 2 - 4],
            "green":  [rows // 2 + 2, cols // 2 + 4],
            "pink":   [rows // 2 - 2, cols // 2 + 4],
            "red":    [rows // 2 + 2, cols // 2 - 4],
        },
        "button_gate_map": [],
    }


def _ensure_schema(data):
    """補齊舊地圖可能缺少的欄位（charge_stations），避免 KeyError。"""
    defaults = empty_map(data.get("rows", 18), data.get("cols", 32))["charge_stations"]
    data.setdefault("charge_stations", {})
    for k in STATION_KEYS:
        data["charge_stations"].setdefault(k, defaults[k])
    return data


def load_map_file(name):
    """從 maps/<name>.json 載入，找不到時回傳空關卡。

    一律把 data["name"] 對齊傳入的檔名，確保「開哪個檔就存哪個檔」，
    避免複製地圖後因 name 欄位殘留而 Ctrl+S 誤蓋到別張圖。
    """
    path = os.path.join(MAPS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        print(f"[Editor] {path} not found, starting from empty map")
        data = empty_map()
        data["name"] = name
        return data
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["name"] = name  # 對齊檔名，避免存檔時誤蓋到別張圖
    print(f"[Editor] loaded {path}")
    return _ensure_schema(data)


def save_map_file(data):
    """寫入 maps/<name>.json。tiles 與 spawns 保留人類友善排版。"""
    os.makedirs(MAPS_DIR, exist_ok=True)
    path = os.path.join(MAPS_DIR, f"{data['name']}.json")
    # 自訂排版：tiles 一行一列、spawns 一行一鍵、button_gate_map 一行一筆
    tile_lines = ",\n    ".join(json.dumps(row) for row in data["tiles"])
    spawn_lines = ",\n    ".join(
        f'"{k}": {json.dumps(data["spawns"][k])}' for k in SPAWN_KEYS
    )
    station_lines = ",\n    ".join(
        f'"{k}": {json.dumps(data["charge_stations"][k])}' for k in STATION_KEYS
    )
    pair_lines = ",\n    ".join(
        json.dumps(entry, ensure_ascii=False) for entry in data["button_gate_map"]
    )
    text = (
        "{\n"
        f'  "name": {json.dumps(data["name"])},\n'
        f'  "tile_size": {data["tile_size"]},\n'
        f'  "rows": {data["rows"]},\n'
        f'  "cols": {data["cols"]},\n'
        f'  "tiles": [\n    {tile_lines}\n  ],\n'
        f'  "spawns": {{\n    {spawn_lines}\n  }},\n'
        f'  "charge_stations": {{\n    {station_lines}\n  }},\n'
        f'  "button_gate_map": [\n    {pair_lines}\n  ]\n'
        "}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[Editor] saved {path}")


def validate(data):
    """回傳 (警告列表, 迷霧數, 按鈕數, 閘門數)，用於 status bar 即時顯示（不擋存檔）。"""
    warnings = []
    tiles = data["tiles"]
    fog_count = sum(row.count("F") for row in tiles)
    # button / gate 數量配對檢查
    btn_count = sum(row.count("B") for row in tiles)
    gate_count = sum(row.count("G") for row in tiles)
    pair_count = len(data["button_gate_map"])
    if pair_count != btn_count or pair_count != gate_count:
        warnings.append(f"B={btn_count} G={gate_count} pairs={pair_count}")
    # 出生點與蓄能站都不能在牆上 / 出界
    checks = list(data["spawns"].items()) + [
        (f"{k} station", v) for k, v in data.get("charge_stations", {}).items()
    ]
    for k, (r, c) in checks:
        if 0 <= r < data["rows"] and 0 <= c < data["cols"]:
            if tiles[r][c] == "W":
                warnings.append(f"{k} on wall")
        else:
            warnings.append(f"{k} out of bounds")
    return warnings, fog_count, btn_count, gate_count


# ─── 編輯器主體 ───────────────────────────────────────────────────────────────
class MapEditor:
    def __init__(self, map_name):
        self.data = load_map_file(map_name)
        self.history = [deepcopy(self.data)]  # undo stack

        # 計算磚片格在螢幕上的尺寸（cell_size）與起始座標
        self._recompute_layout()

        # 目前選中的工具：("tile", char) 或 ("spawn", key) 或 ("pair", None)
        self.tool = ("tile", "W")
        # 配對工具暫存：記住已點的第一格（button 或 gate）
        self._pending_pair = None
        # 另存新檔（F2）的命名模式狀態
        self._naming = False
        self._name_buffer = ""

        # Pygame 物件
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption(f"Map Editor - {self.data['name']}")
        self.font = pygame.font.SysFont(None, 20)
        self.font_small = pygame.font.SysFont(None, 16)
        self.font_large = pygame.font.SysFont(None, 28)
        self.clock = pygame.time.Clock()

    def _recompute_layout(self):
        """根據目前地圖尺寸計算 cell_size 與繪製起點，讓地圖鋪滿可用區域。"""
        rows = self.data["rows"]
        cols = self.data["cols"]
        self.cell_size = min(MAP_AREA_W // cols, MAP_AREA_H // rows)
        map_pixel_w = self.cell_size * cols
        map_pixel_h = self.cell_size * rows
        self.map_origin_x = MAP_AREA_X + (MAP_AREA_W - map_pixel_w) // 2
        self.map_origin_y = MAP_AREA_Y + (MAP_AREA_H - map_pixel_h) // 2

    def push_history(self):
        """把目前狀態存入 undo stack，最多保留 50 步。"""
        self.history.append(deepcopy(self.data))
        if len(self.history) > 50:
            self.history.pop(0)

    def undo(self):
        if len(self.history) > 1:
            self.history.pop()
            self.data = deepcopy(self.history[-1])
            self._recompute_layout()

    # ── 滑鼠互動 ──────────────────────────────────────────────────────────────
    def screen_to_grid(self, mx, my):
        """螢幕座標 → (row, col)；若不在地圖上回傳 None。"""
        if mx < self.map_origin_x or my < self.map_origin_y:
            return None
        col = (mx - self.map_origin_x) // self.cell_size
        row = (my - self.map_origin_y) // self.cell_size
        if 0 <= row < self.data["rows"] and 0 <= col < self.data["cols"]:
            return int(row), int(col)
        return None

    def apply_tool_at(self, row, col):
        """根據目前工具對指定格子套用變更。"""
        kind, value = self.tool

        if kind == "tile":
            # 更換磚片：若原本是 button/gate 且有配對，要清掉配對
            old_char = self.data["tiles"][row][col]
            if old_char in ("B", "G") and value not in ("B", "G"):
                self._remove_pair_at(row, col)
            self.push_history()
            row_str = self.data["tiles"][row]
            self.data["tiles"][row] = row_str[:col] + value + row_str[col + 1:]

        elif kind == "spawn":
            # 把指定顏色的出生點移到該格
            self.push_history()
            self.data["spawns"][value] = [row, col]

        elif kind == "station":
            # 把指定顏色的蓄能站移到該格
            self.push_history()
            self.data.setdefault("charge_stations", {})[value] = [row, col]

        elif kind == "pair":
            self._handle_pair_click(row, col)

    def _handle_pair_click(self, row, col):
        """配對工具：第一次點記下，第二次點建立 button↔gate 配對。"""
        char = self.data["tiles"][row][col]
        if char not in ("B", "G"):
            return  # 只能點 button 或 gate

        if self._pending_pair is None:
            self._pending_pair = (row, col, char)
            return

        pr, pc, pchar = self._pending_pair
        if (pr, pc) == (row, col):
            self._pending_pair = None  # 同格取消
            return
        if pchar == char:
            # 同類型（兩個 B 或兩個 G）：把舊的取代為新的
            self._pending_pair = (row, col, char)
            return

        # 一 B 一 G 建立配對
        if pchar == "B":
            btn, gate = (pr, pc), (row, col)
        else:
            btn, gate = (row, col), (pr, pc)

        # 移除這個 button 或 gate 之前的任何配對，再加入新的
        self._remove_pair_at(*btn)
        self._remove_pair_at(*gate)
        self.push_history()
        self.data["button_gate_map"].append({
            "button": [btn[0], btn[1]],
            "gate":   [gate[0], gate[1]],
            "label":  f"pair {len(self.data['button_gate_map']) + 1}",
        })
        self._pending_pair = None

    def _remove_pair_at(self, row, col):
        """移除涉及指定格的所有配對（無論該格是 button 還是 gate）。"""
        self.data["button_gate_map"] = [
            e for e in self.data["button_gate_map"]
            if tuple(e["button"]) != (row, col) and tuple(e["gate"]) != (row, col)
        ]

    # ── 繪製 ──────────────────────────────────────────────────────────────────
    def draw(self):
        self.screen.fill((30, 30, 40))
        self._draw_sidebar()
        self._draw_map()
        self._draw_pairs()
        self._draw_spawns()
        self._draw_stations()
        self._draw_status_bar()
        if self._naming:
            self._draw_naming_prompt()
        pygame.display.flip()

    def _draw_sidebar(self):
        x = 10
        y = 10
        # 每幀重建「可點擊區 → 工具」命中表，供 _handle_sidebar_click 使用（避免硬寫像素偏移）
        self._sidebar_hits = []
        title = self.font_large.render("Map Editor", True, (240, 240, 240))
        self.screen.blit(title, (x, y))
        y += 36

        # Tile 工具
        self.screen.blit(self.font.render("Tiles:", True, (180, 180, 180)), (x, y))
        y += 22
        for char, label, color in TILES:
            rect = pygame.Rect(x, y, SIDEBAR_W - 30, 26)
            pygame.draw.rect(self.screen, color, rect)
            if self.tool == ("tile", char):
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 3)
            text_color = (20, 20, 20) if char == "." else (240, 240, 240)
            self.screen.blit(self.font.render(f"{char}  {label}", True, text_color),
                             (x + 6, y + 5))
            self._sidebar_hits.append((rect, ("tile", char)))
            y += 30

        # 出生點工具
        y += 8
        self.screen.blit(self.font.render("Spawns (click -> place):", True, (180, 180, 180)), (x, y))
        y += 22
        for key in SPAWN_KEYS:
            rect = pygame.Rect(x, y, SIDEBAR_W - 30, 22)
            pygame.draw.rect(self.screen, SPAWN_COLORS[key], rect)
            if self.tool == ("spawn", key):
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 3)
            self.screen.blit(self.font.render(key, True, (20, 20, 20)), (x + 6, y + 3))
            self._sidebar_hits.append((rect, ("spawn", key)))
            y += 26

        # 蓄能站工具
        y += 8
        self.screen.blit(self.font.render("Charge stations:", True, (180, 180, 180)), (x, y))
        y += 22
        for key in STATION_KEYS:
            rect = pygame.Rect(x, y, SIDEBAR_W - 30, 22)
            pygame.draw.rect(self.screen, SPAWN_COLORS[key], rect)
            if self.tool == ("station", key):
                pygame.draw.rect(self.screen, (255, 255, 255), rect, 3)
            self.screen.blit(self.font.render(f"{key} station", True, (20, 20, 20)), (x + 6, y + 3))
            self._sidebar_hits.append((rect, ("station", key)))
            y += 26

        # 配對工具
        y += 8
        rect = pygame.Rect(x, y, SIDEBAR_W - 30, 26)
        pygame.draw.rect(self.screen, (120, 90, 160), rect)
        if self.tool[0] == "pair":
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3)
        self.screen.blit(self.font.render("Pair (B<->G)", True, (240, 240, 240)), (x + 6, y + 5))
        self._sidebar_hits.append((rect, ("pair", None)))
        y += 38

        # 動作說明（鍵盤快捷鍵）
        self.screen.blit(self.font.render("[Ctrl+S] Save", True, (220, 220, 220)), (x, y))
        y += 20
        self.screen.blit(self.font.render("[Ctrl+Z] Undo", True, (220, 220, 220)), (x, y))
        y += 20
        self.screen.blit(self.font.render("[Ctrl+N] New",  True, (220, 220, 220)), (x, y))
        y += 20
        self.screen.blit(self.font.render("[F2] Save As", True, (220, 220, 220)), (x, y))
        y += 20
        self.screen.blit(self.font_small.render(f"File: {self.data['name']}.json",
                                                True, (160, 160, 160)), (x, y))

    def _draw_map(self):
        cs = self.cell_size
        for r in range(self.data["rows"]):
            for c in range(self.data["cols"]):
                char = self.data["tiles"][r][c]
                color = next((col for ch, _, col in TILES if ch == char), (100, 100, 100))
                rect = pygame.Rect(self.map_origin_x + c * cs,
                                   self.map_origin_y + r * cs, cs, cs)
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, (50, 50, 60), rect, 1)
                # 標記字（B/G/S/F 在格中央標字母）
                if char in ("B", "G", "S", "F"):
                    label = self.font_small.render(char, True, (20, 20, 20))
                    self.screen.blit(label, (rect.x + cs // 2 - 4, rect.y + cs // 2 - 6))

    def _draw_pairs(self):
        """畫 button ↔ gate 的虛線連線，4 對輪流套不同顏色。"""
        cs = self.cell_size
        for i, entry in enumerate(self.data["button_gate_map"]):
            color = PAIR_COLORS[i % len(PAIR_COLORS)]
            br, bc = entry["button"]
            gr, gc = entry["gate"]
            bx = self.map_origin_x + bc * cs + cs // 2
            by = self.map_origin_y + br * cs + cs // 2
            gx = self.map_origin_x + gc * cs + cs // 2
            gy = self.map_origin_y + gr * cs + cs // 2
            self._draw_dashed_line(color, (bx, by), (gx, gy))

        # 配對工具的「pending」提示：在已點選的格上加閃爍框
        if self._pending_pair:
            pr, pc, _ = self._pending_pair
            rect = pygame.Rect(self.map_origin_x + pc * cs,
                               self.map_origin_y + pr * cs, cs, cs)
            pygame.draw.rect(self.screen, (255, 255, 100), rect, 3)

    def _draw_dashed_line(self, color, start, end, dash=6):
        """畫虛線。pygame 沒有原生虛線函式，用一段段短線實作。"""
        import math as _math
        x1, y1 = start
        x2, y2 = end
        length = _math.hypot(x2 - x1, y2 - y1)
        if length < 1:
            return
        steps = max(1, int(length / dash))
        for i in range(0, steps, 2):
            t1 = i / steps
            t2 = min(1.0, (i + 1) / steps)
            sx, sy = x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1
            ex, ey = x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2
            pygame.draw.line(self.screen, color, (sx, sy), (ex, ey), 2)

    def _draw_spawns(self):
        """以彩色小圓 + 標籤畫出 5 個出生點。"""
        cs = self.cell_size
        for key in SPAWN_KEYS:
            r, c = self.data["spawns"][key]
            color = SPAWN_COLORS[key]
            cx = self.map_origin_x + c * cs + cs // 2
            cy = self.map_origin_y + r * cs + cs // 2
            pygame.draw.circle(self.screen, color, (cx, cy), max(4, cs // 3))
            pygame.draw.circle(self.screen, (20, 20, 20), (cx, cy), max(4, cs // 3), 2)
            label = self.font_small.render(key[0].upper(), True, (20, 20, 20))
            self.screen.blit(label, (cx - 4, cy - 6))

    def _draw_stations(self):
        """以彩色空心環 + 'C' 標籤畫出 4 個蓄能站（與出生點的實心圓區隔）。"""
        cs = self.cell_size
        for key in STATION_KEYS:
            station = self.data.get("charge_stations", {}).get(key)
            if not station:
                continue
            r, c = station
            color = SPAWN_COLORS[key]
            cx = self.map_origin_x + c * cs + cs // 2
            cy = self.map_origin_y + r * cs + cs // 2
            rad = max(5, cs // 3)
            pygame.draw.circle(self.screen, color, (cx, cy), rad, 3)        # 空心環
            pygame.draw.circle(self.screen, (20, 20, 20), (cx, cy), rad, 1)
            label = self.font_small.render("C", True, color)
            self.screen.blit(label, (cx - 4, cy - 6))

    def _draw_status_bar(self):
        warnings, fogs, btns, gates = validate(self.data)
        y = WINDOW_H - 60
        pygame.draw.rect(self.screen, (20, 20, 30),
                         (0, y, WINDOW_W, 60))
        info = (f"Fog: {fogs}  |  Buttons: {btns}  |  Gates: {gates}  |  "
                f"Pairs: {len(self.data['button_gate_map'])}  |  "
                f"Stations: {len(self.data.get('charge_stations', {}))}")
        self.screen.blit(self.font.render(info, True, (220, 220, 220)), (12, y + 8))

        if warnings:
            warn_text = "  ".join(f"! {w}" for w in warnings)
            color = (255, 180, 80)
        else:
            warn_text = "OK  map valid"
            color = (140, 220, 140)
        self.screen.blit(self.font.render(warn_text, True, color), (12, y + 32))

    # ── 主迴圈 ────────────────────────────────────────────────────────────────
    def run(self):
        running = True
        mouse_held = False  # 支援按住拖拉刷磚片
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                # 命名模式（F2 另存新檔）優先攔截所有按鍵，避免打字觸發快捷鍵
                if self._naming:
                    self._handle_naming_key(event)
                    continue

                if event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_F2:
                        # 進入「另存新檔」：預填目前名稱，可改成新名稱另存成新檔
                        self._naming = True
                        self._name_buffer = self.data["name"]
                    elif event.key == pygame.K_s and (mods & pygame.KMOD_CTRL):
                        save_map_file(self.data)
                    elif event.key == pygame.K_z and (mods & pygame.KMOD_CTRL):
                        self.undo()
                    elif event.key == pygame.K_n and (mods & pygame.KMOD_CTRL):
                        self.push_history()
                        name = self.data["name"]
                        self.data = empty_map()
                        self.data["name"] = name
                        self._recompute_layout()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mouse_held = True
                        self._handle_click(*event.pos)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        mouse_held = False
                elif event.type == pygame.MOUSEMOTION and mouse_held:
                    # 按住拖拉只用於 tile 工具（持續刷格）
                    if self.tool[0] == "tile":
                        grid = self.screen_to_grid(*event.pos)
                        if grid:
                            r, c = grid
                            # 不重複 push_history，拖拉視為單次操作
                            row_str = self.data["tiles"][r]
                            self.data["tiles"][r] = row_str[:c] + self.tool[1] + row_str[c + 1:]

            self.draw()
            self.clock.tick(60)

        pygame.quit()

    def _handle_naming_key(self, event):
        """另存新檔（F2）命名模式的按鍵處理：打字 → Enter 存成新檔 / Esc 取消。"""
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            new_name = self._sanitize_name(self._name_buffer)
            if new_name:
                self.data["name"] = new_name
                save_map_file(self.data)   # 存成 maps/<new_name>.json（新檔，不動原檔）
                pygame.display.set_caption(f"Map Editor - {new_name}")
            self._naming = False
        elif event.key == pygame.K_ESCAPE:
            self._naming = False  # 取消，不存檔
        elif event.key == pygame.K_BACKSPACE:
            self._name_buffer = self._name_buffer[:-1]
        else:
            ch = getattr(event, "unicode", "")
            # 只收安全的檔名字元：英數、底線、減號
            if ch and (ch.isalnum() or ch in "_-"):
                self._name_buffer += ch

    @staticmethod
    def _sanitize_name(name):
        """過濾成安全檔名（只留英數 / 底線 / 減號），避免奇怪字元或路徑符號。"""
        return "".join(c for c in name.strip() if c.isalnum() or c in "_-")

    def _draw_naming_prompt(self):
        """命名模式時，畫一個置中的「另存新檔」輸入框。"""
        w, h = 540, 130
        x = (WINDOW_W - w) // 2
        y = (WINDOW_H - h) // 2
        pygame.draw.rect(self.screen, (20, 20, 35), (x, y, w, h))
        pygame.draw.rect(self.screen, (200, 200, 220), (x, y, w, h), 2)
        title = self.font_large.render("Save As (new file)", True, (240, 240, 240))
        self.screen.blit(title, (x + 16, y + 12))
        # 輸入框 + 目前輸入內容（加底線游標）
        box = pygame.Rect(x + 16, y + 54, w - 32, 32)
        pygame.draw.rect(self.screen, (40, 40, 60), box)
        pygame.draw.rect(self.screen, (160, 160, 200), box, 1)
        shown = self._sanitize_name(self._name_buffer)
        self.screen.blit(self.font.render(f"{shown}_.json", True, (255, 255, 255)),
                         (box.x + 8, box.y + 7))
        hint = self.font_small.render("Enter = save new file    Esc = cancel    (a-z  0-9  _  -)",
                                      True, (170, 170, 170))
        self.screen.blit(hint, (x + 16, y + 96))

    def _handle_click(self, mx, my):
        # 1. 工具列點擊
        if mx < SIDEBAR_W:
            self._handle_sidebar_click(mx, my)
            return
        # 2. 地圖點擊
        grid = self.screen_to_grid(mx, my)
        if grid:
            self.apply_tool_at(*grid)

    def _handle_sidebar_click(self, mx, my):
        """用 _draw_sidebar 每幀建立的命中表，判定點到哪個工具按鈕。"""
        for rect, tool in getattr(self, "_sidebar_hits", []):
            if rect.collidepoint(mx, my):
                self.tool = tool
                self._pending_pair = None
                return


def main():
    map_name = sys.argv[1] if len(sys.argv) > 1 else "level_default"
    editor = MapEditor(map_name)
    editor.run()


if __name__ == "__main__":
    main()

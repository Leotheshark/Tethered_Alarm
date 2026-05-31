"""
Dodge Knives 小遊戲邏輯模組。

基於 Reverse Pac-Man 的地圖與實體框架實作：
- 玩家在迷宮中移動並躲避隨機生成的飛刀。
- 保留了按鈕開啟閘門的機制，可用於切換逃生路徑。
"""

import json
import math
import os
import pygame

from games.base_game import BaseLogicInterface
from entities import Ghost, PLAYER_SPEED, ColorButton
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（飼料/得分點）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）

# ─── 地圖定義（17 * 32） ────────────────────────────────
MAP_LAYOUT = [
#    0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 0
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 1
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 2
    [W, E, W, E, W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 3
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 4
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 5
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 6
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 7
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 8
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 9
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 10
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 11
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 12
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 13
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 14
    [W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W],  # 15
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 16
#    0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
]

ROWS = len(MAP_LAYOUT)
COLS = len(MAP_LAYOUT[0])
TILE_SIZE = 60
AVATAR_SIZE = 24
BUTTON_HOLD_TIME = 2.5  # 玩家需要踩在按鈕上的總秒數

SPAWN_TILES = {
    "blue":  (3, 3),
    "green": (13, 28),
    "pink":  (3, 28),
    "red":   (13, 3),
}

# 按鈕位置與顏色配置
BUTTON_CONFIGS = [
    {"pos": (3, 3), "color": "blue"},
    {"pos": (13, 28), "color": "green"},
    {"pos": (3, 28), "color": "pink"},
    {"pos": (13, 3), "color": "red"},
]

# ─── 遊戲數值常數 ─────────────────────────────────────────────────────────────

def tile_center(row, col):
    x = col * TILE_SIZE + TILE_SIZE // 2
    y = row * TILE_SIZE + TILE_SIZE // 2
    return x, y

def pixel_to_tile(px, py):
    col = int(px / TILE_SIZE)
    row = int(py / TILE_SIZE)
    return row, col

def is_wall(tile_map, row, col):
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return True
    t = tile_map[row][col]
    return t == W

class PlayerState(Ghost):
    def __init__(self, color, spawn_row, spawn_col):
        super().__init__(color_key=color, avatar_size=AVATAR_SIZE)
        cx, cy = tile_center(spawn_row, spawn_col)
        self.x, self.y = float(cx), float(cy)
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    @property
    def speed(self):
        return getattr(self, '_base_speed', PLAYER_SPEED)

    @speed.setter
    def speed(self, value):
        self._base_speed = value

class DodgeKnives(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list, sound_manager):
        super().__init__(socket_client, player_id_list, sound_manager)
        self.local_color = socket_client.player_color
        self.local_pid = socket_client.player_id
        # 採用 network 的單一真值源（server roster 指定；debug 路徑由 engine 以顏色 fallback 設好），
        # 不再自行用顏色硬猜，避免重連/缺色時授權錯配。
        self.is_authority = bool(getattr(socket_client, "is_authority", self.local_color == "blue"))

        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.buttons = []

        colors = ["blue", "green", "pink", "red"]
        self.players = {}
        for i, pid in enumerate(player_id_list):
            color = colors[i % len(colors)]
            sr, sc = SPAWN_TILES.get(color, (1, 1))
            self.players[color] = PlayerState(color, sr, sc)

        self._cleared = False
        self._input_dx = 0
        self._input_dy = 0
        self._rescuing_target = None

    def on_enter(self, params: dict = None):
        super().on_enter(params)
        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.buttons.clear()
        for cfg in BUTTON_CONFIGS:
            rx, ry = tile_center(*cfg["pos"])
            btn = ColorButton(rx, ry, cfg["color"])
            btn.activated_time = 0
            self.buttons.append(btn)

        for color, p in self.players.items():
            sr, sc = SPAWN_TILES.get(color, (1, 1))
            cx, cy = tile_center(sr, sc)
            p.x, p.y = float(cx), float(cy)
            reset_sync_state(p.sync, float(cx), float(cy))
            p.is_alive = True
            p.visual_key = f"{p.color_key}_{p.direction}"
        self._cleared = False
        print("[DodgeKnives] game entered")

    def on_exit(self):
        super().on_exit()
        print("[DodgeKnives] game exited")

    def handle_event(self, event_data: dict):
        etype = event_data.get("type")
        if etype == "move":
            self._input_dx = event_data.get("dx", 0)
            self._input_dy = event_data.get("dy", 0)

    def update(self, dt: float):
        if not self.is_active: return

        # 更新通關動畫計時器
        self._update_clear_animation(dt)
        if self.is_cleared():
            return

        local = self.players.get(self.local_color)
        if local and local.is_alive and not self.is_input_locked:
            # 收集其他玩家的碰撞矩形（包含倒地者），使其成為物理障礙
            other_rects = [p.rect for c, p in self.players.items() if c != self.local_color]
            local.move(self._input_dx, self._input_dy, dt, TILE_SIZE, 
                               is_wall_cb=lambda px, py: is_wall(self.tile_map, *pixel_to_tile(px, py)),
                               others=other_rects)

        for p in self.players.values():
            p.update(dt)  # 驅動動畫影格計時

        # 讓所有玩家都計算計時器，這樣每個人都能看到進度條動畫
        for btn in self.buttons:
            if btn.is_triggered:
                continue
            
            # 檢查對應顏色的玩家是否正踩在上面（所有客戶端都有玩家同步位置）
            owner = self.players.get(btn.assigned_color)
            on_button = (owner and owner.is_alive and btn.rect.colliderect(owner.rect))
            
            if on_button:
                btn.charge_timer = min(BUTTON_HOLD_TIME, btn.charge_timer + dt)
                # 只有授權端負責判定「完成」
                if self.is_authority and not btn.is_triggered and btn.charge_timer >= BUTTON_HOLD_TIME:
                        btn.is_triggered = True
                        btn.activated_time = pygame.time.get_ticks()
                        self.sound_manager.play("charged")
                        self.socket_client.send_game_event({
                            "type": "button_activated", "color": btn.assigned_color
                        })
            else:
                # 沒人踩時進度條緩慢後退
                btn.charge_timer = max(0.0, btn.charge_timer - dt * 2)

        # 檢查是否所有按鈕都點亮 (僅在非動畫期間觸發)
        if self.clear_anim_stage == 0:
            if all(b.is_triggered for b in self.buttons):
                self.trigger_clear_sequence()

        # 遠端同步
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE, COLS * TILE_SIZE - AVATAR_SIZE, ROWS * TILE_SIZE - AVATAR_SIZE)
        for color, p in self.players.items():
            if color != self.local_color:
                tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

    def get_render_data(self) -> dict:
        return {
            "tile_map": self.tile_map,
            "tile_size": TILE_SIZE,
            "clear_anim": self._get_clear_anim_data(),
            "buttons": [
                {
                    "x": b.x, "y": b.y, 
                    "color": b.assigned_color, 
                    "progress": b.charge_timer / BUTTON_HOLD_TIME,
                    "triggered": b.is_triggered,
                    "activated_time": getattr(b, "activated_time", 0)
                } for b in self.buttons
            ],
            "players": {
                color: {
                    "x": p.x, "y": p.y, "is_alive": p.is_alive,
                    "avatar_size": p.avatar_size,
                    "visual_key": p.visual_key,
                    "frame_index": p.frame_index
                } for color, p in self.players.items()
            }
        }

    def is_cleared(self) -> bool:
        return self._cleared

    def get_sync_data(self) -> dict:
        local = self.players.get(self.local_color)
        if not local: return {}
        return {
            "type": "player_pos", "color": self.local_color,
            "x": local.x, "y": local.y, "dx": local.current_dx, "dy": local.current_dy
        }

    def receive_sync_data(self, data: dict):
        dtype = data.get("type")
        if dtype == "player_pos":
            color = data.get("color")
            p = self.players.get(color)
            if p and color != self.local_color:
                rdx, rdy = data.get("dx", 0.0), data.get("dy", 0.0)
                # 更新遠端玩家的動畫朝向
                if rdx > 0: p.direction = "right"
                elif rdx < 0: p.direction = "left"
                elif rdy != 0: p.direction = "frontback"
                else: p.direction = "idle"
                p.visual_key = f"{p.color_key}_{p.direction}"

                if rdx != 0 and rdy != 0: rdx, rdy = rdx*0.7071, rdy*0.7071
                apply_server_update(p.sync, data.get("x"), data.get("y"), rdx, rdy)

        elif dtype == "button_activated":
            btn_color = data.get("color")
            for b in self.buttons:
                if b.assigned_color == btn_color:
                    b.is_triggered = True
                    self.sound_manager.play("charged")
                    b.activated_time = pygame.time.get_ticks()

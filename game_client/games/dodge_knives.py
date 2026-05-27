"""
Dodge Knives 小遊戲邏輯模組。

基於 Reverse Pac-Man 的地圖與實體框架實作：
- 玩家在迷宮中移動並躲避隨機生成的飛刀。
- 保留了按鈕開啟閘門的機制，可用於切換逃生路徑。
- 被飛刀擊中後需隊友在原地按 E 救援。
"""

import json
import math
import os
import time
from collections import deque

from games.base_game import BaseLogicInterface
from entities import Ghost, PLAYER_SPEED
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（飼料/得分點）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）

# ─── 地圖定義（與 Reverse Pac-Man 相同） ────────────────────────────────
MAP_LAYOUT = [
    [W] * 40,
    *([[W] + [E] * 38 + [W]] * 19),
    [W] * 40
]

ROWS = len(MAP_LAYOUT)
COLS = len(MAP_LAYOUT[0])
TILE_SIZE = 32
AVATAR_SIZE = 14

SPAWN_TILES = {
    "blue":  (1, 1),
    "green": (19, 38),
    "pink":  (1, 38),
    "red":   (19, 1),
}

# ─── 遊戲數值常數 ─────────────────────────────────────────────────────────────
MAX_RESCUES         = 2
RESCUE_RADIUS       = 50
RESCUE_HOLD_TIME    = 2.0
DEBUFF_DURATION     = 10.0
SPIKE_SLOW_DURATION = 3.0

BUTTON_GATE_MAP = {}

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
    return t == W or t == G

class PlayerState(Ghost):
    def __init__(self, color, spawn_row, spawn_col):
        self.alive = True
        self.rescue_count = 0
        self.debuff_timer = 0.0
        self.spike_timer = 0.0
        self.rescue_progress = 0.0
        self.being_rescued = False

        super().__init__(color_key=color, avatar_size=AVATAR_SIZE)
        cx, cy = tile_center(spawn_row, spawn_col)
        self.x, self.y = float(cx), float(cy)
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

    @property
    def speed(self):
        if not self.alive: return 0.0
        base = getattr(self, '_base_speed', PLAYER_SPEED)
        if self.debuff_timer > 0 or self.spike_timer > 0:
            base *= 0.5
        return base

    @speed.setter
    def speed(self, value):
        self._base_speed = value

    @property
    def permanently_down(self):
        return not self.alive and self.rescue_count >= MAX_RESCUES

class DodgeKnives(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list):
        super().__init__(socket_client, player_id_list)
        self.local_color = socket_client.player_color
        self.local_pid = socket_client.player_id
        self.is_authority = bool(player_id_list) and (self.local_pid == player_id_list[0])

        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.open_gates = set()
        self.pellets_remaining = sum(1 for row in self.tile_map for t in row if t == P)

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
        self.open_gates.clear()
        for color, p in self.players.items():
            sr, sc = SPAWN_TILES.get(color, (1, 1))
            cx, cy = tile_center(sr, sc)
            p.x, p.y = float(cx), float(cy)
            reset_sync_state(p.sync, float(cx), float(cy))
            p.alive = True
            p.rescue_count = 0
            p.rescue_progress = 0.0
            p.being_rescued = False
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
        elif etype == "rescue_start":
            self._rescuing_target = self._find_rescue_target()
            if self._rescuing_target:
                target = self.players.get(self._rescuing_target)
                if target:
                    target.being_rescued = True
                    target.rescue_progress = 0.0
                self.socket_client.send_game_event({"type": "rescue_progress_start", "color": self._rescuing_target})
        elif etype == "rescue_stop":
            if self._rescuing_target:
                target = self.players.get(self._rescuing_target)
                if target:
                    target.being_rescued = False
                    target.rescue_progress = 0.0
                self.socket_client.send_game_event({"type": "rescue_progress_stop", "color": self._rescuing_target})
            self._rescuing_target = None

    def update(self, dt: float):
        if not self.is_active or self._cleared: return

        local = self.players.get(self.local_color)
        if local and local.alive:
            # 收集其他玩家的碰撞矩形（包含倒地者），使其成為物理障礙
            other_rects = [p.rect for c, p in self.players.items() if c != self.local_color]
            local.move(self._input_dx, self._input_dy, dt, TILE_SIZE, 
                               is_wall_cb=lambda px, py: is_wall(self.tile_map, *pixel_to_tile(px, py)),
                               others=other_rects)
            self._handle_tile_interaction(local)

        for p in self.players.values():
            p.update(dt)  # 驅動動畫影格計時
            if p.debuff_timer > 0: p.debuff_timer -= dt
            if p.spike_timer > 0: p.spike_timer -= dt

        # 遠端同步
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE, COLS * TILE_SIZE - AVATAR_SIZE, ROWS * TILE_SIZE - AVATAR_SIZE)
        for color, p in self.players.items():
            if color != self.local_color:
                tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

        # 處理救援
        if self._rescuing_target:
            target = self.players.get(self._rescuing_target)
            if target and not target.alive and math.hypot(local.x - target.x, local.y - target.y) <= RESCUE_RADIUS:
                target.rescue_progress += dt
                if target.rescue_progress >= RESCUE_HOLD_TIME:
                    target.alive = True
                    target.rescue_count += 1
                    target.debuff_timer = DEBUFF_DURATION
                    target.being_rescued = False
                    rescued_color = self._rescuing_target
                    self._rescuing_target = None
                    self.socket_client.send_game_event({
                        "type": "player_rescued", "color": rescued_color, "rescue_count": target.rescue_count
                    })
            else:
                # 超出範圍或無效，重設
                if target: target.being_rescued = False
                self.socket_client.send_game_event({"type": "rescue_progress_stop", "color": self._rescuing_target})
                self._rescuing_target = None

        for color, p in self.players.items():
            if color != self._rescuing_target and p.being_rescued:
                p.rescue_progress = min(p.rescue_progress + dt, RESCUE_HOLD_TIME)

        if self.is_authority:
            self._evaluate_gates()

    def get_render_data(self) -> dict:
        return {
            "tile_map": self.tile_map,
            "tile_size": TILE_SIZE,
            "pellets_left": self.pellets_remaining,
            "players": {
                color: {
                    "x": p.x, "y": p.y, "alive": p.alive,
                    "permanently_down": p.permanently_down,
                    "rescue_progress": p.rescue_progress,
                    "rescue_count": p.rescue_count,
                    "debuff": p.debuff_timer > 0,
                    "spike": p.spike_timer > 0,
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
                # 更新遠端玩家的動畫朝向與狀態
                p.state = "WALK" if (rdx != 0 or rdy != 0) else "IDLE"
                if rdx > 0: p.direction = "right"
                elif rdx < 0: p.direction = "left"
                p.visual_key = f"{p.color_key}_{p.direction}"

                if rdx != 0 and rdy != 0: rdx, rdy = rdx*0.7071, rdy*0.7071
                apply_server_update(p.sync, data.get("x"), data.get("y"), rdx, rdy)

        elif dtype == "gate_state":
            new_open = {tuple(g) for g in data.get("open_gates", [])}
            for gr, gc in (new_open - self.open_gates): self.tile_map[gr][gc] = E
            for gr, gc in (self.open_gates - new_open):
                self.tile_map[gr][gc] = G
                self._push_players_off_gate(gr, gc)
            self.open_gates = new_open

        elif dtype == "player_rescued":
            color = data.get("color")
            p = self.players.get(color)
            if p:
                p.alive = True
                p.rescue_count = data.get("rescue_count")
                p.debuff_timer = DEBUFF_DURATION
                p.being_rescued = False

        elif dtype == "rescue_progress_start":
            p = self.players.get(data.get("color"))
            if p: p.being_rescued = True

        elif dtype == "rescue_progress_stop":
            p = self.players.get(data.get("color"))
            if p: p.being_rescued = False; p.rescue_progress = 0.0

    def _handle_tile_interaction(self, player):
        r, c = pixel_to_tile(player.x, player.y)
        if r < 0 or r >= ROWS or c < 0 or c >= COLS: return
        tile = self.tile_map[r][c]
        if tile == P:
            self.tile_map[r][c] = E
            self.pellets_remaining -= 1
            self.socket_client.send_game_event({"type": "pellet_eaten", "tile": [r, c]})
        elif tile == S:
            player.spike_timer = SPIKE_SLOW_DURATION

    def _evaluate_gates(self):
        pressed_buttons = set()
        for p in self.players.values():
            if not p.alive: continue
            r, c = pixel_to_tile(p.x, p.y)
            if (r, c) in BUTTON_GATE_MAP: pressed_buttons.add((r, c))

        should_open = {BUTTON_GATE_MAP[btn] for btn in pressed_buttons}
        if should_open == self.open_gates: return

        for gr, gc in (should_open - self.open_gates): self.tile_map[gr][gc] = E
        for gr, gc in (self.open_gates - should_open):
            self.tile_map[gr][gc] = G
            self._push_players_off_gate(gr, gc)
        
        self.open_gates = should_open
        self.socket_client.send_game_event({"type": "gate_state", "open_gates": [list(g) for g in self.open_gates]})

    def _push_players_off_gate(self, gr, gc):
        neighbors = [(gr - 1, gc), (gr + 1, gc), (gr, gc - 1), (gr, gc + 1)]
        for p in self.players.values():
            pr, pc = pixel_to_tile(p.x, p.y)
            if (pr, pc) == (gr, gc):
                for nr, nc in neighbors:
                    if not is_wall(self.tile_map, nr, nc):
                        p.x, p.y = tile_center(nr, nc)
                        reset_sync_state(p.sync, p.x, p.y)
                        break

    def _find_rescue_target(self) -> str | None:
        local = self.players.get(self.local_color)
        for color, p in self.players.items():
            if color == self.local_color: continue
            if not p.alive and not p.permanently_down:
                if math.hypot(local.x - p.x, local.y - p.y) <= RESCUE_RADIUS:
                    return color
        return None
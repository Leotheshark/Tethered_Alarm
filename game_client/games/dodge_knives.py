"""
Dodge Knives 小遊戲邏輯模組。

基於 Reverse Pac-Man 的地圖與實體框架實作：
- 玩家在迷宮中移動並躲避隨機生成的飛刀。
- 保留了按鈕開啟閘門的機制，可用於切換逃生路徑。
"""

import json
import math
import os
import random
import pygame

from entities import Entity, Ghost, PLAYER_SPEED, ColorButton
from games.base_game import BaseLogicInterface
from sync_helpers import RemoteSyncState, apply_server_update, reset_sync_state, tick_remote_sync

# ─── 地圖磚片類型常數 ───────────────────────────────────────────────────────────
W = 0   # Wall（牆壁）
E = 1   # Empty（空地）
P = 2   # Pellet（飼料/得分點）
G = 3   # Gate（閘門，初始關閉）
B = 4   # Button（按鈕，踩下開啟對應閘門）
S = 5   # Spike（釘板，踩上後速度減半 3 秒）
F = 6   # Fog（迷霧陷阱，踩到後本地視野縮小數秒）
# ─── 地圖定義（18 * 32） ────────────────────────────────
MAP_LAYOUT = [
  #  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 0
    [W, E, E, E, W, B, W, W, W, W, W, W, E, E, E, W, E, E, E, E, E, E, E, E, W, E, E, F, E, E, E, W],  # 1
    [W, E, E, E, W, E, W, W, W, W, W, W, E, W, E, W, E, W, E, E, E, E, E, E, W, E, E, F, E, E, E, W],  # 2
    [W, E, E, E, W, E, F, E, E, E, E, F, E, W, E, E, E, W, E, W, W, W, E, E, W, E, E, F, E, E, E, W],  # 3
    [W, W, G, W, W, G, W, W, W, W, W, W, W, W, W, W, W, W, E, W, E, G, E, E, W, E, E, F, F, F, F, W],  # 4
    [W, E, E, E, W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W, F, W, E, E, E, E, E, E, E, E, E, W],  # 5
    [W, E, E, E, W, E, E, E, E, E, W, F, W, W, W, W, W, W, W, W, E, W, E, E, E, E, E, E, E, E, E, W],  # 6
    [W, E, E, E, F, E, E, E, E, E, W, E, W, W, W, W, W, W, W, W, E, W, W, W, W, W, W, W, W, W, E, W],  # 7
    [W, E, W, W, W, W, W, W, W, W, W, E, W, W, W, E, E, E, B, E, G, E, E, E, E, E, E, E, E, E, E, W],  # 8
    [W, E, E, E, E, E, E, E, E, E, E, G, E, B, E, E, E, W, W, W, E, W, W, W, W, W, W, W, W, W, E, W],  # 9
    [W, E, W, W, W, W, W, W, W, W, W, E, W, W, W, W, W, W, W, W, E, W, E, E, E, E, E, F, E, E, E, W],  # 10
    [W, E, E, E, E, E, E, E, E, E, W, E, W, W, W, W, W, W, W, W, F, W, E, E, E, E, E, W, E, E, E, W],  # 11
    [W, E, E, E, E, E, E, E, E, E, W, F, W, E, E, E, E, E, E, E, E, E, E, E, E, E, E, W, E, E, E, W],  # 12
    [W, F, F, F, F, E, E, W, E, E, G, E, W, E, W, W, W, W, W, W, W, W, W, W, W, W, G, W, W, G, W, W],  # 13
    [W, E, E, E, F, E, E, W, E, E, W, W, W, E, W, E, E, E, W, E, F, E, E, E, E, F, E, W, E, E, E, W],  # 14
    [W, E, E, E, F, E, E, W, E, E, E, E, E, E, W, E, W, E, W, E, W, W, W, W, W, W, E, W, E, E, E, W],  # 15
    [W, E, E, E, F, E, E, W, E, E, E, E, E, E, E, E, W, E, E, E, W, W, W, W, W, W, B, W, E, E, E, W],  # 16
    [W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W, W],  # 17
#    0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
]

ROWS = len(MAP_LAYOUT)
COLS = len(MAP_LAYOUT[0])
TILE_SIZE = 60
AVATAR_SIZE = 24
BUTTON_HOLD_TIME = 10  # 玩家需要踩在按鈕上的總秒數
KNIFE_SPEED = 800
INITIAL_SPAWN_INTERVAL = 20.0
MIN_SPAWN_INTERVAL = 10.0
DEFEAT_VOTE_TIME = 30.0
WARNING_DURATION = 10.0
RESCUE_RADIUS = 70
RESCUE_HOLD_TIME = 2.0

SPAWN_TILES = {
    "blue":  (8, 15),
    "green": (9, 15),
    "pink":  (8, 16),
    "red":   (9, 16),
}

# 按鈕位置與顏色配置
BUTTON_CONFIGS = [
    {"pos": (9, 16), "color": "red"},
    {"pos": (8, 15), "color": "blue"},
    {"pos": (9, 15), "color": "green"},
    {"pos": (8, 16), "color": "pink"},
]
# BUTTON_CONFIGS = [
#     {"pos": (2, 2), "color": "red"},
#     {"pos": (15, 29), "color": "blue"},
#     {"pos": (2, 29), "color": "green"},
#     {"pos": (15, 2), "color": "pink"},
# ]

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
    return t == W or t == G

class PlayerState(Ghost):
    def __init__(self, color, spawn_row, spawn_col):
        super().__init__(color_key=color, avatar_size=AVATAR_SIZE)
        cx, cy = tile_center(spawn_row, spawn_col)
        self.x, self.y = float(cx), float(cy)
        self.sync = RemoteSyncState(target_x=float(cx), target_y=float(cy))

class Knife(Entity):
    def __init__(self, x, y, direction, speed):
        # 根據移動方向選擇對應的視覺資源 (knife_up, knife_down, knife_left, knife_right)
        super().__init__(x, y, visual_key=f"knife_{direction}")
        self.direction = direction
        self.speed = speed
        self.width = 30  # 30x30px 碰撞箱
        self.height = 30
        self.is_active = True
        self.fade_timer = 0.0 # 用於撞擊後的淡出計時

    def update(self, dt):
        if self.is_active:
            if self.direction == "left": self.x -= self.speed * dt
            elif self.direction == "right": self.x += self.speed * dt
            elif self.direction == "up": self.y -= self.speed * dt
            elif self.direction == "down": self.y += self.speed * dt
        elif self.fade_timer > 0:
            # 撞擊閘門後進入淡出階段
            self.fade_timer = max(0.0, self.fade_timer - dt)

class DodgeKnives(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list, sound_manager):
        super().__init__(socket_client, player_id_list, sound_manager)
        self.local_color = socket_client.player_color
        self.local_pid = socket_client.player_id
        # 採用 network 的單一真值源（server roster 指定；debug 路徑由 engine 以顏色 fallback 設好），
        # 不再自行用顏色硬猜，避免重連/缺色時授權錯配。
        self.is_authority = bool(getattr(socket_client, "is_authority", self.local_color == "blue"))

        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.gate_coords = []
        self.button_coords = []
        self.open_gates = set()
        self._any_gate_pressed = False
        self.buttons = []

        colors = ["blue", "green", "pink", "red"]
        self.players = {}
        for i, pid in enumerate(player_id_list):
            color = colors[i % len(colors)]
            sr, sc = SPAWN_TILES.get(color, (1, 1))
            self.players[color] = PlayerState(color, sr, sc)

        # 飛刀管理清單
        self.active_knives: list[Knife] = []

        # 飛刀生成管理 (僅授權端計算)
        self._spawn_timer = INITIAL_SPAWN_INTERVAL
        self._current_interval = INITIAL_SPAWN_INTERVAL
        self._next_direction = "left"
        self._warning_active = False
        self._last_countdown_int = -1 # 用於偵測倒數數字變化以播放音效

        # 失敗投票
        self._voting = False
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False
        self._failed = False

        self._rescue_progress = {} # { color: { "progress": float, "rescuer": color, "being_rescued": bool } }

        self._cleared = False
        self._input_dx = 0
        self._input_dy = 0
        self._rescuing_target = None
        
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0
        self.is_input_locked = True

    @property
    def is_voting(self) -> bool:
        return self._voting

    def on_enter(self, params: dict = None):
        super().on_enter(params)
        self.tile_map = [row[:] for row in MAP_LAYOUT]
        self.gate_coords = []
        self.button_coords = []
        for r in range(ROWS):
            for c in range(COLS):
                t = self.tile_map[r][c]
                if t == G: self.gate_coords.append((r, c))
                if t == B: self.button_coords.append((r, c))
        self.buttons.clear()
        for cfg in BUTTON_CONFIGS:
            rx, ry = tile_center(*cfg["pos"])
            btn = ColorButton(rx, ry, cfg["color"])
            btn.activated_time = 0
            self.buttons.append(btn)

        self.active_knives.clear()

        self._current_interval = INITIAL_SPAWN_INTERVAL
        self._spawn_timer = self._current_interval
        self._next_direction = random.choice(["up", "down", "left", "right"])
        self._last_countdown_int = -1
        self._warning_active = False
        self._rescue_progress.clear()

        for color, p in self.players.items():
            sr, sc = SPAWN_TILES.get(color, (1, 1))
            cx, cy = tile_center(sr, sc)
            p.x, p.y = float(cx), float(cy)
            reset_sync_state(p.sync, float(cx), float(cy))
            p.is_alive = True
            p.visual_key = f"{p.color_key}_{p.direction}"
        self._cleared = False
        self.open_gates.clear()

        # 重置計時與旗標
        self._failed = False
        self._voting = False
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False
        self._any_gate_pressed = False
        self.start_anim_stage = 1
        self.start_anim_timer = 0.0
        self.is_input_locked = True
        print("[DodgeKnives] game entered")

    def on_exit(self):
        super().on_exit()
        print("[DodgeKnives] game exited")

    def handle_event(self, event_data: dict):
        etype = event_data.get("type")

        # 失敗投票階段：只接受投票，且每人只投一次。
        if self._voting:
            if etype == "vote" and not self._local_voted:
                value = bool(event_data.get("value"))
                self._local_voted = True
                self._apply_vote(self.local_color, value)
                try:
                    self.socket_client.send_game_event({
                        "type": "vote_cast", "color": self.local_color, "value": value,
                    })
                except Exception as e:
                    print(f"[DodgeKnives] vote_cast broadcast failed: {e}")
            return  # 投票期間凍結其餘輸入

        if etype == "move":
            self._input_dx = event_data.get("dx", 0)
            self._input_dy = event_data.get("dy", 0)

    def update(self, dt: float):
        if not self.is_active or self._failed:
            return

        # 失敗投票階段：凍結遊戲邏輯
        if self._voting:
            self._update_defeat_vote(dt)
            return

        # 開場動畫邏輯
        if getattr(self, "start_anim_stage", 0) > 0 and self.start_anim_stage < 5:
            self.start_anim_timer += dt
            if self.start_anim_stage == 1 and self.start_anim_timer >= 1.0:
                self.start_anim_stage = 2
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 2 and self.start_anim_timer >= 0.3:
                self.start_anim_stage = 3
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 3 and self.start_anim_timer >= 1.5:
                self.start_anim_stage = 4
                self.start_anim_timer = 0.0
            elif self.start_anim_stage == 4 and self.start_anim_timer >= 0.3:
                self.start_anim_stage = 5
                self.start_anim_timer = 0.0
                self.is_input_locked = False
            
            # 開場期間仍需更新動畫影格（讓角色不會卡在呆板的姿勢）
            for p in self.players.values():
                p.update(dt)
            return

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
            
            # 處理地圖互動 (釘板 S, 迷霧 F)
            tr, tc = pixel_to_tile(local.x, local.y)
            if 0 <= tr < ROWS and 0 <= tc < COLS:
                t = self.tile_map[tr][tc]
                if t == S: # Spike
                    local.spike_timer = 3.0
                elif t == F: # Fog
                    if local.fog_timer <= 0:
                        self.sound_manager.play("blind")
                    local.fog_timer = 2.5

        for p in self.players.values():
            p.update(dt)  # 驅動動畫影格計時
            if p.spike_timer > 0:
                p.spike_timer = max(0.0, p.spike_timer - dt)
            if p.fog_timer > 0:
                p.fog_timer = max(0.0, p.fog_timer - dt)

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
                btn.charge_timer = max(0.0, btn.charge_timer - dt * 0.2)

        # 檢查是否所有按鈕都點亮 (僅在非動畫期間觸發)
        if self.clear_anim_stage == 0:
            if all(b.is_triggered for b in self.buttons):
                self.trigger_clear_sequence()

        # 飛刀倒數計時器更新 (所有端皆更新以確保倒數平滑)
        if not self.is_input_locked and self.clear_anim_stage == 0:
            self._spawn_timer -= dt
            # 偵測倒數數字變化以播放音效 (僅在預警啟動時執行)
            if self._warning_active:
                current_countdown_int = int(self._spawn_timer)
                if current_countdown_int != self._last_countdown_int and current_countdown_int >= 0:
                    self.sound_manager.play("countdown")
                    # 授權端廣播音效，確保所有玩家同步聽到
                    if self.is_authority:
                        self.socket_client.send_game_event({"type": "sfx_trigger", "sfx": "countdown"})
                    self._last_countdown_int = current_countdown_int

        # 飛刀生成邏輯 (僅授權端負責計時與派發)
        if self.is_authority and self.clear_anim_stage == 0 and not self.is_input_locked:
            
            # 檢查是否進入預警階段 (生成前 10 秒)
            if self._spawn_timer <= WARNING_DURATION and not self._warning_active:
                self._warning_active = True
                self._broadcast_warning_state(True)

            # 檢查是否到達生成時間
            if self._spawn_timer <= 0:
                self._spawn_knives(self._next_direction)
                # 廣播生成事件給其他玩家
                self._broadcast_spawn_event(self._next_direction)
                
                # 更新下一次生成的參數
                self._current_interval = max(MIN_SPAWN_INTERVAL, self._current_interval - 1.0)
                self._spawn_timer = self._current_interval
                self._next_direction = random.choice(["up", "down", "left", "right"])
                self._warning_active = False
                self._last_countdown_int = -1
                self._broadcast_warning_state(False)

        # 更新飛刀位置與移除逻辑
        for kn in self.active_knives[:]:
            kn.update(dt)
            # 簡單移除邏輯：飛出地圖外一定距離或淡出結束則刪除
            if kn.is_active:
                if kn.x < -100 or kn.x > COLS * TILE_SIZE + 100 or kn.y < -100 or kn.y > ROWS * TILE_SIZE + 100:
                    self.active_knives.remove(kn)
            elif kn.fade_timer <= 0:
                self.active_knives.remove(kn)

        # 碰撞偵測 (移至更新位置後執行，且所有端都執行閘門判定，防止網路延遲導致穿越)
        if self.clear_anim_stage == 0:
            self._check_knife_collisions()

        # 救援邏輯更新 (本地偵測並推進)
        if not self.is_input_locked:
            self._update_rescues(dt)

        # 壓力板閘門評估 (僅在非動畫期間觸發)
        if self.is_authority and self.clear_anim_stage == 0:
            self._evaluate_gates()
            # 檢查失敗判定
            self._check_win_and_fail()

        # 遠端同步
        map_bounds = (AVATAR_SIZE, AVATAR_SIZE, COLS * TILE_SIZE - AVATAR_SIZE, ROWS * TILE_SIZE - AVATAR_SIZE)
        for color, p in self.players.items():
            if color != self.local_color:
                tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

    def _check_win_and_fail(self):
        """authority 偵測失敗（四人同時倒地），並廣播。"""
        if self._failed or self._voting or self.clear_anim_stage != 0:
            return
        present = list(self.players.values())
        if not present:
            return

        # 失敗：所有在場玩家同時倒地 -> 進入失敗投票階段
        if all(not p.is_alive for p in present):
            print("[DodgeKnives] all players down -> defeat vote")
            self._start_defeat_vote()
            try:
                self.socket_client.send_game_event({"type": "defeat_vote_start"})
            except Exception as e:
                print(f"[DodgeKnives] defeat_vote_start broadcast failed: {e}")

    def _start_defeat_vote(self):
        self._voting = True
        self._vote_timer = 0.0
        self._votes = {}
        self._local_voted = False

    def _update_defeat_vote(self, dt: float):
        self._vote_timer += dt
        if not self.is_authority:
            return

        present = list(self.players.values())
        all_voted = len(self._votes) >= len(present) and len(present) > 0
        timed_out = self._vote_timer >= DEFEAT_VOTE_TIME
        if not (all_voted or timed_out):
            return

        # 結算
        if any(self._votes.values()):
            print("[DodgeKnives] defeat vote -> CONTINUE")
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "continue"})
            except Exception as e:
                print(f"[DodgeKnives] vote_result(continue) broadcast failed: {e}")
            self.on_enter()
        else:
            print("[DodgeKnives] defeat vote -> ABORT")
            self._failed = True
            self._voting = False
            try:
                self.socket_client.send_game_event({"type": "vote_result", "value": "abort"})
                self.socket_client.send_surrender()
            except Exception as e:
                print(f"[DodgeKnives] vote_result(abort)/surrender failed: {e}")

    def _apply_vote(self, color, value):
        if color in self.players:
            self._votes[color] = bool(value)

    def _check_knife_collisions(self):
        """處理飛刀與閘門、玩家的碰撞"""
        for kn in self.active_knives:
            if not kn.is_active:
                continue

            # 1. 檢查閘門碰撞 (使用矩形碰撞，感應更精確)
            hit_gate = False
            r_start, c_start = pixel_to_tile(kn.rect.left, kn.rect.top)
            r_end, c_end = pixel_to_tile(kn.rect.right, kn.rect.bottom)
            for r in range(r_start, r_end + 1):
                for c in range(c_start, c_end + 1):
                    if 0 <= r < ROWS and 0 <= c < COLS and self.tile_map[r][c] == G:
                        gate_rect = pygame.Rect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                        if kn.rect.colliderect(gate_rect):
                            hit_gate = True
                            break
                if hit_gate: break

            if hit_gate:
                self._stop_knife(kn)
                continue

            # 2. 檢查玩家碰撞 (飛刀會穿透玩家)
            if self.is_authority:
                for p in self.players.values():
                    if not p.is_alive:
                        continue
                    if kn.rect.colliderect(p.rect):
                        self._catch_player(p)

    def _stop_knife(self, kn):
        """停止飛刀移動並啟動淡出"""
        kn.is_active = False
        kn.width = 0  # 移除碰撞箱
        kn.height = 0
        kn.fade_timer = 1.0

    def _catch_player(self, player: PlayerState):
        """玩家被擊中倒地"""
        if not player.is_alive: return
        player.is_alive = False
        player.visual_key = "dead"
        self.sound_manager.play("eat")
        try:
            self.socket_client.send_game_event({
                "type": "player_caught",
                "color": player.color_key,
            })
        except: pass

    def _update_rescues(self, dt):
        """處理本地玩家發起的救援行為"""
        local = self.players.get(self.local_color)
        if not local or not local.is_alive or self.is_input_locked:
            return

        for color, target in self.players.items():
            if color == self.local_color or target.is_alive:
                continue

            if color not in self._rescue_progress:
                self._rescue_progress[color] = {"progress": 0.0, "rescuer": None, "being_rescued": False}
            
            state = self._rescue_progress[color]
            dist = math.hypot(local.x - target.x, local.y - target.y)
            in_range = dist <= RESCUE_RADIUS

            if in_range and not state["being_rescued"]:
                state["being_rescued"] = True
                state["rescuer"] = self.local_color
                state["progress"] = 0.0
                self.socket_client.send_game_event({"type": "rescue_progress_start", "color": color})

            if state["being_rescued"]:
                if in_range:
                    state["progress"] += dt
                    if state["progress"] >= RESCUE_HOLD_TIME:
                        # 救援完成
                        target.is_alive = True
                        state["progress"] = 0.0
                        state["being_rescued"] = False
                        self.socket_client.send_game_event({
                            "type": "player_rescued",
                            "color": color,
                            "rescuer": self.local_color
                        })
                else:
                    state["being_rescued"] = False
                    state["progress"] = 0.0
                    self.socket_client.send_game_event({"type": "rescue_progress_stop", "color": color})

    def _spawn_knives(self, direction):
        """在指定方向生成一整排飛刀"""
        if direction == "left":
            spawn_x = COLS * TILE_SIZE + 50
            for r in range(ROWS):
                _, spawn_y = tile_center(r, 0)
                self.active_knives.append(Knife(spawn_x, spawn_y, "left", KNIFE_SPEED))
        elif direction == "right":
            spawn_x = -50
            for r in range(ROWS):
                _, spawn_y = tile_center(r, 0)
                self.active_knives.append(Knife(spawn_x, spawn_y, "right", KNIFE_SPEED))
        elif direction == "up":
            spawn_y = ROWS * TILE_SIZE + 50
            for c in range(COLS):
                spawn_x, _ = tile_center(0, c)
                self.active_knives.append(Knife(spawn_x, spawn_y, "up", KNIFE_SPEED))
        elif direction == "down":
            spawn_y = -50
            for c in range(COLS):
                spawn_x, _ = tile_center(0, c)
                self.active_knives.append(Knife(spawn_x, spawn_y, "down", KNIFE_SPEED))

    def _broadcast_spawn_event(self, direction):
        """通知所有玩家生成飛刀"""
        try:
            self.socket_client.send_game_event({
                "type": "knife_spawn",
                "direction": direction
            })
        except: pass

    def _broadcast_warning_state(self, active):
        """同步預警狀態"""
        try:
            # 若 active 為 True，帶上方向；若為 False 則清空
            self.socket_client.send_game_event({
                "type": "knife_warning",
                "active": active,
                "direction": self._next_direction if active else None,
                "timer": self._spawn_timer
            })
        except: pass

    def _evaluate_gates(self):
        any_pressed = False
        for p in self.players.values():
            if not p.is_alive:
                continue
            r, c = pixel_to_tile(p.x, p.y)
            if (r, c) in self.button_coords:
                any_pressed = True
                break

        if any_pressed != self._any_gate_pressed:
            self._any_gate_pressed = any_pressed
            sfx = "button_in" if any_pressed else "button_out"
            self.sound_manager.play(sfx)
            try:
                self.socket_client.send_game_event({"type": "sfx_trigger", "sfx": sfx})
            except: pass

        should_open = set(self.gate_coords) if any_pressed else set()
        newly_open = should_open - self.open_gates
        newly_closed = self.open_gates - should_open

        if not newly_open and not newly_closed:
            return

        for gr, gc in newly_open:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = E
        for gr, gc in newly_closed:
            if 0 <= gr < ROWS and 0 <= gc < COLS:
                self.tile_map[gr][gc] = G
                self._push_players_off_gate(gr, gc)

        self.open_gates = should_open
        try:
            self.socket_client.send_game_event({
                "type": "gate_state",
                "open_gates": [list(g) for g in self.open_gates],
            })
        except: pass

    def _push_players_off_gate(self, gr, gc):
        gate_rect = pygame.Rect(gc * TILE_SIZE, gr * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        potential_neighbors = [(gr - 1, gc), (gr + 1, gc), (gr, gc - 1), (gr, gc + 1)]
        for p in self.players.values():
            if not p.is_alive: continue
            if p.rect.colliderect(gate_rect):
                best_neighbor_tile = None
                min_distance_sq = float('inf')

                for nr, nc in potential_neighbors:
                    if 0 <= nr < ROWS and 0 <= nc < COLS and not is_wall(self.tile_map, nr, nc):
                        nx, ny = tile_center(nr, nc)
                        dist_sq = (p.x - nx)**2 + (p.y - ny)**2
                        if dist_sq < min_distance_sq:
                            min_distance_sq = dist_sq
                            best_neighbor_tile = (nr, nc)
                
                if best_neighbor_tile:
                    nx, ny = tile_center(*best_neighbor_tile)
                    p.x, p.y = float(nx), float(ny)
                    reset_sync_state(p.sync, p.x, p.y)

    def get_render_data(self) -> dict:
        local = self.players.get(self.local_color)
        return {
            "tile_map": self.tile_map,
            "tile_size": TILE_SIZE,
            "clear_anim": self._get_clear_anim_data(),
            "warning": {
                "active": self._warning_active,
                "direction": self._next_direction,
                "timer": self._spawn_timer
            },
            "fog_active": bool(local and local.fog_timer > 0 and self.clear_anim_stage == 0),
            "fog_radius": 50,
            "start_anim": {"stage": getattr(self, "start_anim_stage", 0), "timer": getattr(self, "start_anim_timer", 0.0)},
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
                    "rescue_progress": self._get_rescue_progress(color),
                    "avatar_size": p.avatar_size, 
                    "visual_key": p.visual_key,
                    "frame_index": p.frame_index
                } for color, p in self.players.items()
            },
            "knives": [
                {
                    "x": kn.x, "y": kn.y,
                    "visual_key": kn.visual_key,
                    "fade_timer": kn.fade_timer,
                    "is_active": kn.is_active
                } for kn in self.active_knives
            ],
            "defeat_vote": {
                "active":      self._voting,
                "time_left":   max(0.0, DEFEAT_VOTE_TIME - self._vote_timer),
                "votes":       dict(self._votes),
                "local_voted": self._local_voted,
                "local_color": self.local_color,
            },
        }

    def _get_rescue_progress(self, color):
        if color in self._rescue_progress:
            return self._rescue_progress[color]["progress"] / RESCUE_HOLD_TIME
        return 0.0

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

        elif dtype == "player_caught":
            color = data.get("color")
            p = self.players.get(color)
            if p and p.is_alive:
                p.is_alive = False
                p.visual_key = "dead"
                self.sound_manager.play("eat")

        elif dtype == "player_rescued":
            color = data.get("color")
            p = self.players.get(color)
            if p and not p.is_alive:
                p.is_alive = True
                p.visual_key = f"{p.color_key}_idle"
                p.rescue_count += 1 # 救援次數增加導致永久減速

        elif dtype == "rescue_progress_start":
            color = data.get("color")
            if color not in self._rescue_progress:
                self._rescue_progress[color] = {"progress": 0.0, "rescuer": None, "being_rescued": False}
            self._rescue_progress[color]["being_rescued"] = True

        elif dtype == "rescue_progress_stop":
            color = data.get("color")
            if color in self._rescue_progress:
                self._rescue_progress[color]["being_rescued"] = False
                self._rescue_progress[color]["progress"] = 0.0

        elif dtype == "button_activated":
            btn_color = data.get("color")
            for b in self.buttons:
                if b.assigned_color == btn_color:
                    b.is_triggered = True
                    self.sound_manager.play("charged")
                    b.activated_time = pygame.time.get_ticks()

        elif dtype == "defeat_vote_start":
            if not self._voting:
                self._start_defeat_vote()
        elif dtype == "vote_cast":
            self._apply_vote(data.get("color"), data.get("value"))
        elif dtype == "vote_result":
            if data.get("value") == "continue":
                self.on_enter()
            else:
                self._failed = True
                self._voting = False

        elif dtype == "knife_spawn":
            # 非授權端接收到生成指令
            if not self.is_authority:
                self._spawn_knives(data.get("direction"))
                # 同步更新 Guest 端的小遊戲狀態變數，確保與 Authority 節奏一致
                self._current_interval = max(MIN_SPAWN_INTERVAL, self._current_interval - 1.0)
                self._spawn_timer = self._current_interval
                self._warning_active = False
        elif dtype == "knife_warning":
            # 非授權端接收到預警狀態同步
            if not self.is_authority:
                self._warning_active = data.get("active", False)
                self._next_direction = data.get("direction", self._next_direction)
                self._spawn_timer = data.get("timer", self._spawn_timer)
        elif dtype == "gate_state":
            new_open = {tuple(g) for g in data.get("open_gates", [])}
            newly_closed = self.open_gates - new_open
            newly_open = new_open - self.open_gates

            for gr, gc in newly_open:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = E
            for gr, gc in newly_closed:
                if 0 <= gr < ROWS and 0 <= gc < COLS:
                    self.tile_map[gr][gc] = G
                    self._push_players_off_gate(gr, gc)

            self.open_gates = new_open

        elif dtype == "sfx_trigger":
            sfx = data.get("sfx")
            if sfx:
                self.sound_manager.play(sfx)

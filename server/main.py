# --- 匯入需要的工具 ---
import asyncio
import os
import subprocess
import sys
import socket
import threading
import time
from datetime import datetime, timedelta

import socketio
import pygame
import uvicorn
import webview

from game_room import GameRoom
from system_helper import SystemHelper
from constants import ServerEvent # 引入伺服器事件常數

base_dir = os.path.dirname(os.path.abspath(__file__))

class ServerState:
    """保存伺服器執行期間的共享狀態。"""

    def __init__(self):
        self.rooms = {}
        self.monitor_started = False
        self.colors = ["blue", "green", "pink", "red"]
        self.alarm_updated_event = asyncio.Event()
        self.timeout_tasks = {}  # { (room_id, color): asyncio.Task }，追蹤斷線倒數任務
        self.uvicorn_server = None  # 持有 uvicorn.Server 以便退出時請求優雅關閉並釋放 5555 埠

        # 音效資源路徑
        self.bgm_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "bgm_loop.ogg")
        self.alarm_sound_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "Alarm_1.ogg")
        self.click_sound_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "click.ogg")
        self.all_ready_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "all_ready.ogg")
        self.alarm_test_sound = None
        self.alarm_real_sound = None
        self.all_ready_sound = None
        self.click_sound = None
        
        # 初始化音訊引擎
        pygame.mixer.init()

    def play_lobby_bgm(self):
        """播放大廳背景音樂 (由 Python 原生播放，不受瀏覽器限制)"""
        if os.path.exists(self.bgm_path) and not pygame.mixer.music.get_busy():
            pygame.mixer.music.load(self.bgm_path)
            pygame.mixer.music.set_volume(0.5)
            pygame.mixer.music.play(-1)  # -1 代表循環播放

    def stop_lobby_bgm(self):
        """停止背景音樂"""
        pygame.mixer.music.stop()

    def play_actual_alarm(self):
        """播放真正的鬧鐘響鈴（循環播放）"""
        try:
            if not self.alarm_real_sound and os.path.exists(self.alarm_sound_path):
                self.alarm_real_sound = pygame.mixer.Sound(self.alarm_sound_path)
            if self.alarm_real_sound:
                self.alarm_real_sound.play(loops=-1)  # -1 代表無限循環
        except Exception as e:
            print(f"[server] failed to play alarm: {e}")

    def stop_actual_alarm(self):
        """停止鬧鐘響鈴"""
        if self.alarm_real_sound:
            self.alarm_real_sound.stop()

    def resume_lobby_bgm(self):
        """恢復背景音樂 (用於測試音量後)"""
        pygame.mixer.music.unpause()

    def play_click(self):
        """播放按鈕點擊音效 (一次性播放)"""
        try:
            if not self.click_sound and os.path.exists(self.click_sound_path):
                self.click_sound = pygame.mixer.Sound(self.click_sound_path)
            
            if self.click_sound:
                # 點擊聲通常很短且頻繁，使用 play() 可以在多重連點時疊加播放
                self.click_sound.play()
        except Exception as e:
            print(f"[server] failed to play click sound: {e}")

    def play_all_ready(self):
        """播放全員準備完成音效"""
        try:
            if not self.all_ready_sound and os.path.exists(self.all_ready_path):
                self.all_ready_sound = pygame.mixer.Sound(self.all_ready_path)
            
            if self.all_ready_sound:
                self.all_ready_sound.play()
        except Exception as e:
            print(f"[server] failed to play all_ready sound: {e}")

    def play_test_alarm(self):
        """播放鬧鐘音效用於測試音量 (播放一次)"""
        try:
            if not self.alarm_test_sound and os.path.exists(self.alarm_sound_path):
                self.alarm_test_sound = pygame.mixer.Sound(self.alarm_sound_path)
            
            if self.alarm_test_sound:
                # 測試時先暫停背景音樂
                pygame.mixer.music.pause()
                self.alarm_test_sound.set_volume(0.5)
                self.alarm_test_sound.play()
                return self.alarm_test_sound.get_length()
        except Exception as e:
            print(f"[server] failed to play test alarm: {e}")
        return 0

state = ServerState()

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# 讓 pywebview 開啟同一個 ASGI app，同時提供 lobby HTML / CSS / JS。
app = socketio.ASGIApp(
    sio,
    static_files={
        "/": os.path.join(base_dir, "static", "index.html"),
        "/index.html": os.path.join(base_dir, "static", "index.html"),
        "/static": os.path.join(base_dir, "static"),
        "/assets": os.path.join(base_dir, "..", "game_client", "assets"),
    },
)


# --- 連線生命週期 ---
@sio.event
async def connect(sid, environ):
    """任一 client 連線時啟動鬧鐘監控背景任務。"""
    print(f"[server] connected: {sid}")
    if not state.monitor_started:
        sio.start_background_task(alarm_monitor)
        sio.start_background_task(hardware_monitor) # 啟動硬體即時監控任務
        state.monitor_started = True
    
    # 偵測硬體狀態並立即告知前端
    is_speaker = await asyncio.to_thread(SystemHelper.get_is_speaker)
    await sio.emit(ServerEvent.HARDWARE_STATUS, {"is_speaker": is_speaker}, to=sid)

@sio.event
async def disconnect(sid):
    """玩家或 game_client 離線時清理房間狀態並觸發斷線流程。"""
    print(f"[server] disconnected: {sid}")

    # 處理 lobby 玩家斷線
    for room_id, room in list(state.rooms.items()):
        if sid in room.players:
            if room.host_sid == sid:
                # 房主退出，直接關閉房間並通知剩餘玩家
                print(f"[room] host disconnected, closing room: {room_id}")
                await sio.emit(ServerEvent.ERROR_MSG, {"message": "Host disconnected. Room closed."}, room=room_id)
                state.rooms.pop(room_id)
                continue
            
            room.remove_player(sid)
            await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)

    # 處理 game_client 斷線：廣播通知並啟動 60 秒倒數
    for room_id, room in list(state.rooms.items()):
        if sid not in room.game_client_sids:
            continue
        color = room.game_client_sids.pop(sid)
        print(f"[server] game_client {sid} ({color}) disconnected from {room_id}")
        await sio.emit(ServerEvent.TEAMMATE_DISCONNECTED,
                       {"player_id": sid, "color": color}, room=room_id)
        task = asyncio.create_task(_teammate_timeout(room_id, color))
        state.timeout_tasks[(room_id, color)] = task
        break


def _is_room_member(room, sid):
    """判斷 sid 是否真的屬於該房（lobby 玩家或已訂閱的 game_client）。
    用於房間範疇事件的發送者驗證：阻止任意連線者（含帶錯 room_id 的 debug client）
    對不屬於自己的房間結束遊戲、注入偽造的位置/狀態封包。"""
    if room is None:
        return False
    return sid in room.players or sid in room.game_client_sids


async def _teammate_timeout(room_id, color):
    """60 秒後若隊友仍未重連，廣播 teammate_timeout 允許投降。"""
    await asyncio.sleep(60)
    print(f"[server] teammate_timeout: {color} in {room_id}")
    await sio.emit(ServerEvent.TEAMMATE_TIMEOUT, {"color": color}, room=room_id)
    state.timeout_tasks.pop((room_id, color), None)


# --- Lobby 玩家房間流程 ---
@sio.event
async def join_room(sid, data):
    """瀏覽器 lobby 玩家加入房間，並取得一個顏色與 player slot。"""
    room_id = data.get("room_id", "default")
    room = state.rooms.setdefault(room_id, GameRoom(room_id))

    if len(room.players) >= room.max_players:
        await sio.emit(ServerEvent.JOIN_FAILED, {"reason": "full"}, to=sid)
        return

    room.add_player(sid)

    await sio.enter_room(sid, room_id)
    await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)
    print(f"[room] {sid} joined {room_id}")

    # 房間滿 4 人時通知 game_client 可以訂閱這個房間。
    if len(room.players) == room.max_players:
        print(f"[room] {room_id} is full; assigning game client")
        await sio.emit(ServerEvent.ASSIGN_ROOM, {"room_id": room_id})


async def hardware_monitor():
    """背景任務：定期檢查硬體裝置，若狀態改變則廣播。"""
    print("[hardware] monitor started")
    last_status = None
    while True:
        # 取得當前輸出裝置是否為喇叭
        is_speaker = await asyncio.to_thread(SystemHelper.get_is_speaker)
        # 只有在狀態發生變化時才發送通知，減少通訊開銷
        if is_speaker != last_status:
            await sio.emit(ServerEvent.HARDWARE_STATUS, {"is_speaker": is_speaker})
            last_status = is_speaker
        # 每 1 秒輪詢一次，兼顧即時性與效能
        await asyncio.sleep(1)


@sio.event
async def player_ready(sid, data):
    """玩家按下 READY 時更新狀態；4 人皆 ready 後通知 lobby 倒數。"""
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    if not room or sid not in room.players:
        return

    room.players[sid]["ready"] = True
    await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)

    if len(room.players) == room.max_players and all(p["ready"] for p in room.players.values()):
        print(f"[room] all players ready in {room_id}")
        await sio.emit(ServerEvent.ALL_READY, {"countdown": 3}, room=room_id)


@sio.event
async def player_unready(sid, data):
    """玩家取消 READY 時同步房間狀態。"""
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    if not room or sid not in room.players:
        return

    room.players[sid]["ready"] = False
    await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)


# --- 鬧鐘流程 ---
async def alarm_monitor():
    """背景檢查所有房間的 alarm_time，時間到時廣播 alarm_triggered。"""
    print("[alarm] monitor started")
    while True:
        now = datetime.now()
        sleep_time = 60
        min_diff = 3600

        for room_id, room in list(state.rooms.items()):
            if not room.alarm_time:
                continue

            try:
                h, m = map(int, room.alarm_time.split(":"))
                alarm_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if alarm_dt < now:
                    alarm_dt += timedelta(days=1)

                diff = (alarm_dt - now).total_seconds()
                min_diff = min(min_diff, diff)

                if -30 < diff <= 59: # TODO: 記得改回來
                    print(f"[alarm] trigger room {room_id} at {room.alarm_time}")
                    room.is_triggered = True
                    await sio.emit(ServerEvent.ALARM_TRIGGERED, {"time": room.alarm_time}, room=room_id)
                    room.alarm_time = None
            except Exception as e:
                print(f"[alarm] invalid alarm in room {room_id}: {e}")

        if min_diff < 120:
            sleep_time = 1

        try:
            await asyncio.wait_for(state.alarm_updated_event.wait(), timeout=sleep_time)
            state.alarm_updated_event.clear()
        except asyncio.TimeoutError:
            pass


@sio.event
async def set_alarm(sid, data):
    """房主在 4 人到齊後設定鬧鐘時間。"""
    room_id = data.get("room_id")
    time_str = data.get("time")
    room = state.rooms.get(room_id)

    if not room:
        return

    if room.host_sid == sid and len(room.players) == room.max_players and not room.is_triggered:
        room.alarm_time = time_str
        state.alarm_updated_event.set()
        await sio.emit(ServerEvent.ALARM_SET, {"time": time_str}, room=room_id)
    else:
        reason = "Need four players before setting alarm" if len(room.players) < room.max_players else "Only host can set alarm"
        await sio.emit(ServerEvent.ERROR_MSG, {"message": reason}, to=sid)


@sio.event
async def test_alarm_sound(sid, data=None):
    """處理前端傳來的測試音量請求。"""
    print(f"[server] test_alarm_sound request from {sid}")
    duration = state.play_test_alarm()
    if duration > 0:
        await sio.emit(ServerEvent.TEST_ALARM_STATUS, {"status": "started"}, to=sid)
        # 等待音效播放結束
        await asyncio.sleep(duration)
        state.resume_lobby_bgm()
        await sio.emit(ServerEvent.TEST_ALARM_STATUS, {"status": "finished"}, to=sid)


@sio.event
async def start_game(sid, data):
    """倒數結束後由 lobby 通知同房間所有 client 進入遊戲，並指定要載入的小遊戲。"""
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    if room:
        # 隨機或固定選擇小遊戲；目前固定為 reverse_pacman
        minigame = "reverse_pacman"
        # 只記錄要玩的小遊戲，並重置派發旗標；此時 game_client 進程尚未啟動，
        # 真正的 START_MINIGAME（含權威玩家名單）延後到 4 個 game_client 都訂閱後
        # 由 _maybe_dispatch_minigame 統一派發一次，確保各 client 拿到一致的名單。
        room.current_minigame = minigame
        room.minigame_dispatched = False

        # GAME_STARTED 仍立即廣播：lobby 前端需要它來停鬧鐘、開遊戲視窗（launch game_client）。
        await sio.emit(ServerEvent.GAME_STARTED, {}, room=room_id)

@sio.event
async def game_cleared(sid, data):
    """小遊戲通關時，由同房 game_client 通知伺服器。"""
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    # 發送者驗證：只有該房成員能宣告通關，阻止外部端結束不屬於自己的房間。
    if not _is_room_member(room, sid):
        return
    print(f"[server] game cleared in {room_id}")
    # 廣播給房間所有人（包含大廳），理由為成功
    await sio.emit(ServerEvent.GAME_OVER, {"reason": "success"}, room=room_id)
    # 重置回大廳可重玩狀態，並重廣播 room_state 讓前端刷新（解除 isBusy → 房主可再設鬧鐘）
    room.reset_for_lobby()
    await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)


@sio.event
async def game_event(sid, data):
    """轉發小遊戲內的即時事件封包給同房其他所有 game_client（排除發送者）。"""
    room_id = data.get("room_id")
    # 發送者驗證：只轉發來自該房成員的封包，阻止外部端注入偽造的遊戲狀態。
    if not _is_room_member(state.rooms.get(room_id), sid):
        return
    await sio.emit(ServerEvent.GAME_EVENT, data, room=room_id, skip_sid=sid)


# --- Game client 房間訂閱流程 ---
@sio.event
async def request_game_room(sid, data):
    """game_client 詢問目前是否有可訂閱的滿員房間。"""
    # game_client 不是玩家，不加入 players，也不佔用顏色；只加入 Socket.IO room。
    # 這樣 alarm_triggered / game_started 仍會送到 Pygame 遊戲進程。
    for room_id, room in state.rooms.items():
        if len(room.players) == room.max_players:
            print(f"[game_client] assigning {sid} to room {room_id}")
            await sio.enter_room(sid, room_id) # 將 game_client 加入房間
            await sio.emit(ServerEvent.ASSIGN_ROOM, {"room_id": room_id}, to=sid) # 告知 game_client 房間 ID
            return
    print(f"[game_client] no full room available for {sid}")


@sio.event
async def subscribe_game_room(sid, data):
    """game_client 已知道 room_id 時，訂閱該房間的廣播事件。"""
    # join_room 是給 lobby 玩家用的，會建立 player 資料。
    # subscribe_game_room 只讓 pygame 視窗聽到同房間的 alarm/game 事件。
    room_id = data.get("room_id")
    if not room_id:
        await sio.emit(ServerEvent.ERROR_MSG, {"message": "room_id required"}, to=sid)
        return
    # DEBUG / 直連情境：若 room 尚未由 lobby 建立，這裡自動補建一個空房間
    # （只配置 game_client 訂閱所需的最小結構，不會佔用 player slot）
    room = state.rooms.get(room_id)
    if not room:
        room = state.rooms.setdefault(room_id, GameRoom(room_id))
        print(f"[game_client] auto-created room {room_id} on subscribe")

    await sio.enter_room(sid, room_id)

    # 顏色決策優先序：
    # 1) 同一 sid 重訂閱（重連 / change_room）→ 沿用既有顏色，絕不重新指派或遞增計數器，
    #    否則同一 client 會拿到兩個顏色、座位與權威判定分歧。
    # 2) 客戶端申報的顏色（來自大廳繼承）。
    # 3) 都沒有 → 用計數器依序指派（相容 debug 直連模式）。
    if sid in room.game_client_sids:
        color = room.game_client_sids[sid]
    else:
        color = data.get("player_color")
        if not color:
            color = state.colors[room.game_client_count % len(state.colors)]
            room.game_client_count += 1

    room.game_client_sids[sid] = color

    await sio.emit(ServerEvent.GAME_ROOM_SUBSCRIBED, {"room_id": room_id, "player_color": color}, to=sid)
    print(f"[game_client] {sid} subscribed to room {room_id} as {color}")

    # 每次有 game_client 訂閱後，檢查是否該派發 minigame（湊滿才發，且只發一次）。
    await _maybe_dispatch_minigame(room)


def _ordered_game_client_roster(room):
    """
    產出房間內 game_client 的權威名單，依顏色固定順序（blue→green→pink→red）排序。
    client 端用這份名單建立一致的 player_id_list，避免各自靠 presence 心跳猜而分歧。
    名單第一位（依顏色順序為 blue）標記 authority=True，作為 Pac-Man AI / 通關判定的
    權威端來源；client 不再各自用「顏色==blue」硬猜，避免重連或缺色時授權錯配。
    """
    color_rank = {"blue": 0, "green": 1, "pink": 2, "red": 3}
    roster = [{"sid": sid, "color": color} for sid, color in room.game_client_sids.items()]
    roster.sort(key=lambda e: (color_rank.get(e["color"], 99), e["sid"]))
    for i, entry in enumerate(roster):
        entry["authority"] = (i == 0)  # 排序後第一位為唯一授權端
    return roster


async def _maybe_dispatch_minigame(room):
    """
    當本局已選定小遊戲、且 4 個 game_client 都已訂閱時，對全房派發一次 START_MINIGAME，
    並夾帶權威玩家名單。只派發一次（minigame_dispatched 旗標），確保各 client 同步且一致。
    """
    if not room.current_minigame or room.minigame_dispatched:
        return
    if len(room.game_client_sids) < room.max_players:
        return  # 尚未湊滿全部 game_client，繼續等下一個訂閱

    room.minigame_dispatched = True
    roster = _ordered_game_client_roster(room)
    await sio.emit(
        ServerEvent.START_MINIGAME,
        {"game": room.current_minigame, "players": roster},
        room=room.room_id,
    )
    print(f"[game_client] dispatched start_minigame ({room.current_minigame}) with roster: {roster}")


# --- 玩家位置同步 ---
@sio.event
async def player_move(sid, data):
    """接收玩家位置封包並轉發給同房其他所有 game_client（排除發送者）。"""
    room_id = data.get("room_id")
    # 發送者驗證：只轉發來自該房成員的位置封包，阻止外部端注入偽造座標。
    if not _is_room_member(state.rooms.get(room_id), sid):
        return
    await sio.emit(ServerEvent.PLAYER_MOVE, data, room=room_id, skip_sid=sid)


# --- 投降流程 ---
@sio.event
async def surrender(sid, data):
    """同房成員選擇投降，廣播 game_over 給同房所有人。"""
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    # 發送者驗證：只有該房成員能結束本局，阻止任意連線者投降掉不屬於自己的房間。
    if not _is_room_member(room, sid):
        return
    print(f"[server] surrender from {sid} in {room_id}")
    await sio.emit(ServerEvent.GAME_OVER, {"reason": "surrender"}, room=room_id)
    # 重置回大廳可重玩狀態，並重廣播 room_state 讓前端刷新（解除 isBusy → 房主可再設鬧鐘）
    room.reset_for_lobby()
    await sio.emit(ServerEvent.ROOM_STATE, room.get_state(), room=room_id)


# --- 啟動與視窗管理 ---
def launch_game_client(room_id="default", server_url="http://127.0.0.1:5555", color="blue"):
    """啟動 game_client/main.py，並注入連線資訊與角色顏色。"""
    game_client_script = os.path.normpath(os.path.join(base_dir, "..", "game_client", "main.py"))
    if not os.path.exists(game_client_script):
        print("[server] game_client/main.py not found")
        return

    try:
        # 建立環境變數，讓 Pygame 進程繼承大廳的連線設定
        env = os.environ.copy()
        env["ROOM_ID"] = room_id
        env["SERVER_URL"] = server_url
        env["PLAYER_COLOR"] = color
        # 強制 Pygame 啟動後立即顯示視窗
        env["FORCE_START"] = "1"

        print(f"[server] launching game client for {color} in room {room_id}")
        subprocess.Popen(
            [sys.executable, game_client_script], 
            cwd=os.path.dirname(game_client_script),
            env=env
        )
    except Exception as e:
        print(f"[server] failed to launch game client: {e}")


def run_server():
    """在背景執行 Socket.IO ASGI server。

    持有 uvicorn.Server 物件（存入 state.uvicorn_server），讓退出時能請求優雅關閉、
    確實釋放 5555 埠，而不是靠 os._exit 硬殺、留下埠被殘留 socket 鎖住的風險。
    """
    config = uvicorn.Config(app, host="0.0.0.0", port=5555, log_level="error")
    server = uvicorn.Server(config)
    state.uvicorn_server = server
    server.run()


class LobbyAPI:
    """暴露給 JavaScript 呼叫的 Python API，用於控制 pywebview 視窗生命週期。"""
    def close_lobby(self):
        if webview.windows:
            webview.windows[0].destroy()

    def minimize_lobby(self):
        """縮小大廳視窗。"""
        if webview.windows:
            webview.windows[0].minimize()

    def restore_lobby(self):
        """恢復大廳視窗。"""
        if webview.windows:
            webview.windows[0].restore()

    def trigger_topmost(self):
        """鬧鐘響起時，由前端呼叫此 API 將本地視窗置頂。"""
        SystemHelper.set_webview_topmost()

    def launch_game_instance(self, room_id, server_url, color):
        """由前端通知啟動遊戲執行個體，並帶入目前大廳的連線參數。"""
        launch_game_client(room_id, server_url, color)

    def start_bgm(self):
        """由前端通知播放本地背景音樂。"""
        state.play_lobby_bgm()

    def stop_bgm(self):
        """由前端通知停止本地背景音樂。"""
        state.stop_lobby_bgm()

    def start_alarm_sound(self):
        """由前端通知播放本地鬧鐘音效。"""
        state.play_actual_alarm()

    def stop_alarm_sound(self):
        """由前端通知停止本地鬧鐘音效。"""
        state.stop_actual_alarm()

    def play_click_sound(self):
        """由前端通知播放按鈕點擊聲。"""
        state.play_click()

    def play_all_ready_sound(self):
        """由前端通知播放全員準備音效。"""
        state.play_all_ready()

    def test_alarm_local(self):
        """本地測試音效：不經過伺服器廣播，直接在本地進程播放。"""
        duration = state.play_test_alarm()
        if duration > 0:
            # 建立線程在播放完畢後自動恢復背景音樂
            def resume_after_delay():
                time.sleep(duration)
                state.resume_lobby_bgm()
            
            threading.Thread(target=resume_after_delay, daemon=True).start()
        return duration

    def get_tailscale_ip(self):
        """偵測並回傳本機的 Tailscale IP (100.x.y.z)。"""
        try:
            # 獲取本機主機名稱與所有關聯 IP
            hostname = socket.gethostname()
            ips = socket.gethostbyname_ex(hostname)[2]
            # 篩選出 Tailscale 專用的 100.x.y.z 網段
            for ip in ips:
                if ip.startswith("100."):
                    return ip
        except Exception as e:
            print(f"[server] Failed to detect Tailscale IP: {e}")
        return "127.0.0.1"


def start_window():
    """開啟 pywebview lobby 視窗，並掛載 LobbyAPI 供 JS 呼叫。"""
    # 根據環境變數決定 UI 載入位址，若無則預設為本地伺服器
    # 這允許 Guest 實例直接載入 Host 的頁面，避免單機測試時的連接埠衝突
    target_url = os.environ.get("SERVER_URL", "http://127.0.0.1:5555")

    webview.create_window(
        "Tethered Alarm",
        target_url,
        width=1000,
        height=700,
        resizable=False,
        js_api=LobbyAPI(),
    )
    webview.start(debug=False)


def cleanup():
    """退出前主動釋放關鍵資源，避免反覆開關時殘留導致下次啟動失敗。

    依序處理影響面最大的三項：
      1. 音訊引擎（pygame.mixer）：不 quit 會殘留佔用音訊裝置，下次 init 可能失敗。
      2. uvicorn server：請求優雅關閉以釋放 5555 埠，避免下次綁定撞 WinError 10048。
      3. 防休眠狀態：還原系統電源行為。
    每一步各自 try/except，確保一項失敗不影響其餘清理。
    """
    try:
        pygame.mixer.quit()
        print("[server] pygame.mixer released")
    except Exception as e:
        print(f"[server] mixer cleanup failed: {e}")

    try:
        if state.uvicorn_server is not None:
            state.uvicorn_server.should_exit = True  # 通知 uvicorn 主迴圈優雅收尾
            print("[server] requested uvicorn shutdown")
    except Exception as e:
        print(f"[server] uvicorn shutdown request failed: {e}")

    try:
        SystemHelper.restore_sleep()
    except Exception as e:
        print(f"[server] restore_sleep failed: {e}")


if __name__ == "__main__":
    # 1. 系統準備：防止休眠
    SystemHelper.prevent_sleep()

    # 2. 啟動伺服器邏輯 (僅在未設定 SKIP_SERVER 時執行)
    # 在單機多人測試 (debug_overall.py) 中，只有 Host 會啟動此線程
    if os.environ.get("SKIP_SERVER") != "1":
        print(f"[server] Starting Uvicorn on port 5555...")
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # 關鍵：給予 Uvicorn 一點時間完成初始化，避免 Webview 載入時伺服器尚未就緒
        time.sleep(1.0)

    print("[server] opening lobby window...")
    try:
        start_window()  # 阻塞直到 lobby 視窗關閉
    finally:
        # 不論正常關閉或例外，都先釋放資源再退出。
        cleanup()
        # 給 uvicorn 一點時間完成優雅關閉、釋放埠（daemon thread 不會擋退出）。
        time.sleep(0.5)
        # 仍以 os._exit 作最後保證：pygame/webview 殘留執行緒可能讓正常 exit 卡住不結束；
        # 但關鍵資源（音訊裝置、5555 埠）已於 cleanup() 主動釋放，不再靠硬殺善後。
        os._exit(0)

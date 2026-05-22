# --- 匯入需要的工具 ---
import asyncio
import os
import subprocess
import sys
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

        # 音效資源路徑
        self.bgm_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "bgm_loop.ogg")
        self.alarm_sound_path = os.path.join(base_dir, "..", "game_client", "assets", "sounds", "Alarm_1.ogg")
        self.alarm_test_sound = None
        
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

    def resume_lobby_bgm(self):
        """恢復背景音樂 (用於測試音量後)"""
        pygame.mixer.music.unpause()

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

    # 玩家連線時，由後端直接啟動音效播放
    state.play_lobby_bgm()


@sio.event
async def disconnect(sid):
    """玩家或 game_client 離線時清理房間狀態並觸發斷線流程。"""
    print(f"[server] disconnected: {sid}")

    # 處理 lobby 玩家斷線
    for room_id, room in list(state.rooms.items()):
        if sid in room.players:
            room.remove_player(sid)
            if not room.players:
                state.rooms.pop(room_id)
                continue
            if room.host_sid == sid:
                room.host_sid = next(iter(room.players))
                print(f"[room] host changed: {room.host_sid}")
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

                if -30 < diff <= 1:
                    print(f"[alarm] trigger room {room_id} at {room.alarm_time}")
                    await sio.emit(ServerEvent.ALARM_TRIGGERED, {"time": room.alarm_time}, room=room_id)
                    await asyncio.to_thread(SystemHelper.set_webview_topmost) # 鬧鐘響起時將視窗置頂
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

    if room.host_sid == sid and len(room.players) == room.max_players:
        room.alarm_time = time_str
        state.alarm_updated_event.set()
        state.stop_lobby_bgm()  # 鬧鐘設定完成後停止大廳音樂
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
        await sio.emit(ServerEvent.TEST_ALARM_STATUS, {"status": "started"})
        # 等待音效播放結束
        await asyncio.sleep(duration)
        state.resume_lobby_bgm()
        await sio.emit(ServerEvent.TEST_ALARM_STATUS, {"status": "finished"})


@sio.event
async def start_game(sid, data):
    """倒數結束後由 lobby 通知同房間所有 client 進入遊戲，並指定要載入的小遊戲。"""
    room_id = data.get("room_id")
    if room_id in state.rooms:
        await sio.emit(ServerEvent.GAME_STARTED, {}, room=room_id)
        # 隨機或固定選擇小遊戲；目前固定為 reverse_pacman
        await sio.emit(
            ServerEvent.START_MINIGAME,
            {"game": "reverse_pacman"},
            room=room_id,
        )


@sio.event
async def game_event(sid, data):
    """轉發小遊戲內的即時事件封包給同房其他所有 game_client（排除發送者）。"""
    room_id = data.get("room_id")
    if room_id:
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
    room = state.rooms.get(room_id)
    if not room:
        await sio.emit(ServerEvent.ERROR_MSG, {"message": "room not found"}, to=sid)
        return

    await sio.enter_room(sid, room_id)

    # 依訂閱順序指派顏色，讓每個 game_client 有唯一的角色顏色
    color = state.colors[room.game_client_count % len(state.colors)]
    room.game_client_count += 1

    room.game_client_sids[sid] = color

    await sio.emit(ServerEvent.GAME_ROOM_SUBSCRIBED, {"room_id": room_id, "player_color": color}, to=sid)
    print(f"[game_client] {sid} subscribed to room {room_id} as {color}")


# --- 玩家位置同步 ---
@sio.event
async def player_move(sid, data):
    """接收玩家位置封包並轉發給同房其他所有 game_client（排除發送者）。"""
    room_id = data.get("room_id")
    if room_id:
        await sio.emit(ServerEvent.PLAYER_MOVE, data, room=room_id, skip_sid=sid)


# --- 投降流程 ---
@sio.event
async def surrender(sid, data):
    """任一玩家選擇投降，廣播 game_over 給同房所有人。"""
    room_id = data.get("room_id")
    if room_id:
        print(f"[server] surrender from {sid} in {room_id}")
        await sio.emit(ServerEvent.GAME_OVER, {"reason": "surrender"}, room=room_id)


# --- 啟動與視窗管理 ---
def launch_game_client():
    """自動啟動 game_client/main.py；可用 AUTO_START_GAME_CLIENT=0 關閉。"""
    auto_start = os.environ.get("AUTO_START_GAME_CLIENT", "1")
    if auto_start == "0":
        print("[server] auto-start game client disabled")
        return

    game_client_script = os.path.normpath(os.path.join(base_dir, "..", "game_client", "main.py"))
    if not os.path.exists(game_client_script):
        print("[server] game_client/main.py not found")
        return

    try:
        print(f"[server] launching game client: {game_client_script}")
        subprocess.Popen([sys.executable, game_client_script], cwd=os.path.dirname(game_client_script))
    except Exception as e:
        print(f"[server] failed to launch game client: {e}")


def run_server():
    """在背景執行 Socket.IO ASGI server。"""
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="error")


class LobbyAPI:
    """暴露給 JavaScript 呼叫的 Python API，用於控制 pywebview 視窗生命週期。"""
    def close_lobby(self):
        if webview.windows:
            webview.windows[0].destroy()


def start_window():
    """開啟 pywebview lobby 視窗，並掛載 LobbyAPI 供 JS 呼叫。"""
    webview.create_window(
        "Tethered Alarm",
        "http://127.0.0.1:5000",
        width=1000,
        height=700,
        resizable=False,
        js_api=LobbyAPI(),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    SystemHelper.prevent_sleep()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(1)
    launch_game_client()

    print("[server] opening lobby window...")
    start_window()

    SystemHelper.restore_sleep()
    os._exit(0)

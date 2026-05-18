# --- 引入工具箱 ---
import socketio    # 處理即時通訊的工具 (就像電話線)
import uvicorn     # 啟動網頁伺服器的引擎 (就像發電機)
import os          # 處理檔案路徑的工具
import threading   # 用來同時執行伺服器與視窗
import asyncio     # 用來處理非同步的背景任務
from datetime import datetime, timedelta
import webview     # 負責產生「軟體外殼」視窗的工具
from game_room import GameRoom  # 引入我們自己寫的房間管理員
from system_helper import SystemHelper # 引入封裝後的系統工具

class ServerState:
    """集中管理伺服器狀態與旗標"""
    def __init__(self):
        self.rooms = {}
        self.monitor_started = False
        self.colors = ["blue", "green", "pink", "red"]
        self.alarm_updated_event = asyncio.Event()

state = ServerState()

# --- 初始化伺服器 ---
# 建立一個 Socket.IO 伺服器，允許任何人連線 (cors_allowed_origins='*')
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# 取得目前程式所在的資料夾路徑，確保能正確找到網頁檔案
base_dir = os.path.dirname(os.path.abspath(__file__))

# 將伺服器包裝成一個「網頁應用程式」，並設定「靜態檔案」
# 這裡改用絕對路徑來指定 index.html，避免因為執行指令時的目錄位置不同而導致找不到檔案 (404)
app = socketio.ASGIApp(sio, static_files={
    '/': os.path.join(base_dir, 'index.html'),
    '/index.html': os.path.join(base_dir, 'index.html'),
})

# --- 事件處理：當事情發生時該怎麼辦 ---

# 1. 當有人連線上來時
@sio.event
async def connect(sid, environ):
    if not state.monitor_started:
        sio.start_background_task(alarm_monitor)
        state.monitor_started = True
    print(f"[系統] 玩家連線：{sid}")

# 2. 當有人斷開連線時 (關閉網頁)
@sio.event
async def disconnect(sid):
    print(f"[系統] 玩家斷線：{sid}")
    for room_id, room in list(state.rooms.items()):
        room.remove_player(sid)
        if not room.players:
            state.rooms.pop(room_id)
            continue
            
        if room.host_sid == sid:
            # 轉移房長權限給下一個玩家
            room.host_sid = next(iter(room.players))
            print(f"[系統] 房長變更為：{room.host_sid}")
        
        await sio.emit("room_state", room.get_state(), room=room_id)

# 3. 當玩家請求加入房間時
@sio.event
async def join_room(sid, data):
    room_id = data.get("room_id", "default")
    room = state.rooms.setdefault(room_id, GameRoom(room_id))

    if len(room.players) >= 4:
        await sio.emit("join_failed", {"reason": "full"}, to=sid)
        return

    color = state.colors[len(room.players)]
    room.add_player(sid, color)
    
    await sio.enter_room(sid, room_id)
    await sio.emit("room_state", room.get_state(), room=room_id)
    print(f"[房間] {sid} 加入了 {room_id}，顏色是 {color}")

# 4. 當玩家按下 READY 按鈕時
@sio.event
async def player_ready(sid, data):
    room_id = data.get("room_id")
    room = state.rooms.get(room_id)
    if room:
        room.players[sid]["ready"] = True
        await sio.emit("room_state", room.get_state(), room=room_id)
        
        # 檢查是否全員準備完成 (必須滿 4 人且全部按下 READY)
        if len(room.players) == 4 and all(p["ready"] for p in room.players.values()):
            print(f"[系統] 房間 {room_id} 全員準備就緒，開始倒數")
            await sio.emit("all_ready", {"countdown": 3}, room=room_id)

# 5. 當玩家取消 READY 狀態時
@sio.event
async def player_unready(sid, data):
    room = state.rooms.get(data.get("room_id"))
    if room:
        room.players[sid]["ready"] = False
        await sio.emit("room_state", room.get_state(), room=room.room_id)

# 6. 房長設定起床時間 (鬧鐘時間)
async def alarm_monitor():
    """背景監測任務：根據鬧鐘接近程度自動調整檢查頻率"""
    print("[系統] 鬧鐘監控任務已啟動")
    while True:
        now = datetime.now()
        # 預設檢查頻率為 60 秒，若有鬧鐘接近則會自動調快
        sleep_time = 60 
        min_diff = 3600

        for room_id, room in list(state.rooms.items()):
            if not room.alarm_time: continue
            
            try:
                h, m = map(int, room.alarm_time.split(':'))
                alarm_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if alarm_dt < now: alarm_dt += timedelta(days=1)
                
                diff = (alarm_dt - now).total_seconds()
                min_diff = min(min_diff, diff)

                if -30 < diff <= 2:
                    print(f"[廣播] 房間 {room_id} 時間到！發送鬧鐘觸發訊號")
                    await sio.emit("alarm_triggered", {"time": room.alarm_time}, room=room_id)
                    room.alarm_time = None
            except Exception as e:
                print(f"[錯誤] 解析房間 {room_id} 時間失敗: {e}")

        # 若鬧鐘在 2 分鐘內，進入每秒偵測模式
        if min_diff < 120: sleep_time = 1

        try:
            await asyncio.wait_for(state.alarm_updated_event.wait(), timeout=sleep_time)
            state.alarm_updated_event.clear()
        except asyncio.TimeoutError:
            pass # 正常超時，進入下一輪檢查

@sio.event
async def set_alarm(sid, data):
    room_id = data.get("room_id")
    time_str = data.get("time")
    room = state.rooms.get(room_id)
    
    if room:
        if room.host_sid == sid and len(room.players) == 4:
            room.alarm_time = time_str
            state.alarm_updated_event.set()
            await sio.emit("alarm_set", {"time": time_str}, room=room_id)
        else:
            reason = "人滿了才能設鬧鐘喔！" if len(room.players) < 4 else "只有房長能設定。"
            await sio.emit("error_msg", {"message": reason}, to=sid)

# 7. 倒數結束，遊戲正式開始
@sio.event
async def start_game(sid, data):
    room_id = data.get("room_id")
    if room_id in state.rooms:
        await sio.emit("game_started", {}, room=room_id)

# --- 視窗管理邏輯 ---
def run_server():
    """在獨立線程中執行伺服器"""
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="error") # 減少日誌干擾

def start_window():
    """建立並啟動桌面視窗"""
    # 建立視窗，指向本地伺服器網址
    webview.create_window(
        'Tethered Alarm', 
        'http://127.0.0.1:5000',
        width=1000, 
        height=700,
        resizable=False
    )
    # 將 debug 設為 False，防止啟動時自動彈出開發者工具
    webview.start(debug=False)

# --- 啟動程式 ---
if __name__ == "__main__":
    SystemHelper.prevent_sleep()
    
    # 1. 啟動後台伺服器
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 2. 啟動桌面視窗
    print("[啟動] 正在開啟桌面視窗...")
    start_window()
    
    # 3. 視窗關閉後清理
    SystemHelper.restore_sleep()
    os._exit(0) 
# --- 引入工具箱 ---
import socketio    # 處理即時通訊的工具 (就像電話線)
import uvicorn     # 啟動網頁伺服器的引擎 (就像發電機)
import os          # 處理檔案路徑的工具
import platform    # 檢查電腦系統 (Windows, Mac, Linux)
import ctypes      # 用來呼叫電腦底層指令 (用來阻止電腦睡著)
import threading   # 用來同時執行伺服器與視窗
import webview     # 負責產生「軟體外殼」視窗的工具
from game_room import GameRoom  # 引入我們自己寫的房間管理員

def prevent_sleep():
    """
    透過 Win32 API 防止系統進入睡眠模式。
    ES_CONTINUOUS (0x80000000): 使設定持續有效。
    ES_SYSTEM_REQUIRED (0x00000001): 防止系統進入睡眠。
    ES_DISPLAY_REQUIRED (0x00000002): 防止螢幕關閉。
    """
    if platform.system() == "Windows":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            print("[系統] Win32：伺服器防休眠模式已啟用")
        except Exception as e:
            print(f"[系統] 啟用防休眠失敗：{e}")

def restore_sleep():
    """恢復系統預設的睡眠行為"""
    if platform.system() == "Windows":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print("[系統] Win32：已恢復系統預設休眠設定")
        except:
            pass

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

rooms = {}
COLORS = ["blue", "green", "pink", "red"]

# --- 事件處理：當事情發生時該怎麼辦 ---

# 1. 當有人連線上來時
@sio.event
async def connect(sid, environ):
    print(f"[系統] 玩家連線：{sid}")

# 2. 當有人斷開連線時 (關閉網頁)
@sio.event
async def disconnect(sid):
    print(f"[系統] 玩家斷線：{sid}")
    # 尋找並清理該玩家所在的房間
    rooms_to_delete = []
    for room_id, room in rooms.items():
        room.remove_player(sid)
        if len(room.players) == 0:
            rooms_to_delete.append(room_id)
        else:
            # 如果房長離開了，將房長權限交給房間內下一個玩家
            if room.host_sid == sid:
                room.host_sid = list(room.players.keys())[0]
                print(f"[系統] 房長變更為：{room.host_sid}")
            
            # 通知房間裡剩下的玩家：有人走掉了，更新畫面
            await sio.emit("room_state", room.get_state(), room=room_id)
    
    for rid in rooms_to_delete:
        del rooms[rid]
        print(f"[系統] 房間 {rid} 已空，自動移除")

# 3. 當玩家請求加入房間時
@sio.event
async def join_room(sid, data):
    room_id = data.get("room_id", "default")
    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id)
    
    room = rooms[room_id]
    # 根據目前人數自動分配顏色 (0=藍, 1=綠...)
    color = COLORS[len(room.players)]
    success = room.add_player(sid, color)
    
    if success:
        await sio.enter_room(sid, room_id) # 讓玩家進入 Socket 的房間頻道
        # 將「最新的房間狀態」廣播給房間裡的所有玩家
        await sio.emit("room_state", room.get_state(), room=room_id)
        print(f"[房間] {sid} 加入了 {room_id}，顏色是 {color}")
    else:
        # 如果加入失敗（通常是人滿了），通知該玩家
        print(f"[系統] 玩家 {sid} 嘗試加入已滿的房間 {room_id}")
        await sio.emit("join_failed", {"reason": "full"}, to=sid)

# 4. 當玩家按下 READY 按鈕時
@sio.event
async def player_ready(sid, data):
    room_id = data.get("room_id")
    if room_id in rooms:
        room = rooms[room_id]
        room.players[sid]["ready"] = True
        await sio.emit("room_state", room.get_state(), room=room_id)
        
        # 檢查是否全員準備完成 (必須滿 4 人且全部按下 READY)
        if len(room.players) == 4 and all(p["ready"] for p in room.players.values()):
            print(f"[系統] 房間 {room_id} 全員準備就緒，開始倒數")
            await sio.emit("all_ready", {"countdown": 3}, room=room_id)

# 5. 當玩家取消 READY 狀態時
@sio.event
async def player_unready(sid, data):
    room_id = data.get("room_id")
    if room_id in rooms:
        rooms[room_id].players[sid]["ready"] = False
        print(f"[房間] {sid} 在房間 {room_id} 取消了準備")
        await sio.emit("room_state", rooms[room_id].get_state(), room=room_id)

# 6. 房長設定起床時間 (鬧鐘時間)
@sio.event
async def set_alarm(sid, data):
    room_id = data.get("room_id")
    time_str = data.get("time") # 格式如 "08:30"
    if room_id in rooms:
        room = rooms[room_id]
        # 只有房長可以設定時間
        if room.host_sid == sid:
            room.alarm_time = time_str
            print(f"[設定] 房間 {room_id} 鬧鐘設定為 {time_str}，進入睡眠等待模式")
            # 通知所有人進入睡眠模式畫面
            await sio.emit("alarm_set", {"time": time_str}, room=room_id)

# 7. 倒數結束，遊戲正式開始
@sio.event
async def start_game(sid, data):
    room_id = data.get("room_id")
    if room_id in rooms:
        print(f"[遊戲] 房間 {room_id} 遊戲正式開始！")
        # 通知所有人遊戲開始
        await sio.emit("game_started", {}, room=room_id)

# --- 視窗管理邏輯 ---
def run_server():
    """在獨立線程中執行伺服器"""
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="error")

def start_window():
    """建立並啟動桌面視窗"""
    # 建立視窗，指向本地伺服器網址
    window = webview.create_window(
        'Tethered Alarm', 
        'http://127.0.0.1:5000',
        width=1000, 
        height=700,
        resizable=False # 固定大小，更有軟體感
    )
    # 將 debug 設為 False，防止啟動時自動彈出開發者工具
    webview.start(debug=True)

# --- 啟動程式 ---
if __name__ == "__main__":
    prevent_sleep()
    
    # 1. 啟動後台伺服器
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 2. 啟動桌面視窗
    print("[啟動] 正在開啟桌面視窗...")
    start_window()
    
    # 3. 視窗關閉後恢復設定
    restore_sleep()
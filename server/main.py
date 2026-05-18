import socketio
import uvicorn
import platform
import ctypes
from game_room import GameRoom

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

# 使用 ASGI 模式初始化伺服器
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = socketio.ASGIApp(sio)

rooms = {}
COLORS = ["blue", "green", "pink", "red"]

@sio.event
async def connect(sid, environ):
    print(f"[連線] {sid}")

@sio.event
async def disconnect(sid):
    print(f"[斷線] {sid}")
    # 尋找並清理該玩家所在的房間
    rooms_to_delete = []
    for room_id, room in rooms.items():
        room.remove_player(sid)
        if len(room.players) == 0:
            rooms_to_delete.append(room_id)
        else:
            await sio.emit("room_state", room.get_state(), room=room_id)
    
    for rid in rooms_to_delete:
        del rooms[rid]
        print(f"[系統] 房間 {rid} 已空，自動移除")

@sio.event
async def join_room(sid, data):
    room_id = data.get("room_id", "default")
    if room_id not in rooms:
        rooms[room_id] = GameRoom(room_id)
    
    room = rooms[room_id]
    color = COLORS[len(room.players)]
    success = room.add_player(sid, color)
    
    if success:
        await sio.enter_room(sid, room_id)
        await sio.emit("room_state", room.get_state(), room=room_id)
        print(f"[加入] {sid} 進入房間 {room_id}")

@sio.event
async def player_ready(sid, data):
    room_id = data.get("room_id")
    if room_id in rooms:
        rooms[room_id].players[sid]["ready"] = True
        await sio.emit("room_state", rooms[room_id].get_state(), room=room_id)

if __name__ == "__main__":
    print("Tethered Alarm Server (Uvicorn) starting on port 5000...")
    prevent_sleep()
    try:
        # 使用 uvicorn 執行 ASGI 應用程式
        uvicorn.run(app, host="0.0.0.0", port=5000)
    finally:
        restore_sleep()
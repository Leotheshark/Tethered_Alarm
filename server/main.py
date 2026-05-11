import asyncio
import socketio
from aiohttp import web
from game_room import GameRoom

sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

rooms = {}
COLORS = ["blue", "green", "pink", "red"]

@sio.event
async def connect(sid, environ):
    print(f"[連線] {sid}")

@sio.event
async def disconnect(sid):
    print(f"[斷線] {sid}")
    for room in rooms.values():
        room.remove_player(sid)
        await sio.emit("room_state", room.get_state(), room=room.room_id)

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
    web.run_app(app, host="0.0.0.0", port=5000)
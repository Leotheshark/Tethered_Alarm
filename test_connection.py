import socketio
import time
import threading

results = []

def connect_player(name):
    sio = socketio.SimpleClient()
    try:
        sio.connect("http://localhost:5000")
        sio.emit("join_room", {"room_id": "test-room"})
        event = sio.receive(timeout=3)
        count = event[1].get("count", "?")
        print(f"[{name}] ✅ 連線成功，房間人數：{count}")
        results.append(True)
        time.sleep(3)
        sio.disconnect()
    except Exception as e:
        print(f"[{name}] ❌ 連線失敗：{e}")
        results.append(False)

# 模擬四人同時連線
threads = []
for i in range(4):
    t = threading.Thread(target=connect_player, args=(f"玩家{i+1}",))
    threads.append(t)

for t in threads:
    t.start()
    time.sleep(0.3)

for t in threads:
    t.join()

print("\n--- 測試結果 ---")
print(f"成功：{results.count(True)}/4")
if all(results):
    print("✅ 第一週全部完成！可以進入第二週了！")
else:
    print("❌ 有玩家連線失敗，請貼錯誤訊息給我")
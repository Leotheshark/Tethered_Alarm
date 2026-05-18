# --- 引入工具箱 ---
import socketio    # 連線伺服器的工具
import time        # 處理延遲
import threading   # 同時執行多個任務 (模擬多玩家)

results = [] # 儲存測試結果

def connect_player(name):
    """模擬單一玩家連線的行為"""
    sio = socketio.SimpleClient()
    try:
        sio.connect("http://localhost:5000") # 連接到本地伺服器
        sio.emit("join_room", {"room_id": "test-room"}) # 加入測試房間
        event = sio.receive(timeout=3) # 等待伺服器回應
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
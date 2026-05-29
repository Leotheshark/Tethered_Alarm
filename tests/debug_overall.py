import argparse
import os
import subprocess
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="Launch multiple instances of the server for debugging.")
    parser.add_argument("--servers", type=int, default=4, help="Number of server instances to launch (default: 4)")
    parser.add_argument("--start-port", type=int, default=5000, help="Starting port for the first server (default: 5000)")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_dir = os.path.join(project_root, "server")

    procs: list[subprocess.Popen] = []
    
    # 定義統一的伺服器連線資訊
    main_port = args.start_port
    server_url = f"http://127.0.0.1:{main_port}"
    debug_room_id = "debug-multiplayer-test"

    print(f"[debug_overall] 正在模擬多人連線：1 Server + {args.servers} 客戶端視窗")
    print(f"[debug_overall] 伺服器位址: {server_url}, 房間 ID: {debug_room_id}")

    for i in range(args.servers):
        server_env = os.environ.copy()
        server_env["PORT"] = str(main_port)
        server_env["SERVER_URL"] = server_url
        server_env["ROOM_ID"] = debug_room_id
        server_env["MAX_PLAYERS"] = "4" # 確保房間需要 4 人才能開始
        server_env["DEBUG_WINDOWED"] = "1"
        server_env["DEBUG_TITLE"] = f"Player {i+1} ({'HOST' if i==0 else 'GUEST'})"
        
        # 除了第一個實例，其餘全部跳過啟動伺服器的動作（模擬 Guest 電腦）
        if i > 0:
            server_env["SKIP_SERVER"] = "1"
        
        # 階梯式排列視窗位置
        offset = i * 60
        server_env["DEBUG_WINDOW_POS"] = f"{50 + offset},{50 + offset}"

        print(f"[debug_overall] 正在啟動實例 {i+1}...")
        procs.append(subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=server_dir,
            env=server_env,
        ))
        time.sleep(1) # 錯開啟動時間確保 Host 優先佔領 Port 5000

    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    raise KeyboardInterrupt
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[debug_overall] 關閉所有實例...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[debug_overall] All server instances terminated.")

if __name__ == "__main__":
    main()

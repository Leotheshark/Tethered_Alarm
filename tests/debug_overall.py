import argparse
import os
import subprocess
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="Launch multiple instances of the server for debugging.")
    parser.add_argument("--servers", type=int, default=4, help="Number of server instances to launch (default: 4)")
    parser.add_argument("--start-port", type=int, default=5555, help="Starting port for the first server (default: 5555)")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_dir = os.path.join(project_root, "server")

    procs: list[subprocess.Popen] = []
    
    # 定義連線資訊：使用 127.0.0.1 模擬房主的 Tailscale IP
    main_port = args.start_port
    host_ip = "127.0.0.1"
    base_url = f"http://{host_ip}:{main_port}"

    print(f"[debug_overall] 正在模擬多人連線：1 Server + {args.servers} 客戶端視窗")
    print(f"[debug_overall] 伺服器位址: {base_url}, 房間 ID: {host_ip}")

    for i in range(args.servers):
        server_env = os.environ.copy()
        server_env["MAX_PLAYERS"] = "4" # 確保房間需要 4 人才能開始
        server_env["DEBUG_WINDOWED"] = "0"
        server_env["DEBUG_TITLE"] = f"({'HOST' if i==0 else 'GUEST'})"
        
        # 模擬 Host 與 Guest 的行為差異
        if i > 0:
            server_env["SKIP_SERVER"] = "1"  # Guest 不啟動 Uvicorn 

        server_env["SERVER_URL"] = base_url
        
        # 階梯式排列視窗位置
        offset = i * 60
        server_env["DEBUG_WINDOW_POS"] = f"{50 + offset},{50 + offset}"

        print(f"[debug_overall] 正在啟動實例 {i+1}...")
        procs.append(subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=server_dir,
            env=server_env,
        ))
        time.sleep(1.2) # 錯開啟動時間確保 Host 優先佔領 Port 5555

    try:
        while True:
            # 1. 檢查 Host (第一個實例) 是否還在
            if procs[0].poll() is not None:
                print("[debug_overall] Host 實例已關閉，正在結束整個測試連線...")
                break
            
            # 2. 檢查 Guest 是否被手動關閉，若有關閉則僅記錄，不影響他人
            for i in range(1, len(procs)):
                if procs[i] is not None and procs[i].poll() is not None:
                    print(f"[debug_overall] Guest {i+1} 已斷開連線")
                    procs[i] = None # 標記已處理

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

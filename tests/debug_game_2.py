"""
快速測試腳本：一鍵啟動 server + 4 個玩家視窗。

用法：
    python tests/debug_game.py            # 啟動 server + 4 個 client (預設全螢幕)
    python tests/debug_game.py --clients 2 # 只開 2 個 client
    python tests/debug_game.py --no-server # 不啟動 server，只開 client（server 已在跑時用）
    python tests/debug_game.py --windowed  # 使用視窗模式

按 Ctrl+C 會一起關閉所有子行程。
"""
import argparse
import os
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=int, default=4, help="要開幾個玩家視窗 (1-4)")
    parser.add_argument("--no-server", action="store_true", help="不要自動啟動 server")
    parser.add_argument("--room", default="debug", help="ROOM_ID")
    parser.add_argument("--windowed", action="store_true", help="使用視窗模式 (預設為全螢幕)")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    game_client = os.path.join(project_root, "game_client", "main.py")
    server_dir = os.path.join(project_root, "server")

    procs: list[subprocess.Popen] = []

    if not args.no_server:
        print("[debug] 啟動 server (uvicorn server.main:app on port 5000)")
        server_env = os.environ.copy()
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", "5000", "--log-level", "error"],
            cwd=server_dir,
            env=server_env,
        ))
        # 等 server 起來再開 client
        time.sleep(2)

    # 視窗 1280x720，階梯式排列（會互相重疊，需要 Alt+Tab 切換看不同玩家）
    positions = [
        (0, 0),
        (80, 60),
        (160, 120),
        (240, 180),
    ]

    n = max(1, min(args.clients, 4))
    for i in range(n):
        env = os.environ.copy()
        env["DEBUG_MODE"] = "1"
        env["DEBUG_MINIGAME"] = "1"
        env["DEBUG_MINIGAME_NAME"] = "dodge_knives"
        env["DEBUG_WINDOWED"] = "1" if args.windowed else "0"
        env["DEBUG_WINDOW_POS"] = f"{positions[i][0]},{positions[i][1]}"
        env["DEBUG_TITLE"] = f"Player {i + 1}"
        env["DEBUG_PLAYERS"] = str(n)  # 湊滿 n 人才啟動小遊戲
        env["ROOM_ID"] = args.room
        env["SERVER_URL"] = "http://127.0.0.1:5000"
        print(f"[debug] 啟動 client {i + 1} 於 {positions[i]}")
        procs.append(subprocess.Popen([sys.executable, game_client], env=env))
        time.sleep(0.5)  # 錯開連線，避免顏色指派競爭

    print("[debug] 全部啟動完成。按 Ctrl+C 關閉所有視窗。")
    try:
        # 等任何一個 client 結束就一起收掉
        while True:
            for p in procs:
                if p.poll() is not None:
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[debug] 關閉所有子行程...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()

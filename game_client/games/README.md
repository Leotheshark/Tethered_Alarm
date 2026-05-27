# 新增小遊戲指南

## 步驟（只需要這三步，不需要改任何其他檔案）

### 1. 在這個資料夾新增一個 `.py` 檔案
檔名用 snake_case，例如 `bomb_defuse.py`。這個名稱就是伺服器廣播時用的遊戲 ID。

### 2. 繼承 `BaseLogicInterface` 並實作 8 個方法

```python
from games.base_game import BaseLogicInterface

class BombDefuse(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list):
        super().__init__(socket_client, player_id_list)
        self.local_color = socket_client.player_color  # 必須有這個屬性，Renderer 會用到
        # ... 初始化你的遊戲狀態

    def on_enter(self, params=None): ...
    def on_exit(self): ...
    def handle_event(self, event_data): ...   # 接收 move / rescue_start / rescue_stop 等輸入
    def update(self, dt): ...
    def get_render_data(self) -> dict: ...    # 回傳渲染器需要的資料
    def is_cleared(self) -> bool: ...
    def get_sync_data(self) -> dict: ...
    def receive_sync_data(self, data): ...
```

> **注意**：你的類別必須有 `self.local_color` 屬性（`socket_client.player_color`），
> 引擎在呼叫 `renderer.draw_game(render_data, game.local_color)` 時會用到。

### 3. 在 server/main.py 的 start_game 裡把遊戲名稱換成你的

```python
await sio.emit("start_minigame", {"game": "bomb_defuse"}, room=room_id)
```

---

## 引擎自動幫你做的事

- **自動發現**：引擎啟動時掃描這個資料夾，找到所有繼承 `BaseLogicInterface` 的類別並自動註冊，不需要改 `engine.py`。
- **輸入傳遞**：WASD 移動會以 `handle_event({"type": "move", "dx": ..., "dy": ...})` 傳入。E 鍵按下/放開會傳 `rescue_start` / `rescue_stop`。
- **網路同步**：引擎每 50ms 呼叫你的 `get_sync_data()` 並廣播，收到封包時呼叫 `receive_sync_data(data)`。
- **通關偵測**：`is_cleared()` 回傳 `True` 時引擎自動呼叫 `on_exit()`。

## 網路廣播

在遊戲邏輯裡直接呼叫：

```python
self.socket_client.send_game_event({"type": "my_event", "data": ...})
```

其他客戶端的 `receive_sync_data` 就會收到這包資料。

## 渲染

`get_render_data()` 回傳任意字典，然後在 `renderer.py` 的 `draw_game()` 裡根據你的遊戲客製化繪製邏輯（需要改 `renderer.py`，但只是加 `elif` 分支，不影響其他遊戲）。

---

## 遠端位置同步（DR + LERP）

如果你的遊戲有「玩家在地圖上移動」這類需要同步位置的實體，**不要自己寫插值邏輯**，直接用 `game_client/sync_helpers.py` 提供的工具。它整合了 Dead Reckoning（封包空檔時用最後速度向量預測）與 LERP（每幀平滑逼近目標），讓遠端玩家不會在別人視角看起來像在瞬移或卡頓。

### 三個 API

```python
from sync_helpers import RemoteSyncState, apply_server_update, tick_remote_sync, reset_sync_state
```

| 函式 | 何時呼叫 |
|---|---|
| `RemoteSyncState(target_x, target_y)` | 建立遠端實體時，附在實體上（例如 `entity.sync = RemoteSyncState(...)`） |
| `apply_server_update(state, x, y, dx, dy)` | 在 `receive_sync_data` 收到該實體的位置封包時 |
| `tick_remote_sync(entity, state, dt, speed, bounds=...)` | 每幀在 `update` 裡，對「非本地」實體呼叫，會直接更新 `entity.x/y` |
| `reset_sync_state(state, x, y)` | 在 `on_enter` 重置遊戲時，避免上局殘留 target 拖動畫面 |

### 範例樣板

```python
from sync_helpers import RemoteSyncState, apply_server_update, tick_remote_sync, reset_sync_state

class MyGame(BaseLogicInterface):
    def __init__(self, socket_client, player_id_list):
        super().__init__(socket_client, player_id_list)
        self.local_color = socket_client.player_color
        # 為每個玩家建立同步狀態
        for player in self.players.values():
            player.sync = RemoteSyncState(target_x=player.x, target_y=player.y)

    def update(self, dt):
        # 本地玩家由輸入直接更新位置；其餘玩家交給 sync_helpers
        map_bounds = (0, 0, MAP_WIDTH, MAP_HEIGHT)
        for color, p in self.players.items():
            if color == self.local_color:
                continue
            tick_remote_sync(p, p.sync, dt, PLAYER_SPEED, bounds=map_bounds)

    def receive_sync_data(self, data):
        if data.get("type") == "player_pos":
            p = self.players.get(data["color"])
            if p and data["color"] != self.local_color:
                apply_server_update(p.sync, data["x"], data["y"],
                                    data.get("dx", 0), data.get("dy", 0))

    def on_enter(self, params=None):
        super().on_enter(params)
        for p in self.players.values():
            reset_sync_state(p.sync, p.spawn_x, p.spawn_y)
```

### 注意事項

- **`dx/dy` 必須是「單位向量」**（長度 = 速度方向，非位移量）。如果你的輸入是 WASD 那種 `(±1, ±1)` 形式，斜向時要正規化乘上 `0.7071`，否則 DR 預測會超速。可以在收封包時做一次（見 `reverse_pacman.py` 的 `receive_sync_data`）。
- **`speed` 要對應該實體當下的速度**。若敵人有加速狀態，傳當下速度即可。
- **`bounds`** 是 `(min_x, min_y, max_x, max_y)`，避免 DR 把 target 推到地圖外害 LERP 拖出畫面；若實體會自由穿越邊界可不傳。
- **預設參數**：`lerp_speed=12`、`dr_timeout=0.15s`。封包頻率高（如 20Hz+）通常不用調；若覺得太遲鈍可調高 `lerp_speed`（如 18），太抖則調低（如 8）。
- **不要對本地玩家呼叫 `tick_remote_sync`**。本地玩家的位置由你自己的物理 / 輸入處理直接更新。

### 為什麼要用這套？

實際案例可參考 `reverse_pacman.py` — 在沒套 sync_helpers 之前，遠端玩家每 50ms 才硬切位置一次，看起來會卡頓；套上後變成 60fps 平滑插值，封包遲到時還會用 DR 預測，幾乎看不出網路延遲。同一套邏輯也用在 `entities.py` 的 `RemoteGhost`（大廳模式的遠端玩家）。

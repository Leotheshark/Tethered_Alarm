# 關卡編輯器與 JSON 格式

`maps/` 資料夾存放 Reverse Pac-Man 的關卡檔。每個關卡是一個 `.json`，由 `tools/map_editor.py` 視覺化編輯，由 `game_client/games/reverse_pacman.py` 載入。

---

## 啟動編輯器

```bash
# 編輯預設關卡
python tools/map_editor.py

# 編輯指定關卡（檔名不含 .json）
python tools/map_editor.py level_2
```

若指定的關卡檔不存在，會開啟一張全新的空白地圖（18×32、外圈牆），存檔時自動以該名稱建立。

## 操作

| 功能 | 操作 |
|---|---|
| 套用磚片 | 左側選磚片（W/./P/G/B/S）→ 點地圖格 |
| 拖拉刷磚片 | 選磚片後按住左鍵拖過格子 |
| 移動出生點 | 左側選 spawn 顏色 → 點目的格 |
| 建立按鈕↔閘門配對 | 左側選 `Pair (B↔G)` → 點一格 button → 再點一格 gate |
| 取消未完成的配對 | 在已選的同一格再點一次 |
| 儲存 | `Ctrl+S` |
| 復原 | `Ctrl+Z` |
| 新關卡（清空當前） | `Ctrl+N` |

底部 status bar 即時顯示 pellet / button / gate / pair 數量與警告（出生點在牆上、按鈕未配對等）。警告不會擋存檔，僅作為提示。

## 磚片符號

| 符號 | 意義 |
|---|---|
| `W` | Wall（牆，玩家與 Pac-Man 不可通過） |
| `.` | Empty（空地） |
| `P` | Pellet（飼料，玩家吃光即通關） |
| `G` | Gate（閘門，初始視為牆，被對應按鈕觸發後打開） |
| `B` | Button（按鈕，玩家踩到時開啟配對的閘門） |
| `S` | Spike（釘板，玩家踩到後 3 秒速度減半） |

---

## JSON 格式

```json
{
  "name": "level_default",
  "tile_size": 40,
  "rows": 18,
  "cols": 32,
  "tiles": [
    "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
    "WPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPW",
    "...",
    "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW"
  ],
  "spawns": {
    "blue":   [1, 1],
    "green":  [15, 30],
    "pink":   [1, 30],
    "red":    [15, 1],
    "pacman": [8, 16]
  },
  "button_gate_map": [
    {"button": [3, 4],  "gate": [16, 27], "label": "A: 左上 → 右下"}
  ]
}
```

| 欄位 | 說明 |
|---|---|
| `name` | 關卡名稱，與檔名一致 |
| `tile_size` | 每格的像素邊長（目前固定 40，未來可改） |
| `rows` / `cols` | 地圖尺寸；必須與 `tiles` 長度一致 |
| `tiles` | 字串陣列，每字串 1 行、每字元 1 格。字元定義見上方表格 |
| `spawns` | 5 個出生點 `[row, col]`；必須包含 `blue`、`green`、`pink`、`red`、`pacman` |
| `button_gate_map` | 按鈕-閘門配對清單；`label` 為可選註解，遊戲端不讀取 |

格座標一律 `[row, col]`（不是 `[x, y]`），原點在左上角。

---

## 在遊戲中切換關卡

`reverse_pacman.py` 模組載入時會自動呼叫 `load_map("level_default")`，覆寫模組級的 `MAP_LAYOUT`、`SPAWN_TILES`、`PACMAN_SPAWN_TILE`、`BUTTON_GATE_MAP`、`ROWS`、`COLS`、`TILE_SIZE`。

要切換到其他關卡，目前最簡單的方法是在 import 後手動呼叫：

```python
from games import reverse_pacman
reverse_pacman.load_map("level_2")
```

未來支援「房間選關卡」時會把 `map_name` 透過 server 廣播給所有 client。

## 新增關卡的工作流程

1. `python tools/map_editor.py level_2` → 開啟空地圖
2. 用工具列畫地圖、設定出生點與按鈕配對
3. `Ctrl+S` 儲存
4. 把 `maps/level_2.json` 提交到 git
5. 在遊戲中載入該關卡測試

寫好的關卡可直接 PR review，因為 JSON 是純文字、`git diff` 看得到每一格的差異。

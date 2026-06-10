# STM32MP1 — mp1gui 架構與資料流（圖解）

> 對象：`C:\Stone\AI_try\MP1\mp1gui`
> 用途：看懂各檔案怎麼互相牽動，方便之後改 GUI。

---

## 1. 檔案角色一覽

| 檔案 | 角色 | 改它會影響 |
|------|------|-----------|
| `ui/app.slint` | **GUI 版面/長相**（宣告式） | 畫面排版、顏色、字級、元件、**對外的資料介面**（property / callback） |
| `src/main.rs` | **Rust 邏輯** | 抓資料（/proc、USB）、解析、把值餵進 UI、按鈕行為 |
| `build.rs` | 編譯期把 `.slint` 轉成 Rust | 一般不動 |
| `Cargo.toml` | 相依與 Slint features | 加套件（serialport）、改後端（linuxkms/winit） |
| `run-panel.sh` | 板子上啟動 | 用 `openvt -s` 投實體面板、旋轉、環境變數 |
| `deploy.ps1` | 取二進位 → scp 上板 | 部署流程 |

---

## 2. 建置流程（原始碼 → 跑在面板）

```
  ui/app.slint ─┐
                │  build.rs 呼叫 slint_build::compile()
                ▼
        [產生的 Rust 程式碼]  ← MainWindow 型別、set_*/get_*/on_* 方法
                │
                │  src/main.rs 用 slint::include_modules!() 把它拉進來
   src/main.rs ─┤
   Cargo.toml ──┤  (相依/features)
                ▼
        cargo build --release   （Docker + QEMU 編 armhf；見 Rust GUI 筆記 §5 快取）
                ▼
        mp1gui（armhf 二進位，~12MB）
                │  deploy.ps1 / scp
                ▼
        板子 /home/root/mp1gui
                │  run-panel.sh：systemctl stop weston → openvt -s → SLINT_BACKEND=linuxkms
                ▼
        實體 DSI 面板（480×800，軟體算繪走 DRM）
```

**關鍵**：`app.slint` 不是執行期讀的檔，是**編譯期**被 `build.rs` 變成 Rust。所以改 `app.slint` **要重編**才會生效。

---

## 3. Slint ↔ Rust 的「介面契約」

`app.slint` 宣告的東西，會在 Rust 端產生對應方法。這就是兩邊溝通的唯一管道：

| `app.slint` 宣告 | Rust（`main.rs`）用法 | 方向 |
|------------------|----------------------|------|
| `in property <string> uptime;` | `ui.set_uptime("...".into())` | Rust → UI |
| `in property <string> dev_value;` | `ui.set_dev_value(...)` | Rust → UI |
| `in property <bool> dev_connected;` | `ui.set_dev_connected(true)` | Rust → UI |
| `in-out property <int> counter;` | `ui.get_counter()` / `ui.set_counter(n)` | 雙向 |
| `callback inc();` | `ui.on_inc(|| { ... })` | UI → Rust |

> 想在畫面上多顯示一個值 → ① `app.slint` 加一個 `in property` + 一個 `Text`，② `main.rs` 算出值後 `ui.set_xxx(...)`。兩邊名字要對上。

---

## 4. 執行期資料流（程式跑起來後）

三個來源各自把資料推進同一個畫面：

```
┌──────────────────────────── src/main.rs ────────────────────────────┐
│                                                                      │
│  【A. 系統資訊】每秒                                                   │
│   /proc/uptime,/meminfo,/loadavg ─► fmt_uptime/mem/load()            │
│                                          │                           │
│  【B. USB 感測器】背景 thread (spawn_serial)                          │
│   /dev/ttyUSB0 ◄── 送 "SC RE\r" ──► 收回應                            │
│       (FT232)        每秒一次        │                               │
│                                     ▼                                │
│                    parse_reply() 抓 nT1/nH1/nF1                       │
│                                     │                                │
│                                     ▼                                │
│                    Arc<Mutex<DevData{result,connected}>>  ◄── 共享狀態 │
│                                     │                                │
│           ┌─────────────────────────┘                               │
│           ▼                                                          │
│   refresh() （由 1 秒 Timer 觸發）                                    │
│     ui.set_uptime/mem/load(...)        ← 來自 A                       │
│     ui.set_dev_value/dev_connected(...) ← 來自 B（讀 Mutex）           │
│           │                                                          │
│  【C. 按鈕事件】（非定時，點了才觸發）                                 │
│   app.slint: clicked => inc()  ──►  ui.on_inc(): set_counter(+1)     │
│           │                                                          │
└───────────┼──────────────────────────────────────────────────────────┘
            ▼
   Slint 重繪有變動的 property
            ▼
   linuxkms / DRM dumb buffer ─► 實體 DSI 面板
```

- **A 系統資訊**、**B 感測器** 走「每秒 Timer 拉一次」。
- **B 的讀取**在**獨立背景 thread**（避免序列 I/O 卡住畫面），用 `Arc<Mutex<DevData>>` 把結果交給主執行緒。
- **C 按鈕**是**事件驅動**，點下去才跑 `inc()`。

---

## 5. 逐秒 Action Flow（時間軸）

```
每隔 1 秒（兩條獨立節奏，互不阻塞）：

主執行緒 Timer ──┐
                ├─ set_elapsed(+1)
                ├─ refresh():
                │     讀 /proc → set_uptime/mem/load
                │     鎖 DevData → set_dev_value / set_dev_connected
                └─ Slint 偵測 property 變動 → 重繪 → DRM present → 面板更新

背景 serial thread ──┐
                    ├─ port.clear(Input)            （清殘留）
                    ├─ write "SC RE\r"              （送查詢，CR 結尾）
                    ├─ read（最多等 2 秒讓回應到、收到後 idle 才停）
                    ├─ parse_reply() → "Temp..\nHumidity..\nFlow.."
                    ├─ 寫進 Arc<Mutex<DevData>>      （給 refresh 讀）
                    └─ sleep 1 秒

事件（隨時）：
使用者點按鈕 ─► inc() ─► set_counter(+1) ─► Slint 重繪按鈕文字
```

> 注意：**serial thread 的 1 秒** 和 **UI Timer 的 1 秒** 是各自獨立計時，不保證對齊 —— 但因為走共享 `DevData`，UI 永遠顯示「最後一次成功讀到的值」，所以不會閃爍或卡頓。

---

## 6. 想改東西時看哪裡

| 我想… | 改哪個檔 | 具體 |
|-------|---------|------|
| 換排版/顏色/字級/加框 | `ui/app.slint` | 改 `Text`/`VerticalBox`/`GroupBox`… |
| 多顯示一個數值 | `app.slint` + `main.rs` | slint 加 `in property` + `Text`；main 算值後 `set_xxx` |
| 改感測器指令或解析 | `src/main.rs` | `SENSOR_CMD`、`parse_reply()` |
| 改輪詢頻率 | `src/main.rs` | serial thread 的 `sleep(1s)` |
| 改畫面方向 | `run-panel.sh` | 加 `SLINT_KMS_ROTATION=270` |
| 加套件/換顯示後端 | `Cargo.toml` | features / dependencies |

---

## 7. 相關文件
- [`MP1_Rust_GUI開發筆記.md`](MP1_Rust_GUI開發筆記.md) — 交叉編譯、顯示後端、Docker 快取
- [`MP1_USB感測器與面板GUI整合筆記.md`](MP1_USB感測器與面板GUI整合筆記.md) — USB 驅動 + 感測器協定完整鏈路

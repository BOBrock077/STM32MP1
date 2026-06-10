# STM32MP1 — Rust + Slint GUI 開發筆記

> 最後更新：2026-06-10（新增：linuxkms 實體面板打通、USB 感測器整合、Docker 相依快取）
> 專案目錄：`C:\Stone\AI_try\MP1\mp1gui`（PC 端）
> 板子背景見 `MP1_知識總整理.md`；USB 感測器/驅動完整鏈路見 `MP1_USB感測器與面板GUI整合筆記.md`

---

## 0. 目標與目前成果

把一支 **Rust + Slint** 的 GUI（系統儀表板：即時 uptime / 記憶體 / 負載 + 計數按鈕）跑在 STM32MP1 板子上。

| 階段 | 狀態 |
|------|------|
| 程式碼（Slint app） | ✅ 完成，Windows 原生跑過 |
| 交叉編譯成 armhf 執行檔 | ✅ 完成（Docker + QEMU + Debian buster） |
| 傳進板子並執行 | ✅ 完成（`scp` → `/home/root/mp1gui`，10MB） |
| 跑在 **VNC 桌面 :1**（X11，PC 可遠端看） | ✅ **已驗證可動**，顯示真實 /proc 資料 |
| 跑在 **板子實體 DSI 面板**（linuxkms 全螢幕） | ✅ **2026-06-10 打通**（`openvt -s` 拿 DRM master，見 §4b） |
| 透過 **USB 讀外部感測器**並顯示數值 | ✅ **2026-06-10**（`SC RE` 輪詢 → Temp/Humidity/Flow，見 §4c） |

---

## 1. 專案結構

```
mp1gui/
├─ Cargo.toml          # 相依與 Slint features（含 serialport、backend-linuxkms-noseat）
├─ build.rs            # 呼叫 slint_build 編譯 .slint
├─ ui/app.slint        # GUI 版面（Slint 語言；含 Sensor(SC RE) 顯示框）
├─ src/main.rs         # 讀 /proc + 背景 thread 輪詢 USB 感測器、Timer 每秒刷新
├─ Dockerfile          # armhf(buster) 編譯環境（已改成相依快取結構，見 §6）
├─ deploy.ps1          # 從 image 取出二進位 → scp 進板子
├─ run-panel.sh        # 用 openvt -s 把 GUI 起在實體 DSI 面板（見 §4b）
└─ .dockerignore
```

UI 文字一律用 **英文**（板子無中文字型，中文會變方框）。

---

## 2. 為什麼這樣編（被板子限制鎖定的決策）

- 板子 **armv7l、glibc 2.28、RAM 427M、無 gcc/rust** → 不能在板子上編，必須 PC 交叉編譯。
- 採 **Docker + QEMU「原生 armhf 編譯」**（非交叉連結）：
  - `FROM arm32v7/debian:buster` —— buster 的 **glibc 剛好 2.28**，與板子（Yocto thud）完全相容；且能裝到真正 armhf 版的 wayland / x11 / drm / 字型等開發函式庫。
  - 比在 Windows 上搞交叉連結 + sysroot 省事可靠，代價是 QEMU 模擬編譯較慢（~15–20 分，會編到 `rav1e` 等大套件）。

### 兩個一定要填的坑
1. **buster 已封存**：apt 來源改指 `archive.debian.org`，並關掉日期檢查
   （`Acquire::Check-Valid-Until "false"`）。
2. **buster 的 curl 是 GnuTLS、CA 太舊**（`unable to get local issuer certificate`）→ rustup / crates.io 的 TLS 全失敗。
   修法：先 `curl -k` 抓現代 Mozilla bundle，再用環境變數指過去：
   ```dockerfile
   RUN curl -k -sS https://curl.se/ca/cacert.pem -o /opt/cacert.pem
   ENV CURL_CA_BUNDLE=/opt/cacert.pem SSL_CERT_FILE=/opt/cacert.pem
   ```
   （curl、rustup、cargo 都吃這兩個變數，一次全解。）
3. buster 內建的 rust 太舊，編不動 Slint 1.16 → 用 **rustup 裝 stable**。

---

## 3. 建置與部署指令（PC 端 PowerShell）

```powershell
# 0) 一次性：Docker Desktop 開著，啟用 arm 模擬
docker run --privileged --rm tonistiigi/binfmt --install arm

# 1) 編譯（QEMU 模擬，慢）
docker build --platform linux/arm/v7 -t mp1gui-build "C:\Stone\AI_try\MP1\mp1gui"

# 2) 取出二進位（deploy.ps1 已封裝）
docker create --platform linux/arm/v7 --name mp1x mp1gui-build
docker cp mp1x:/src/target/release/mp1gui "C:\Stone\AI_try\MP1\mp1gui\mp1gui-arm"
docker rm mp1x

# 3) 傳進板子
scp "C:\Stone\AI_try\MP1\mp1gui\mp1gui-arm" mp1:/home/root/mp1gui
ssh mp1 'chmod +x /home/root/mp1gui'
```

> 觀察編譯進度：`Get-Content "...\build.log" -Wait -Tail 20`（`-Wait` = tail -f）。
> 整個 `cargo build` 是 Docker 的**單一步驟**，所以步驟標題會一直停在
> `RUN cargo build`，真正進度是底下一行行 `Compiling ...`，不是卡住。

---

## 4. 顯示後端 —— 最關鍵的踩雷

板子接的是 **DSI 觸控面板（`/sys/class/drm/card0-DSI-1` = connected）**；
**HDMI 沒插**（`card0-HDMI-A-1` = disconnected）。Weston 把 ST demo 顯示在 DSI 上（weston.ini 設 `transform=270` 旋轉）。

| 後端 | 結果 | 原因 |
|------|------|------|
| **Wayland（winit）→ 實體面板** | ❌ 失敗 | 板子 **Weston 5.0（2018）太舊**，winit 0.30 要新的 `xdg_wm_base` 協定，舊 Weston 不提供 → `the requested global was not found in the registry` |
| **X11（winit）→ Xwayland :0 → 實體面板** | ❌ 不可靠 | Weston 5.0 的 Xwayland 是延遲啟動、**無對外可連的 X socket**（`Failed to open connection to X server`）。這片舊 Weston 對外部 X client 支援很差 |
| **X11（winit）→ Xvnc :1（VNC 桌面）** | ✅ **可用** | VNC 那個 X 桌面隨時都在；軟體算繪、不需 GPU |
| **linuxkms / DRM → 直接畫到面板** | ⚠️ 計畫 | 繞過 compositor，最穩，但需重編 + 停掉 Weston |

### 4a. 目前可用：跑在 VNC（X11 :1）
二進位用 **`backend-winit` + `renderer-software`**，在板子上：
```sh
# 在板子（ssh mp1 後）
export DISPLAY=:1
export XAUTHORITY=/home/root/.Xauthority
unset WAYLAND_DISPLAY
/home/root/mp1gui
```
畫面出現在 VNC 桌面，PC 用 RealVNC 連 `100.192.0.50:5901` 看得到、可點按鈕。
（PC 端非互動 ssh 的 PATH 很精簡，記得 `export PATH=/usr/sbin:/sbin:/usr/bin:/bin`。）

### 4b. ✅ 已打通：跑在實體 DSI 面板（linuxkms 全螢幕，2026-06-10）
- `Cargo.toml` features：**`backend-linuxkms-noseat`**（root 直開 DRM，免 seatd）+ **`renderer-software`**。
- `Dockerfile` apt 已含 **`libdrm-dev libinput-dev libudev-dev`**。執行時相依板子都有：`libdrm.so.2`、`libinput.so.10`、`libudev.so.1`、`/dev/dri/card0` ✓。
- **絕對不要**啟用 `renderer-femtovg`：板子的 `libgbm.so` 是 Vivante 廠商版、**沒有標準 `libgbm.so.1` soname**，一旦連到 gbm 會 `cannot open shared object file` 起不來。軟體算繪走 DRM dumb buffer，不碰 gbm。（已驗證二進位沒連到 gbm，log 顯示 `Using Software renderer`。）

#### ⚠️ 最大踩雷：DRM master 權限
直接 `systemd-run` 或裸跑會：
```
Error presenting framebuffer on screen: Permission denied (os error 13)
```
原因：行程**沒掛在前景 VT** 上，拿不到 DRM master（fbcon 文字主控台佔著 CRTC）。`nohup` 跑有時剛好搶到、有時搶不到，**不可靠**。

**解法照抄 weston 的做法**：weston 是透過 `weston-start` 裡的 **`openvt -s`**（配一個新前景 VT）啟動的。所以我們也用 `openvt -s`：

```sh
# mp1gui/run-panel.sh 的核心
systemctl stop weston          # 釋放 DRM master（ST demo 會關掉）
openvt -s -- sh -c 'SLINT_BACKEND=linuxkms exec /home/root/mp1gui >/tmp/gui.log 2>&1'
```
- log 出現 `Using Software renderer` / `Rendering at 480x800`、**無 permission denied** → 成功。
- 跑在 VT 上（`ps` 看到 `ttyN ... Ssl+`），**ssh 關線不會死**（之前用 `nohup` 會被收掉）。
- 面板原生 **480×800 直式**；若方向不對，`run-panel.sh` 加 `export SLINT_KMS_ROTATION=270`。
- ⚠️ **VNC 看不到 linuxkms 的畫面**（Weston 5.0 無 VNC backend、linuxkms 走 DRM 不經 X）。要遠端看得改回 §4a 的 X11/VNC 模式（同一支二進位），但序列埠一次只能一個程式開。

### 4c. USB 感測器整合（2026-06-10）
GUI 透過 USB 對外部 **SGX 感測板**（FT232 → `/dev/ttyUSB0`，驅動見整合筆記）查詢數值並顯示。
- `Cargo.toml` 加 **`serialport = "4"`**（Linux 用 libudev，板子已有）。
- `src/main.rs` 背景 thread：
  1. 埠優先 **`ttyUSB0`** 再 `ttyACM0`，115200 8N1，開 DTR/RTS。
  2. 每秒 `clear(Input)` → 送 **`SC RE\r`**（CR 結尾！）→ 收回應。
     - **bug 教訓**：一開始第一次 `read` 逾時就 break，抓不到「較慢才開始回」的回應 → 改成**等最多 2 秒讓回應開始到、收到資料後 idle 才結束**。
  3. `parse_reply()` 專抓含 `nT1/nH1/nF1` 的行，格式化成 `Temp / Humidity / Flow` 三行；非量測行（如板號）回空字串 → GUI 保留上一筆，不閃爍。
- `ui/app.slint`：加「Sensor (SC RE)」GroupBox（連線狀態燈 + 量測值）。
- 除錯：serial thread `eprintln!("[serial] ...")` → 進 `/tmp/gui.log`，可看實際收到的位元組與解析結果。
- 協定/資料格式（`nT1`=溫度、`nH1`=濕度、`nF1`=流量）與驅動細節見 `MP1_USB感測器與面板GUI整合筆記.md`。

---

## 5. Docker 建置加速（相依快取）

QEMU 原生編 armhf 約 **40 分**（Slint 相依樹大）。兩個加速法：

1. **Dockerfile 相依快取結構**：先用 stub crate（`fn main(){}`）只編相依層，再 COPY 真實碼編 `mp1gui`。改 `src`/`ui` 重編從 40 分降到 **1–2 分**（`Cargo.toml`/`Cargo.lock` 不變就吃快取）。**首次用新 Dockerfile 仍會慢一次**建立快取。
   ```dockerfile
   COPY Cargo.toml Cargo.lock ./
   RUN mkdir src && echo "fn main() {}" > src/main.rs && echo "fn main() {}" > build.rs \
    && cargo build --release && rm -rf src build.rs
   COPY . .
   RUN cargo build --release
   ```
2. **容器內增量編**（迭代最快，~1 分）：進舊映像容器，只換 `src/main.rs` 重編，重用 `/src/target` 的相依快取：
   ```powershell
   docker run -d --name mp1edit --platform linux/arm/v7 mp1gui-build sleep infinity
   docker cp src\main.rs mp1edit:/src/src/main.rs
   docker exec mp1edit sh -c "cd /src && cargo build --release"
   docker cp mp1edit:/src/target/release/mp1gui mp1gui-arm
   docker rm -f mp1edit
   ```
   > scp 上板前先 `pkill -x mp1gui`，否則執行檔被佔、scp 會 **ETXTBSY**（`dest open: Failure`）。

---

## 6. 踩雷速查

| 症狀 | 原因 / 解法 |
|------|-------------|
| Docker build：`curl: (60) ... local issuer` | buster CA 太舊 → 用第 2 節的 cacert.pem + 環境變數 |
| Docker build：`cargo: not found` | rustup 因上面 TLS 失敗沒裝成功 → 同上 |
| build 標題卡在 `7/7 RUN cargo build` | 正常，整個編譯是同一步驟，看底下 `Compiling` 才是進度 |
| 紅字 / `warn: ... os error 75` | 無害：cargo 進度寫 stderr 被染紅；rustup 在 QEMU 清暫存的警告 |
| 板子上 `ssh mp1 'ifconfig...'` → not found | 非互動 ssh PATH 精簡 → `export PATH=/usr/sbin:/sbin:/usr/bin:/bin` |
| `pkill -f mp1gui` 把 ssh 自己殺了（exit 255） | `-f` 比對到含 mp1gui 的整條命令列 → 改 **`pkill -x mp1gui`** |
| GUI：`requested global was not found` | Weston 太舊，winit Wayland 起不來 → 改用 X11（:1）或 linuxkms |
| GUI：`Failed to open connection to X server`（:0） | Xwayland 沒對外 socket → 用 :1 或 linuxkms |
| `org.freedesktop.portal.Desktop` 警告 | 無害可忽略 |
| PowerShell→ssh→板子 三層引號，grep `|` 樣式被拆壞 | 別用 `|` 交替；改 `grep -e A -e B`，或多次 grep；複雜邏輯**寫成 .sh scp 到板子跑** |
| linuxkms：`Error presenting framebuffer: Permission denied` | 沒掛前景 VT、拿不到 DRM master → 用 **`openvt -s`** 起（見 §4b） |
| GUI 跑一下就消失（`nohup` 啟動） | ssh 關線把它收掉 → 改用 `openvt -s`（掛 VT，不死） |
| serial 永遠 `no reply` 但埠有開（fd 有 ttyUSB0） | read 第一次逾時就 break、抓不到慢回應 → 等 ~2 秒讓回應開始到再收（見 §4c） |
| scp 上板 `dest open: Failure`（ETXTBSY） | 舊 mp1gui 還在跑、執行檔被佔 → 先 `pkill -x mp1gui` 再 scp |

---

## 7. 待辦 / 下一步

- [x] ~~重編 linuxkms 版並在實體 DSI 面板驗證~~ → **2026-06-10 完成**（`openvt -s`，§4b）。
- [x] ~~確認二進位沒連到 `libgbm.so.1`~~ → log 顯示 `Using Software renderer`，未連 gbm。
- [ ] 畫面**旋轉**確認（若方向不對加 `SLINT_KMS_ROTATION=270`）。
- [ ] **觸控輸入**測試（linuxkms 已開 `/dev/input/event0/1`，libinput 觸控未測）。
- [ ] **開機自動啟動**（systemd service 包 `openvt -s` 起 GUI）；FTDI 驅動也要開機自動 `insmod`。
- [ ] 之後可換 femtovg(GPU) 提升效能 —— 但需先解決板子無標準 libgbm.so.1 的問題。
```

# STM32MP1 — Rust + Slint GUI 開發筆記

> 最後更新：2026-06-02
> 專案目錄：`C:\Stone\AI_try\MP1\mp1gui`（PC 端）
> 板子背景見 `MP1_知識總整理.md`

---

## 0. 目標與目前成果

把一支 **Rust + Slint** 的 GUI（系統儀表板：即時 uptime / 記憶體 / 負載 + 計數按鈕）跑在 STM32MP1 板子上。

| 階段 | 狀態 |
|------|------|
| 程式碼（Slint app） | ✅ 完成，Windows 原生跑過 |
| 交叉編譯成 armhf 執行檔 | ✅ 完成（Docker + QEMU + Debian buster） |
| 傳進板子並執行 | ✅ 完成（`scp` → `/home/root/mp1gui`，10MB） |
| 跑在 **VNC 桌面 :1**（X11，PC 可遠端看） | ✅ **已驗證可動**，顯示真實 /proc 資料 |
| 跑在 **板子實體 DSI 面板**（linuxkms 全螢幕） | ⚠️ **計畫中**：設定已改、尚未重編驗證 |

---

## 1. 專案結構

```
mp1gui/
├─ Cargo.toml          # 相依與 Slint features
├─ build.rs            # 呼叫 slint_build 編譯 .slint
├─ ui/app.slint        # GUI 版面（Slint 語言）
├─ src/main.rs         # 讀 /proc、綁定 callback、Timer 每秒刷新
├─ Dockerfile          # armhf(buster) 編譯環境
├─ deploy.ps1          # 從 image 取出二進位 → scp 進板子
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

### 4b. 計畫：跑在實體 DSI 面板（linuxkms 全螢幕）
**設定已改、尚未重編驗證**（用 `git`/檔案現況為準）：
- `Cargo.toml` features 加入 **`backend-linuxkms-noseat`**（root 直開 DRM，免 seatd），
  繼續只用 **`renderer-software`**。
- `Dockerfile` apt 加 **`libdrm-dev libinput-dev libudev-dev`**。
- **絕對不要**啟用 `renderer-femtovg`：板子的 `libgbm.so` 是 Vivante 廠商版、**沒有標準 `libgbm.so.1` soname**，一旦連到 gbm，二進位在板子上會 `libgbm.so.1: cannot open shared object file` 起不來。軟體算繪走 DRM dumb buffer，不碰 gbm。
- 執行步驟（重編完）：
  ```sh
  systemctl stop weston            # 釋放 DRM master（ST demo 會關掉）
  SLINT_BACKEND=linuxkms /home/root/mp1gui
  # 若畫面方向不對：試 SLINT_KMS_ROTATION=270（面板原生方向 vs Weston 的 transform=270）
  ```
- 執行時相依（板子已確認）：`libdrm.so.2`、`libinput.so.10`、`libudev.so.1`、`/dev/dri/card0` ✓。

---

## 5. 踩雷速查

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
| PowerShell→ssh→板子 三層引號，grep `|` 樣式被拆壞 | 別用 `|` 交替；改 `grep -e A -e B`，或多次 grep |

---

## 6. 待辦 / 下一步

- [ ] 重編 linuxkms 版並在實體 DSI 面板驗證（第 4b 節）；處理畫面旋轉。
- [ ] 確認重編後二進位 **沒有**連到 `libgbm.so.1`（`ldd` 或 readelf 檢查）。
- [ ] 觸控輸入測試（libinput / `/dev/input`）。
- [ ] 之後可換 femtovg(GPU) 提升效能 —— 但需先解決板子無標準 libgbm.so.1 的問題。
- [ ] 開機自動啟動（systemd service）。
```

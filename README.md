# STM32MP1 開發板專案

STM32MP1 Discovery kit（OpenSTLinux）的連線、遠端桌面與 **Rust + Slint GUI** 交叉編譯實作紀錄。
本倉庫收錄 PC 端工具腳本、GUI 專案原始碼、systemd 服務設定，以及完整的開發/除錯筆記。

> 板子：STM32MP1（Dual Cortex‑A7 + Copro Cortex‑M4），OpenSTLinux（Yocto，Weston 5.0 / Wayland），root 自動登入、無密碼。

---

## 倉庫內容

| 路徑 | 說明 |
|------|------|
| `probe_mp1.py` | 自動偵測序列埠鮑率（`--poke` 送 Enter 觸發回應） |
| `monitor_mp1.py` | 即時監控／記錄序列埠輸出（`--log`、`--hex`） |
| `run_cmd_mp1.py` | 對板子 shell 送單一指令並擷取乾淨回應（sentinel marker 判斷結束） |
| `mp1gui/` | Rust + Slint 系統儀表板 GUI 專案（交叉編譯成 armhf） |
| `mp1-vnc.service` | 開機自動啟動 VNC 桌面的 systemd unit |
| `MP1_知識總整理.md` | 板子設定、VNC、疑難排解總整理 |
| `MP1_Rust_GUI開發筆記.md` | GUI 交叉編譯與顯示後端的完整踩雷筆記 |
| `網路設定.md` | 直連網路、靜態 IP 設定與排查紀錄 |
| `stm32mp1starter.pdf` | 入門參考文件 |

> 已透過 `.gitignore` 排除：flash image（`*.tar.gz`，>1GB）、Rust 編譯產物（`mp1gui/target/`）、編譯出的二進位 `mp1gui-arm`、第三方工具 `MobaXterm_Portable_v26.3/`。

---

## 連線方式

| 介面 | 位址 | 用途 |
|------|------|------|
| 序列主控台 | `COM99 @ 115200 8N1`（ST‑Link VCP） | 下指令、看 log；root 自動登入 |
| eth0（有線直連） | `100.192.0.50/24`（靜態，PC 端 `100.192.0.23`） | PC ↔ 板子直連、VNC、SSH |
| wlan0（WiFi） | DHCP | 對外網路（apt 下載） |

- 直連線上**無 DHCP**，板子 eth0 採靜態 IP（`/etc/systemd/network/10-eth0-static.network`）。
- SSH 為 **Dropbear**（非 OpenSSH，socket 啟動）；root 無密碼，改用金鑰登入。設好 `~/.ssh/config` 後可直接 `ssh mp1` 免密碼進 root。
  - ⚠️ Dropbear **不支援 X11 forwarding**（`ssh -X` 無效，GUI 須走 VNC）。
- 檔案傳輸：`scp`／SFTP（已裝 `openssh-sftp-server`，WinSCP/MobaXterm 可用）。

### PC 端工具用法（PowerShell）

```powershell
$env:PYTHONIOENCODING="utf-8"          # 避免中文亂碼
python probe_mp1.py --poke             # 偵測序列埠鮑率
python monitor_mp1.py --log mp1.log    # 即時監控序列輸出
python run_cmd_mp1.py "ifconfig eth0"  # 送指令取回應
```

---

## VNC 遠端桌面

由於 Weston 5.0 **沒有 VNC/RDP backend**，無法鏡像實體 HDMI 畫面，因此採用**虛擬桌面**：TigerVNC `Xvnc :1` + openbox WM + ST demo + xterm。

- 連線：`100.192.0.50:5901`（走直連線最穩），client 用 RealVNC Viewer。
- 開機自動啟動：`mp1-vnc.service`（部署到板子 `/etc/systemd/system/`，已 `enable`）。
  - 管理：`systemctl start|stop|restart|status mp1-vnc`
- 桌面操作：空白處**按右鍵**為萬用入口（Terminals → Xterm）；切換視窗用 **Ctrl+Alt+→/←**（Alt+Tab 被本機 Windows 攔截）。
- 黑屏／空桌面屬正常（背景是黑的、視窗被關光），右鍵叫回 Xterm，要 demo 打 `demo-x11` 即可。

> 詳細除錯與限制見 [`MP1_知識總整理.md`](MP1_知識總整理.md)。

---

## Rust + Slint GUI（`mp1gui/`）

一支系統儀表板 GUI：即時顯示 uptime / 記憶體 / 負載 + 計數按鈕，讀取板子真實 `/proc` 資料。

### 專案結構

```
mp1gui/
├─ Cargo.toml      # 相依與 Slint features
├─ build.rs        # 呼叫 slint_build 編譯 .slint
├─ ui/app.slint    # GUI 版面（Slint 語言；文字一律用英文，板子無中文字型）
├─ src/main.rs     # 讀 /proc、綁定 callback、Timer 每秒刷新
├─ Dockerfile      # armhf(buster) 編譯環境
└─ deploy.ps1      # 從 image 取出二進位 → scp 進板子
```

### 為何用 Docker + QEMU 原生 armhf 編譯

板子為 **armv7l、glibc 2.28、RAM ~427M、無 gcc/rust**，不能在板子上編。採 `arm32v7/debian:buster`（glibc 剛好 2.28，與板子相容）在 QEMU 下原生編譯，比 Windows 交叉連結 + sysroot 可靠。

### 建置與部署（PowerShell）

```powershell
# 0) 一次性：Docker Desktop 開著，啟用 arm 模擬
docker run --privileged --rm tonistiigi/binfmt --install arm

# 1) 編譯（QEMU 模擬，約 15–20 分）
docker build --platform linux/arm/v7 -t mp1gui-build "C:\Stone\AI_try\MP1\mp1gui"

# 2) 取出二進位
docker create --platform linux/arm/v7 --name mp1x mp1gui-build
docker cp mp1x:/src/target/release/mp1gui "C:\Stone\AI_try\MP1\mp1gui\mp1gui-arm"
docker rm mp1x

# 3) 傳進板子並執行
scp "C:\Stone\AI_try\MP1\mp1gui\mp1gui-arm" mp1:/home/root/mp1gui
ssh mp1 'chmod +x /home/root/mp1gui'
```

### 在板子上執行（VNC / X11 :1）

```sh
export DISPLAY=:1
export XAUTHORITY=/home/root/.Xauthority
unset WAYLAND_DISPLAY
/home/root/mp1gui      # 畫面出現在 VNC 桌面，PC 用 RealVNC 連線可看可點
```

### 顯示後端現況

| 後端 | 狀態 | 備註 |
|------|------|------|
| X11 (winit) → Xvnc :1 | ✅ 可用、已驗證 | 軟體算繪，不需 GPU |
| Wayland (winit) → 實體面板 | ❌ | Weston 5.0 太舊，winit 要的 `xdg_wm_base` 不提供 |
| X11 → Xwayland :0 | ❌ | 舊 Weston 無對外 X socket |
| linuxkms / DRM → 直接畫到 DSI 面板 | ⚠️ 計畫中 | 設定已改、尚未重編驗證 |

> ⚠️ **不要啟用 `renderer-femtovg`**：板子的 `libgbm.so` 是 Vivante 廠商版、無標準 `libgbm.so.1` soname，連到 gbm 會起不來。軟體算繪走 DRM dumb buffer，不碰 gbm。

完整顯示後端踩雷見 [`MP1_Rust_GUI開發筆記.md`](MP1_Rust_GUI開發筆記.md)。

---

## 已知限制

- **無法即時鏡像實體 HDMI 螢幕**：Weston 5.0 沒有 VNC/RDP backend；VNC 看到的是另開的虛擬桌面。
- **硬體加速 demo 在 VNC 不能用**（白屏）：Video、Camera、3D Pict (GPU)、AI、intro 影片。
- VNC 桌面可正常用：2D 選單、netdata、Bluetooth、資訊頁、終端機、一般 GTK X11 程式。

---

## 待辦

- [ ] 重編 linuxkms 版並在實體 DSI 面板驗證（含畫面旋轉、確認未連到 `libgbm.so.1`）。
- [ ] 觸控輸入測試（libinput / `/dev/input`）。

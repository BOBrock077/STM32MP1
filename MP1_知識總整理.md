# STM32MP1 開發板 — 設定與操作總整理

> 最後更新：2026-06-02
> 工作目錄：`C:\Stone\AI_try\MP1`（PC 端）

---

## 1. 裝置概觀

| 項目 | 內容 |
|------|------|
| 裝置 | STM32MP1 開發板（Discovery kit，Dual Cortex-A7 + Copro Cortex-M4） |
| 作業系統 | OpenSTLinux（Yocto "thud"，但用 dpkg/apt 套件管理，Debian 風格） |
| 圖形環境 | Weston 5.0.0（Wayland）+ ST demo launcher（Python GTK3） |
| 套件來源 | `http://packages.openstlinux.st.com/1.2 thud`（apt 可用，需 WiFi 對外） |
| root | 自動登入、**無密碼**（`root NP`） |

---

## 2. 連線方式與 IP

| 介面 | 位址 | 用途 | 備註 |
|------|------|------|------|
| **序列主控台** | **COM99 @ 115200 8N1** | 下指令、看 log | ST-Link Virtual COM Port；root 自動登入 |
| **eth0（有線）** | **`100.192.0.50/24`**（靜態） | PC↔板子直連、VNC | PC 端 `100.192.0.23`；此線**無 DHCP/閘道** |
| **wlan0（WiFi）** | `192.168.0.8/24`（DHCP） | 對外網路（apt 下載） | 連 **ASTRON_BIO**（密碼 `astron808`），閘道 192.168.0.99 |

- eth0 靜態設定檔：`/etc/systemd/network/10-eth0-static.network`
- WiFi 連線：`wpa_supplicant -B -i wlan0 -c /tmp/wpa_astron.conf -D nl80211` + `udhcpc -i wlan0`

---

## 3. PC 端自製工具（`C:\Stone\AI_try\MP1\`）

| 檔案 | 用途 | 範例 |
|------|------|------|
| `probe_mp1.py` | 自動偵測序列埠鮑率 | `python probe_mp1.py --poke` |
| `monitor_mp1.py` | 即時監控/記錄序列輸出 | `python monitor_mp1.py --log mp1.log` |
| `run_cmd_mp1.py` | 送指令並擷取乾淨回應（sentinel marker 判斷結束） | `python run_cmd_mp1.py "ifconfig"` |

> 註：PowerShell 執行前先 `$env:PYTHONIOENCODING="utf-8"` 避免中文亂碼。

---

## 4. VNC 遠端桌面

**方案**：虛擬桌面（Xvnc），**非**鏡像實體 HDMI 螢幕（Weston 5.0 無 VNC/RDP backend，做不到鏡像）。

| 項目 | 值 |
|------|-----|
| 連線位址 | **`100.192.0.50:5901`**（走直連線最穩） |
| VNC 密碼 | **`astron808`**（傳統 VNC 僅取前 8 碼） |
| 桌面組成 | tigervnc `Xvnc :1` + **openbox** WM + ST demo + xterm |
| 啟動腳本 | `/home/root/.vnc/xstartup`、密碼檔 `/home/root/.vnc/passwd` |
| PC 端 client | RealVNC Viewer |

### VNC 桌面操作（WM = openbox）

| 操作 | 方法 |
|------|------|
| **桌面右鍵選單** ⭐ | 空白處**按右鍵** → 最可靠的萬用入口（含 Terminals → Xterm）。不靠鍵盤、不怕關光 |
| 開新終端機 | 右鍵 → Terminals → Xterm；或 **Ctrl+Alt+T**（焦點要在 VNC 內） |
| 切換視窗 | **Ctrl+Alt+→ / ←**（**Alt+Tab 不可用**：被本機 Windows 攔截） |
| 關閉視窗 | 標題列 **✕**，或 **Ctrl+Alt+C** |
| **一鍵修復 demo** | 終端機打 **`demo-x11`** |

> openbox 自訂設定在 `/home/root/.config/openbox/rc.xml`（已加 C-A-t / C-A-Right / C-A-Left / C-A-c 等 keybind）；改完 `openbox --reconfigure` 生效。

### ⚠️ 救命：畫面全黑 / 空桌面怎麼辦

VNC 桌面是 **openbox**，背景是黑的。若把視窗用 **✕ 關光** 或 demo 沒起來，就只剩一片黑。**不是壞掉**，照下面救：

1. **空白桌面按右鍵** → 選單 → **Terminals → Xterm**（叫回終端機）
2. 要 demo → 在終端機打 **`demo-x11`**（約 15 秒選單出現）
3. 連右鍵都沒反應 → 先在 VNC 畫面**點一下**讓焦點進 VNC，再試

> 注意：`Ctrl+Alt+T` 連按多次會開出一堆 xterm **疊在同位置**，看似沒反應其實都開了 → 用右鍵選單比較不會搞混。

### 手動啟動/重啟 VNC（從序列埠）

```sh
vncserver -kill :1 2>/dev/null; pkill -f 'Xvnc :1'; sleep 2
rm -f /tmp/.X11-unix/X1 /tmp/.X1-lock /home/root/.vnc/*.pid
vncserver :1 -geometry 1280x800 -SecurityTypes VncAuth
```

---

## 5. 疑難排解

| 症狀 | 原因 | 解法 |
|------|------|------|
| **白屏** | demo 的 intro 影片 / Video / Camera / 3D Pict / AI 用 GPU/VPU 硬體加速，Xvnc 純軟體畫不出 | `demo-x11`（自動關影片）；這些硬體 demo 在 VNC 無法用 |
| **黑屏 / 空桌面** | ① 視窗被 **✕ 關光**（最常見，非當機）；② 啟動 demo 漏 `GDK_BACKEND=x11`/`XDG_RUNTIME_DIR`。**已排除 OOM**（記憶體還有 ~270M） | 右鍵桌面 → Terminals → Xterm；要 demo 打 `demo-x11` |
| **Ctrl+Alt+T 像沒反應** | 新 xterm 疊在同位置、或焦點不在 VNC 內 | 改用右鍵選單；或先點 VNC 畫面再按 |
| **VNC Authentication failure** | 密碼錯 / 超過 8 碼歧義 | 密碼用 `astron808`（前 8 碼 `astron80`） |
| **vncserver 說 already running** | stale 鎖檔；kill 與 start 時序競爭 | 先清 `/tmp/.X1*-lock`、`/tmp/.X11-unix/X1`、`*.pid`，分開兩步再啟動 |
| **磁碟 100% 滿** | `/home/root/.cache/pip`（~196M） | `rm -rf /home/root/.cache/pip`（純快取、安全） |
| **Alt+Tab 沒反應** | 被本機 Windows 攔截 | 改用 Ctrl+Alt+方向鍵；或用 RealVNC「送出按鍵」 |
| **demo 開不起來（another instance）** | singleton 鎖 `/var/lock/demo_launcher.lock`（fcntl，行程死即釋放） | 先 `pkill -f demo_launcher.py` |

### 停止會白屏的 demo 影片
```sh
pkill -f touch-event-gtk-player; pkill -f launch_video.sh
```

---

## 6. 已安裝的套件（apt，存於 OpenSTLinux 套件庫）

`tigervnc`、`xauth`、`matchbox-wm`（已棄用，改 openbox）、`openbox`、`imagemagick`（截圖用 `import`）。
（`matchbox-panel-2` 會 segfault，勿用。）

### 螢幕截圖（除錯用）
```sh
DISPLAY=:1 XAUTHORITY=/home/root/.Xauthority import -window root /tmp/x.png
# 板子上開 HTTP 給 PC 抓： cd /tmp && python3 -m http.server 8088 --bind 100.192.0.50
# PC： Invoke-WebRequest http://100.192.0.50:8088/x.png -OutFile x.png
```

---

## 7. 尚未完成 / 下一步

- [x] **開機自動啟動（2026-06-02 完成）**：systemd service `mp1-vnc.service`（`/etc/systemd/system/`，已 `enable`）。開機自動起 Xvnc:1 + openbox + 終端機 + demo（自動關白屏影片）。已實測 `systemctl start` 成功拉起整套。
    - 管理：`systemctl start|stop|restart|status mp1-vnc`（從序列埠或 `ssh mp1`）
    - service 檔來源在 PC：`C:\Stone\AI_try\MP1\mp1-vnc.service`（改完用 `scp ... mp1:/etc/systemd/system/` 再 `systemctl daemon-reload`）
    - xstartup `/home/root/.vnc/xstartup` 內含：xterm + (搶 singleton→啟動 demo→關影片) + `exec openbox`
- [x] **檔案傳輸 / SSH（2026-06-02 完成）**：SSH server 實際是 **Dropbear**（非 OpenSSH，socket 啟動），root 無密碼故用金鑰。PC 端 `~/.ssh/id_ed25519`（無 passphrase），公鑰已在板子 `~/.ssh/authorized_keys`。**用 `ssh mp1` 連即免密碼進 root**（`~/.ssh/config` 已設 `HostKeyAlgorithms +ssh-rsa`，因板子只有 RSA host key；直接 `ssh root@IP` 會 no matching host key）。已裝 `openssh-sftp-server`→ WinSCP/MobaXterm SFTP 拖檔可用。
- ⚠️ **Dropbear 不支援 X11 forwarding**：`ssh -X` 行不通，GUI 仍須走 VNC。
- 備援傳檔：可用直連線上的 HTTP（板子→PC 下載）。

---

## 8. 重要限制總結

- **無法即時鏡像實體 HDMI 螢幕**：Weston 5.0 沒有 VNC/RDP backend。VNC 看到的是另開的虛擬桌面。
- **硬體加速 demo 在 VNC 不能用**（白屏）：Video、Camera、3D Pict(GPU)、AI、intro 影片。
- 可正常用：demo 2D 選單、netdata、Bluetooth、資訊頁、終端機、一般 GTK X11 程式。

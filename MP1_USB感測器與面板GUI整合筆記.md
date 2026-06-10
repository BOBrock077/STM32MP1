# STM32MP1 — USB 感測器整合 + GUI 投到實體面板（實作筆記）

> 日期：2026-06-10
> 目標：透過 **USB** 跟外部裝置溝通，把回傳的數值即時顯示在**板子的實體 DSI 面板**上。

---

## 0. 成果總覽

一支 Rust + Slint GUI（`mp1gui`），跑在 STM32MP1 的**實體 DSI 面板**上（linuxkms / DRM 軟體算繪），每秒透過 USB 對外部 **SGX 感測板**送 `SC RE` 查詢，解析回應後即時顯示：

```
Temp     : 23.5 C
Humidity : 75.6 %
Flow     : 306.0 sml/min
```

過程中解掉三個硬骨頭：
1. **板子核心沒有 FTDI 驅動** → 自行交叉編 `ftdi_sio.ko` 並 force-load。
2. **裝置是請求-回應協定** → 破解出指令格式（`SC RE` + CR 結尾）與資料格式。
3. **linuxkms 投實體面板拿不到 DRM master** → 照抄 weston 用 `openvt -s` 起在前景 VT。

---

## 1. 硬體 / 連線拓樸

```
[SGX 感測板] --UART--> [FT232RL] --USB--> [STM32MP1 USB-A host 埠]
                                              │
                                       /dev/ttyUSB0 (ftdi_sio)
                                              │  serialport crate
                                       [mp1gui (Rust+Slint)]
                                              │  linuxkms / DRM
                                       [實體 DSI 面板 480x800]
```

- 板子：STM32MP1，核心 **Linux 4.19.94 armv7l**，OpenSTLinux（Weston 5.0）。
- 外部裝置：**FTDI FT232RL**（`lsusb` = `0403:6001`）後接 **SGX 感測板**
  - 板號（`SC RE`）：`SXT2SGXECE010010`
  - 韌體（`SC IN`）：`SXT2_SGX_ver006_20220613`
- 連線管理見 [`MP1_知識總整理.md`](MP1_知識總整理.md)：`ssh mp1`（Dropbear 金鑰，免密）、eth0 直連 `100.192.0.50`。

---

## 2. Part A — USB-serial 驅動（`ftdi_sio.ko` 交叉編 + force-load）

### 2.1 問題：核心沒有 FTDI 驅動

查板子 `/proc/config.gz`：

| 旗標 | 值 | 意義 |
|------|-----|------|
| `CONFIG_USB_ACM` | `=y` | **只有 CDC-ACM** 內建（原生 USB-CDC 裝置 → `/dev/ttyACM0` 免驅動） |
| `CONFIG_USB_SERIAL*` | 未設 | **沒有** FTDI / CH340 / CP210x / PL2303 驅動 |
| `CONFIG_MODVERSIONS` | `=y` | 載入模組要對符號 CRC |
| `CONFIG_MODULE_FORCE_LOAD` | `=y` | ✅ 可 `insmod -f` 繞過 CRC/vermagic |
| `CONFIG_MODULE_SIG` | 未設 | 不需簽章 |

→ FT232 插上會枚舉（`lsusb` 看得到）但**沒有 `/dev` 節點**，因為缺 `ftdi_sio`。

- ❌ apt 裝不到：ST OpenSTLinux feed（`packages.openstlinux.st.com`）只有 userspace `libftdi1-2`，**沒有** `ftdi_sio` 核心模組套件。
- ❌ 抓現成 `.ko`：vermagic 必須完全吻合這顆 ST build，網路上不會有。
- ✅ **只能自己編**（靠 `MODULE_FORCE_LOAD=y` force-load）。

### 2.2 解法：交叉編 + force-load

做法在 `ftdi-mod/`，用 x86 交叉工具鏈編（不走 QEMU，快），原始碼用 kernel.org 的 stable **linux-4.19.94**，`.config` 用板子的 `/proc/config.gz`。

**踩雷：gcc 10 預設 `-fno-common`** 撞上 4.19 自帶的 `dtc`（`multiple definition of yylloc`）→ 給 host 工具加 `HOSTCFLAGS="-O2 -fcommon"`。另外 host 端要裝原生 `gcc`（編 `fixdep` 等工具），不是只有交叉 gcc。

關鍵步驟（`ftdi-mod/Dockerfile`）：
```dockerfile
FROM debian:bullseye
RUN apt-get install -y bc bison flex libssl-dev libelf-dev make cpio kmod \
      gcc gcc-arm-linux-gnueabihf libc6-dev xz-utils ca-certificates wget
# 下載 linux-4.19.94，board.config -> .config，開兩個選項：
RUN ./scripts/config --module CONFIG_USB_SERIAL \
 && ./scripts/config --module CONFIG_USB_SERIAL_FTDI_SIO \
 && make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- HOSTCFLAGS="-O2 -fcommon" olddefconfig \
 && make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- HOSTCFLAGS="-O2 -fcommon" modules_prepare \
 && make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- HOSTCFLAGS="-O2 -fcommon" M=drivers/usb/serial
# 產出 drivers/usb/serial/usbserial.ko、ftdi_sio.ko
```

編出的 **vermagic 與板子完全吻合**：`4.19.94 SMP preempt mod_unload modversions ARMv7 p2v8`。

### 2.3 上板載入

```sh
# .ko 放在板子 /home/root/mods/
insmod -f /home/root/mods/usbserial.ko
insmod -f /home/root/mods/ftdi_sio.ko        # -f 繞過 MODVERSIONS CRC
```
dmesg：
```
usbcore: registered new interface driver ftdi_sio
usb 2-1.1: Detected FT232RL
usb 2-1.1: FTDI USB Serial Device converter now attached to ttyUSB0
```
→ **`/dev/ttyUSB0`**（group dialout）出現。`module_layout: kernel tainted` 是 force-load 的預期警告，無害。

> ⚠️ 目前是手動 `insmod`，**重開機後要重載**（尚未設開機自動載入）。

---

## 3. Part B — 裝置通訊協定（SGX 感測板）

### 3.1 破解過程

被動監聽 10 秒：**收不到任何資料** → 裝置是**請求-回應**型（要先送指令）。用腳本（`ftdi-mod/sertest.sh`，scp 到板子跑，避開 PowerShell→ssh→sh 三層引號）試 `SC RE` / `SC IN` 配 CR/LF/CRLF/無結尾各一輪，結論：

| 項目 | 結論 |
|------|------|
| 線路設定 | **115200 8N1**，無流控 |
| 指令結尾 | **CR（`\r`）** ← 重點！LF / 無結尾裝置不理；CRLF 會殘留上一筆 |
| 指令格式 | ASCII `SC <操作>\r` |
| 回應結構 | echo + 解析欄位（`command string Type/Operation/...`）+ 最後一行 `標籤:值` |

### 3.2 資料格式

`SC RE` 回傳的量測資料行：
```
nT1:23.500000 C,nH1:75.599998 %,nF1:306.000000 sml/min,
```
| 欄位 | 意義 | 範例 |
|------|------|------|
| `nT1` | 溫度 | 23.5 °C |
| `nH1` | 濕度 | 75.6 % |
| `nF1` | 流量 | 306 sml/min |

（裝置偶爾改回 `Sensor board:SXT2SGXECE010010` 板號，GUI 端忽略非量測行。）

### 3.3 手動操作工具

- `ftdi-mod/sc.sh`：板子上 `sh /home/root/sc.sh RD` → 送 `SC RD\r` 印回應。
- 互動式：`microcom -s 115200 /dev/ttyUSB0`（Enter 送 CR，Ctrl-X 離開）。板子也有 `minicom`。
- 純手動：`stty -F /dev/ttyUSB0 115200 ... raw`；`cat /dev/ttyUSB0 &`（讀）+ `printf 'SC RE\r' > /dev/ttyUSB0`（寫）。

---

## 4. Part C — GUI 程式（`mp1gui/src/main.rs`）

- `Cargo.toml` 加 **`serialport = "4"`**（Linux 用 libudev，板子已有 `libudev.so.1`）。
- 背景 thread：
  1. 埠優先 **`/dev/ttyUSB0`** 再 `/dev/ttyACM0`（哪個存在用哪個），115200 8N1，開 DTR/RTS。
  2. 每秒：`clear(Input)` → 送 `SC RE\r` → 收回應（**等最多 2 秒讓回應開始到、收到後 idle 才結束**；早期 bug 是第一次 read 逾時就 break、抓不到慢回應）。
  3. `parse_reply()` 專抓含 `nT1/nH1/nF1` 的行，格式化成 `Temp/Humidity/Flow` 三行；非量測行回空字串 → GUI 保留上一筆，不閃爍。
  4. 自動重連（拔插不死）。
- `ui/app.slint`：多一個「Sensor (SC RE)」GroupBox，顯示連線狀態 + 量測值。
- 除錯：serial thread `eprintln!("[serial] ...")` → 寫進 `/tmp/gui.log`。

---

## 5. Part D — 投到實體 DSI 面板（linuxkms）

- `Cargo.toml` features：`backend-linuxkms-noseat` + `renderer-software`（**不要** femtovg / gbm — 板子 `libgbm.so` 是 Vivante 版、無標準 soname）。
- 執行期相依板子都有：`libdrm.so.2`、`libinput.so.10`、`libudev.so.1`、`/dev/dri/card0`。

### ⚠️ 關鍵踩雷：DRM master 權限

直接 `systemd-run` 或裸跑會：
```
Error presenting framebuffer on screen: Permission denied (os error 13)
```
原因：沒掛在**前景 VT** 上，拿不到 DRM master（fbcon 佔著 CRTC）。

**解法照抄 `weston-start`：用 `openvt -s` 起一個新前景 VT 來跑。** 見 `mp1gui/run-panel.sh`：
```sh
systemctl stop weston          # 釋放 DRM master
openvt -s -- sh -c 'SLINT_BACKEND=linuxkms exec /home/root/mp1gui >/tmp/gui.log 2>&1'
```
log 出現 `Using Software renderer` / `Rendering at 480x800`、無 permission denied → 成功。跑在 VT 上，**ssh 關線不死**。

- 面板原生 **480×800 直式**（weston 是 transform=270 轉橫式）。若 GUI 方向不對，`run-panel.sh` 加 `SLINT_KMS_ROTATION=270`。
- ⚠️ **VNC 看不到 linuxkms 畫面**（Weston 無 VNC backend、linuxkms 走 DRM 不經 X）。要遠端看得改用 X11/VNC 模式跑（`DISPLAY=:1 ...`），但序列埠一次只能一個程式開。

---

## 6. Part E — Docker 建置加速

QEMU 原生編 armhf 約 **40 分**（Slint 相依樹大）。兩個加速法：

1. **Dockerfile 相依快取結構**（`mp1gui/Dockerfile`）：先用 stub crate 編相依層（`Cargo.toml`/`Cargo.lock` 不變就吃快取），再 COPY 真實碼編 `mp1gui`。改 `src`/`ui` 重編從 40 分降到 **1–2 分**。（**首次用新 Dockerfile 仍會慢一次**建立快取。）
2. **容器內增量編**（本次迭代用的）：直接進舊映像容器，`docker cp` 換 `src/main.rs`，`cargo build --release` 重用 `/src/target` 的相依快取 → **約 1 分**：
   ```powershell
   docker run -d --name mp1edit --platform linux/arm/v7 mp1gui-build sleep infinity
   docker cp src\main.rs mp1edit:/src/src/main.rs
   docker exec mp1edit sh -c "cd /src && cargo build --release"
   docker cp mp1edit:/src/target/release/mp1gui mp1gui-arm
   docker rm -f mp1edit
   ```

---

## 7. 檔案清單（今天新增/修改）

| 路徑 | 說明 |
|------|------|
| `ftdi-mod/Dockerfile` | 交叉編 `ftdi_sio.ko` + `usbserial.ko` 的環境 |
| `ftdi-mod/board.config` | 板子 `/proc/config.gz`（當 .config 用） |
| `ftdi-mod/usbserial.ko`, `ftdi_sio.ko` | 編好的核心模組（vermagic 吻合板子） |
| `ftdi-mod/sertest.sh` | 序列協定探測腳本（多結尾符測試） |
| `ftdi-mod/sc.sh` | 板子上手動下 `SC <op>` 的小工具 |
| `mp1gui/run-panel.sh` | 用 `openvt -s` 把 GUI 起在實體面板 |
| `mp1gui/src/main.rs` | 加 SC RE 輪詢 + 量測解析 |
| `mp1gui/ui/app.slint` | 加「Sensor (SC RE)」顯示框 |
| `mp1gui/Dockerfile` | 改成相依快取結構 |
| `mp1gui/Cargo.toml` | 加 `serialport`、`backend-linuxkms-noseat` |

板子上：`/home/root/mods/*.ko`、`/home/root/mp1gui`、`/home/root/run-panel.sh`、`/home/root/sc.sh`。

---

## 8. 操作速查

```sh
# 1) 載入 FTDI 驅動（重開機後需重做）
ssh mp1 'insmod -f /home/root/mods/usbserial.ko; insmod -f /home/root/mods/ftdi_sio.ko'

# 2) 手動測感測器
ssh mp1 'sh /home/root/sc.sh RE'        # 送 SC RE，看回應

# 3) 把 GUI 投到實體面板
ssh mp1 'sh /home/root/run-panel.sh'

# 4) 看 GUI 的 serial 除錯
ssh mp1 'cat /tmp/gui.log'

# 5) 關掉 GUI、還原 weston 桌面
ssh mp1 'pkill -x mp1gui; systemctl start weston'
```

開發端重編（改了 GUI）：用第 6 節的「容器內增量編」→ scp 上板前先 `pkill -x mp1gui`（否則執行檔被佔、scp 會 ETXTBSY）。

---

## 9. 待辦 / 已知限制

- [ ] **FTDI 驅動開機自動載入**（目前手動 `insmod`，重開機要重做）→ 可放 `/etc/modules-load.d/` + 把 .ko 進 `/lib/modules` 後 `depmod`，或寫 systemd service。
- [ ] **GUI 開機自動啟動**（systemd service 包 `openvt -s`）。
- [ ] **觸控輸入**：linuxkms 已開了 `/dev/input/event0/1`，但 libinput 觸控還沒測。
- [ ] **畫面旋轉**確認（若面板方向不對，加 `SLINT_KMS_ROTATION=270`）。
- [ ] 確認 `SC RE` 為何有時回板號、有時回量測（裝置端行為），必要時改用更穩定的量測指令。
- 限制：實體面板（linuxkms）的畫面**無法同步到 VNC**（Weston 5.0 無 VNC backend）。

---

## 10. 相關文件

- [`MP1_知識總整理.md`](MP1_知識總整理.md) — 板子連線 / VNC / 網路 / 疑難排解
- [`MP1_Rust_GUI開發筆記.md`](MP1_Rust_GUI開發筆記.md) — Rust+Slint 交叉編譯與顯示後端踩雷
- [`網路設定.md`](網路設定.md) — 直連網路與靜態 IP

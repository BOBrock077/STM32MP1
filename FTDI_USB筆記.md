# FTDI USB 與 Linux USB 掛載筆記

> 重點觀念：FTDI 不是「掛載」問題，是「缺 driver」問題。
> 兩件事是不同類型的 USB 裝置，常被搞混。

---

## 1. 一般 Linux USB 裝置的「掛載」流程

關鍵：**只有「儲存類」USB（隨身碟、外接硬碟）才需要 mount。**

```
插入 USB
  → 核心偵測 (USB 控制器產生事件)
  → 比對 VID/PID，載入對應 driver
      ‧ usb-storage   → 出現 block device  /dev/sdb, /dev/sdb1
  → udev 建立 /dev 節點、可選自動掛載
  → mount /dev/sdb1 /mnt/usb   (掛上檔案系統才能讀寫檔案)
```

### 觀察指令

| 指令 | 用途 |
|------|------|
| `dmesg -w` | 插入時核心有沒有認到、載了哪個 driver |
| `lsusb` | 看 VID:PID（USB 層級有沒有看到這顆晶片） |
| `lsblk` / `ls /dev/sd*` | 看有沒有變成 block device |
| `mount /dev/sdb1 /mnt` | 真正掛載檔案系統 |

**重點觀念：要走到「mount」，前提是這個裝置會被歸類成 block device（區塊裝置 / 有檔案系統）。**

---

## 2. FTDI 其實不是「掛載」問題

FTDI（如 FT232）是 **USB-to-Serial 轉接晶片**，它**不是儲存裝置**。

它正確運作時：

- driver `ftdi_sio` 會把它變成一個 **character device（字元裝置）**：`/dev/ttyUSB0`
- 你**不 mount 它**，而是直接用序列埠去 open：
  - `screen /dev/ttyUSB0 115200`
  - `minicom`
  - 或程式碼開 tty

> 「掛載流程」對 FTDI 根本不適用。它要的是 **driver**，不是 mount。

---

## 3. 目前板子的真正問題

從 `ftdi-mod/board.config`（板子 STM32MP1 出廠核心 4.19.94 的設定）裡，關鍵這一行：

```
# CONFIG_USB_SERIAL is not set
```

意思是：**板子出廠核心在編譯時根本沒把 USB serial 子系統包進去**，連帶 `ftdi_sio.ko` / `usbserial.ko` 都不存在。

### 現象

- `lsusb` **看得到** FTDI 晶片（USB 控制器層正常）
- 但 `dmesg` **不會**出現 `ttyUSB0`
- `/dev/ttyUSB0` **不存在**
- 因為沒有 driver 去 bind 它 → 抓不到序列埠

---

## 4. 解法：`ftdi-mod/Dockerfile`

那個 Dockerfile 就是針對這個問題，補編缺的核心模組。

板子核心特性：
- Linux 4.19.94 armv7l
- `MODVERSIONS=y`
- `MODULE_SIG not set`（沒簽章驗證）
- `MODULE_FORCE_LOAD=y`（可強制載入，繞過 CRC/vermagic 不符）

### Build 流程（在 x86 上交叉編譯，不需 QEMU）

1. 用 x86 + armhf 交叉工具鏈，下載**相同版本** kernel 4.19.94 原始碼
2. 套上**板子自己的 `.config`**（保證 vermagic/MODVERSIONS 一致）
3. 只把 `CONFIG_USB_SERIAL` 與 `CONFIG_USB_SERIAL_FTDI_SIO` 開成 module
4. 只編 `drivers/usb/serial` → 產出 `usbserial.ko` + `ftdi_sio.ko`

```bash
# 在 ftdi-mod/ 目錄
docker build -t ftdi-mod .
# 從 image 取出 .ko（範例）
docker create --name x ftdi-mod
docker cp x:/build/linux-4.19.94/drivers/usb/serial/usbserial.ko .
docker cp x:/build/linux-4.19.94/drivers/usb/serial/ftdi_sio.ko .
docker rm x
```

### 板子端載入步驟

```bash
# 把兩個 .ko 傳到板子 (scp)，然後：
insmod usbserial.ko      # 先 base
insmod ftdi_sio.ko       # 再 FTDI
# CRC/vermagic 對不上時改用強制載入：
#   modprobe --force ftdi_sio   或   insmod 強載（板子 MODULE_FORCE_LOAD=y 可繞過）

# 插上 FTDI，檢查：
dmesg | tail
ls /dev/ttyUSB*          # 應該出現 /dev/ttyUSB0
```

---

## 一句話總結

> 你不是「FTDI 掛載失敗」，而是「板子核心沒有 USB serial driver，所以 FTDI 插上去不會生出 `/dev/ttyUSB0`」。
> 解法不是 mount，而是把缺的 `ftdi_sio.ko` / `usbserial.ko` 補編出來載進核心。

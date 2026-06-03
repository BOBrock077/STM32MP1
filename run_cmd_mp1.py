"""
run_cmd_mp1.py — 對 MP1 (COM99) 的 Linux root shell 送指令並擷取回應

原理：
  透過序列埠送出一行指令，並在其後串接一個 `echo <標記>`。
  shell 執行完指令後會印出該標記，程式讀到標記即知「輸出結束」，
  比靠提示字元判斷更可靠。同時會自動移除 shell 回顯的指令本身，
  只回傳乾淨的指令輸出。

用法：
    python run_cmd_mp1.py "uname -a"
    python run_cmd_mp1.py "cat /proc/cpuinfo"
    python run_cmd_mp1.py "ls -l /sys/class/thermal" --timeout 8
    python run_cmd_mp1.py "date" --raw          # 顯示原始（含回顯與標記）

注意：這會對裝置「送指令」。請確認指令安全、不會影響系統。
"""

import argparse
import sys
import time

import serial

# 確保在 Windows 主控台輸出 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 標記：用 "" 把字串切開，讓「shell 回顯的指令列」與「實際印出的標記」長得不一樣，
# 這樣搜尋實際標記時不會誤中回顯那一行。
TOKEN = "MP1_DONE_a7f3"
MARKER = f"@@{TOKEN}@@"                       # 實際輸出會出現這個完整字串
ECHO_CMD = f'echo "@@""{TOKEN}""@@"'          # shell 回顯這行，但因有 "" 不含完整 MARKER


def run_command(ser: serial.Serial, cmd: str, timeout: float) -> bytes:
    ser.reset_input_buffer()
    line = f"{cmd}; {ECHO_CMD}\r\n"
    ser.write(line.encode("utf-8"))
    ser.flush()

    buf = bytearray()
    deadline = time.monotonic() + timeout
    marker_bytes = MARKER.encode("utf-8")
    while time.monotonic() < deadline:
        chunk = ser.read(4096)
        if chunk:
            buf.extend(chunk)
            if marker_bytes in bytes(buf):
                break
    return bytes(buf)


def extract_output(raw: bytes, cmd: str) -> str:
    """從原始擷取資料中抽出乾淨的指令輸出。"""
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    # 1) 砍掉標記（含）之後的所有東西（標記後通常是新的 shell 提示字元）
    idx = text.find(MARKER)
    if idx != -1:
        text = text[:idx]

    # 2) 移除 shell 回顯的整行指令（我們送出的那一行會被 echo 回來）
    sent_line = f"{cmd}; {ECHO_CMD}"
    pos = text.find(sent_line)
    if pos != -1:
        text = text[pos + len(sent_line):]

    return text.strip("\n")


def main():
    ap = argparse.ArgumentParser(description="對 MP1 Linux shell 送指令並擷取回應")
    ap.add_argument("command", help="要在 MP1 上執行的指令，例如 \"uname -a\"")
    ap.add_argument("--port", default="COM99")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="等待輸出的最長秒數（預設 5）")
    ap.add_argument("--raw", action="store_true",
                    help="顯示原始擷取內容（含回顯與標記），用於除錯")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, baudrate=args.baud, bytesize=8,
                            parity=serial.PARITY_NONE, stopbits=1, timeout=0.2)
    except serial.SerialException as e:
        print(f"無法開啟 {args.port}：{e}", file=sys.stderr)
        print("（請確認沒有其他程式佔用此埠，如 PuTTY / CubeIDE）", file=sys.stderr)
        sys.exit(1)

    with ser:
        raw = run_command(ser, args.command, args.timeout)

    if not raw:
        print("（沒有收到任何回應，請確認鮑率/接線，或加大 --timeout）", file=sys.stderr)
        sys.exit(2)

    if MARKER.encode() not in raw:
        print("（在 timeout 內沒讀到結束標記，以下為目前收到的內容；"
              "可能指令仍在執行或輸出很長，請加大 --timeout）", file=sys.stderr)

    if args.raw:
        print(raw.decode("utf-8", errors="replace"))
    else:
        print(extract_output(raw, args.command))


if __name__ == "__main__":
    main()

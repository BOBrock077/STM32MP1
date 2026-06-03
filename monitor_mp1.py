"""
monitor_mp1.py — 監控 / 記錄 MP1 (COM99) 序列埠資料

持續從序列埠讀取資料，即時顯示在畫面上，並可選擇同時寫入記錄檔。
只讀不寫，不會對裝置送出任何指令。

用法：
    python monitor_mp1.py                      # 預設 115200 8N1，即時顯示
    python monitor_mp1.py --baud 9600          # 指定鮑率
    python monitor_mp1.py --log mp1.log        # 同時存成記錄檔（含時間戳）
    python monitor_mp1.py --hex                # 以十六進位顯示（適合二進位協定）

按 Ctrl+C 結束。
"""

import argparse
import datetime
import sys

import serial

# 確保在 Windows 主控台輸出 UTF-8，避免中文變亂碼
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def make_timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def main():
    ap = argparse.ArgumentParser(description="監控 MP1 序列埠資料")
    ap.add_argument("--port", default="COM99", help="序列埠名稱（預設 COM99）")
    ap.add_argument("--baud", type=int, default=115200, help="鮑率（預設 115200）")
    ap.add_argument("--bytesize", type=int, default=8, choices=[5, 6, 7, 8])
    ap.add_argument("--parity", default="N", choices=["N", "E", "O", "M", "S"])
    ap.add_argument("--stopbits", type=float, default=1, choices=[1, 1.5, 2])
    ap.add_argument("--hex", action="store_true", help="以十六進位顯示原始位元組")
    ap.add_argument("--log", help="將輸出同時寫入此記錄檔")
    args = ap.parse_args()

    parity_map = {
        "N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD, "M": serial.PARITY_MARK, "S": serial.PARITY_SPACE,
    }

    logf = open(args.log, "a", encoding="utf-8", buffering=1) if args.log else None

    def emit(line: str):
        print(line, end="", flush=True)
        if logf:
            logf.write(line)

    try:
        ser = serial.Serial(
            port=args.port, baudrate=args.baud, bytesize=args.bytesize,
            parity=parity_map[args.parity], stopbits=args.stopbits, timeout=0.2,
        )
    except serial.SerialException as e:
        print(f"無法開啟 {args.port}：{e}", file=sys.stderr)
        print("（請確認沒有其他程式佔用此埠，如 PuTTY / CubeIDE 主控台）", file=sys.stderr)
        sys.exit(1)

    print(f"已連線 {args.port} @ {args.baud} "
          f"{args.bytesize}{args.parity}{int(args.stopbits)}"
          f"{'（HEX 模式）' if args.hex else ''}  — 按 Ctrl+C 結束\n")

    line_started = False
    try:
        with ser:
            while True:
                data = ser.read(4096)
                if not data:
                    continue
                if args.hex:
                    ts = make_timestamp()
                    hexstr = " ".join(f"{b:02X}" for b in data)
                    emit(f"[{ts}] {hexstr}\n")
                else:
                    # 文字模式：逐行加時間戳，無法解碼的位元組以 . 取代
                    text = data.decode("utf-8", errors="replace")
                    for ch in text:
                        if not line_started:
                            emit(f"[{make_timestamp()}] ")
                            line_started = True
                        emit(ch)
                        if ch == "\n":
                            line_started = False
    except KeyboardInterrupt:
        print("\n\n已停止監控。")
    finally:
        if logf:
            logf.close()


if __name__ == "__main__":
    main()

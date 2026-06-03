"""
probe_mp1.py — 自動偵測 MP1 (COM99) 的序列埠鮑率

由於 MP1 的通訊參數未知，本程式會輪流嘗試常見鮑率，
在每個鮑率下被動聆聽數秒，統計收到的位元組數與「可列印字元比例」，
藉此推測哪個鮑率最可能正確（亂碼少、可讀文字多 = 比較可能對）。

注意：本程式只「讀」不「寫」，不會對裝置送出任何指令。
"""

import argparse
import sys
import time

import serial

# 確保在 Windows 主控台輸出 UTF-8，避免中文變亂碼
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = "COM99"
# 常見鮑率，115200 放第一個：STM32MP1 系列序列主控台預設值
BAUD_CANDIDATES = [115200, 9600, 57600, 38400, 19200, 230400, 460800, 921600]
LISTEN_SECONDS = 3.0   # 每個鮑率聆聽秒數


def printable_ratio(data: bytes) -> float:
    """計算可列印 ASCII（含換行、tab）的比例，作為『是否像文字』的指標。"""
    if not data:
        return 0.0
    good = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return good / len(data)


def preview(data: bytes, limit: int = 120) -> str:
    """把收到的位元組做安全預覽（非可列印字元以 . 取代）。"""
    sample = data[:limit]
    text = "".join(chr(b) if 32 <= b <= 126 else "." for b in sample)
    return text


def probe_one(baud: int, poke: bool = False) -> dict:
    try:
        with serial.Serial(PORT, baudrate=baud, bytesize=8,
                           parity=serial.PARITY_NONE, stopbits=1,
                           timeout=0.2) as ser:
            ser.reset_input_buffer()
            if poke:
                # 送一個換行去「戳」裝置，誘使主控台/登入提示回應
                ser.write(b"\r\n")
                ser.flush()
            buf = bytearray()
            end = time.monotonic() + LISTEN_SECONDS
            while time.monotonic() < end:
                chunk = ser.read(4096)
                if chunk:
                    buf.extend(chunk)
            return {
                "baud": baud,
                "bytes": len(buf),
                "ratio": printable_ratio(bytes(buf)),
                "preview": preview(bytes(buf)),
                "error": None,
            }
    except serial.SerialException as e:
        return {"baud": baud, "bytes": 0, "ratio": 0.0, "preview": "", "error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="探測 MP1 序列埠鮑率")
    ap.add_argument("--poke", action="store_true",
                    help="每個鮑率開始時送一個 Enter 去觸發裝置回應")
    args = ap.parse_args()

    mode = "送 Enter 觸發後聆聽" if args.poke else "被動聆聽，不送指令"
    print(f"探測序列埠 {PORT}（{mode}）")
    print(f"每個鮑率聆聽 {LISTEN_SECONDS} 秒…\n")
    results = []
    for baud in BAUD_CANDIDATES:
        print(f"  嘗試 {baud:>7} baud … ", end="", flush=True)
        r = probe_one(baud, poke=args.poke)
        if r["error"]:
            print(f"開啟失敗：{r['error']}")
            # 埠被佔用或不存在時，繼續試也沒意義
            if "could not open" in r["error"].lower() or "存取被拒" in r["error"]:
                print("    （COM99 可能被其他程式佔用，請先關閉佔用的軟體）")
            results.append(r)
            continue
        print(f"收到 {r['bytes']:>5} bytes，可列印比例 {r['ratio']*100:5.1f}%")
        if r["bytes"]:
            print(f"      預覽: {r['preview']}")
        results.append(r)

    print("\n========== 結果摘要 ==========")
    usable = [r for r in results if r["bytes"] > 0]
    if not usable:
        print("所有鮑率都沒有收到任何資料。可能原因：")
        print("  1) MP1 此刻沒有主動輸出（需要先按重置鍵 / 觸發它送資料）")
        print("  2) COM99 被其他程式佔用（如 PuTTY、STM32CubeIDE 主控台）")
        print("  3) 接線 / 裝置電源問題")
        sys.exit(1)

    # 以可列印比例為主、位元組數為輔來排序，挑最像「正確鮑率」的
    usable.sort(key=lambda r: (r["ratio"], r["bytes"]), reverse=True)
    best = usable[0]
    print(f"最可能的鮑率：{best['baud']} "
          f"（可列印比例 {best['ratio']*100:.1f}%, {best['bytes']} bytes）")
    print(f"預覽: {best['preview']}")
    print(f"\n下一步：python monitor_mp1.py --baud {best['baud']}")


if __name__ == "__main__":
    main()

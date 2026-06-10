#!/bin/sh
# Send an "SC <op>" command (CR-terminated) to the SGX sensor, show the reply.
# Usage:
#   sh /home/root/sc.sh RD          -> sends "SC RD\r"
#   sh /home/root/sc.sh "RD 1"      -> sends "SC RD 1\r"
export PATH=/usr/sbin:/sbin:/usr/bin:/bin
PORT=/dev/ttyUSB0
if [ ! -c "$PORT" ]; then
    echo "no $PORT  -- driver not loaded? run:"
    echo "  insmod -f /home/root/mods/usbserial.ko; insmod -f /home/root/mods/ftdi_sio.ko"
    exit 1
fi
stty -F "$PORT" 115200 cs8 -cstopb -parenb -crtscts clocal -echo raw
: > /tmp/scresp
timeout 3 cat "$PORT" > /tmp/scresp 2>/dev/null &
P=$!
sleep 1
printf 'SC %s\r' "$1" > "$PORT"
wait $P
echo "---- reply ----"
cat -v /tmp/scresp
echo "---------------"

#!/bin/sh
# Probe a request-response serial device on /dev/ttyUSB0.
# Sends a command with several line terminators, captures the reply.
export PATH=/usr/sbin:/sbin:/usr/bin:/bin
PORT=/dev/ttyUSB0
stty -F "$PORT" 115200 cs8 -cstopb -parenb -crtscts clocal -echo raw

probe() {
    CMD="$1"; TNAME="$2"; TERM="$3"
    echo "==================== CMD=[$CMD]  TERM=[$TNAME] ===================="
    : > /tmp/resp
    timeout 6 cat "$PORT" > /tmp/resp 2>/dev/null &
    RPID=$!
    sleep 1
    printf '%s%s' "$CMD" "$TERM" > "$PORT"
    wait $RPID
    N=$(wc -c < /tmp/resp)
    echo "bytes=$N"
    echo "HEX:"; od -An -tx1 /tmp/resp
    echo "TXT:"; cat -v /tmp/resp
    echo
}

CR=$(printf '\r')
LF=$(printf '\n')
CRLF=$(printf '\r\n')

for CMD in "SC RE" "SC IN"; do
    probe "$CMD" "CRLF" "$CRLF"
    probe "$CMD" "CR"   "$CR"
    probe "$CMD" "LF"   "$LF"
    probe "$CMD" "none" ""
done
echo ALLDONE

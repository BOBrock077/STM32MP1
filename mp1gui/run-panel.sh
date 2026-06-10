#!/bin/sh
# Launch mp1gui on the physical DSI panel via Slint's linuxkms backend.
# Like weston-start, run it on a freshly-switched-to VT (openvt -s) so the app
# can become DRM master and present to the panel.
export PATH=/usr/sbin:/sbin:/usr/bin:/bin

# Free the DRM master (Weston / ST demo holds it).
systemctl stop weston
sleep 1

# Clean up any previous run.
systemctl stop mp1gui 2>/dev/null
pkill -x mp1gui 2>/dev/null
sleep 1

# openvt -s : allocate a new VT and switch to it, run the app there.
# Rotation: prepend SLINT_KMS_ROTATION=270 below if the image is sideways.
openvt -s -- sh -c 'SLINT_BACKEND=linuxkms exec /home/root/mp1gui >/tmp/gui.log 2>&1'

sleep 4
echo "=== alive? ==="
if ps w | grep -v grep | grep -q -e '[m]p1gui'; then
    echo "RUNNING:"; ps w | grep -v grep | grep -e '[m]p1gui'
else
    echo "NOT running"
fi
echo "=== /tmp/gui.log ==="
cat /tmp/gui.log
echo "=== end ==="

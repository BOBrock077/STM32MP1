# Extract the armhf binary from the built image and ship it to the MP1 board.
$ErrorActionPreference = "Stop"
$d = (Get-Command docker).Source
$bin = "C:\Stone\AI_try\MP1\mp1gui\mp1gui-arm"

# 1. Pull the binary out of the image via a throwaway container.
& $d rm -f mp1x 2>$null | Out-Null
& $d create --name mp1x mp1gui-build | Out-Null
& $d cp mp1x:/src/target/release/mp1gui $bin
& $d rm mp1x | Out-Null
Write-Host ("binary size: " + (Get-Item $bin).Length + " bytes")

# 2. Copy to the board (uses ~/.ssh/config 'mp1' alias).
scp $bin mp1:/home/root/mp1gui
ssh mp1 'chmod +x /home/root/mp1gui; ls -l /home/root/mp1gui; file /home/root/mp1gui 2>/dev/null'

Write-Host "Done. To run on the board's screen:"
Write-Host "  ssh mp1 'XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-0 /home/root/mp1gui'"

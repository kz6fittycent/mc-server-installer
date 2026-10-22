#!/bin/bash
# Install a built snap (SNAP_FILE) and run a real Minecraft server with it:
# the background service, the bundled Java, the menu, then the server itself,
# plain and with Bedrock players on (Fabric, Geyser, Floodgate). Used by
# "🧪 Snap Builds" on every architecture the snap is built for.
set -euo pipefail

SNAP_NAME=mc-server-installer
C="$SNAP_NAME.ctl"
CONSOLE=/var/snap/$SNAP_NAME/common/server/console.log

field() { python3 -c "import json, sys; print(json.load(sys.stdin).get('$1'))"; }
fail() { echo "::error::$1"; sudo tail -40 "$CONSOLE" 2>/dev/null || true; sudo snap logs "$SNAP_NAME.service" -n 30; exit 1; }
wait_ready() {
  for _ in $(seq 120); do
    [[ "$($C status | field ready)" == True ]] && return 0
    [[ "$($C status | field running)" == True ]] || fail "the server stopped while starting"
    sleep 2
  done
  fail "the server did not finish starting"
}
wait_for_line() {
  for _ in $(seq 120); do sudo grep -q "$1" "$CONSOLE" && return 0; sleep 2; done
  fail "the server never printed: $1"
}
stop_cleanly() {
  how="$($C stop | field how)"
  echo "stopped: $how"
  [[ "$how" == console* ]] || fail "the server did not stop when asked ($how)"
}

echo "== Install ($(uname -m))"
sudo snap install --dangerous "$SNAP_FILE"
# Not connected by itself until the store grants it; Bedrock's NetherNet needs it.
sudo snap connect "$SNAP_NAME:mount-observe"
for _ in $(seq 30); do $C status >/dev/null 2>&1 && break; sleep 2; done
snap services "$SNAP_NAME"

echo "== The bundled Java, and the menu with its library"
snap run --shell "$SNAP_NAME" -c '
  set -e
  java="$(ls -d "$SNAP"/usr/lib/jvm/java-*/bin/java | head -1)"
  "$java" -version 2>&1 | head -2
  PYTHONPATH="$SNAP/lib" "$SNAP/bin/python3" -c "import textual, mcsi.menu; print(\"menu loads with Textual\", textual.__version__)"
'

echo "== A plain server"
$C accept-eula >/dev/null
echo "downloaded Minecraft $($C download | field version)"
[[ "$($C start ram_mb=2048 | field ok)" == True ]] || fail "start was refused"
wait_ready
$C command text="list" | field reply
stop_cleanly

echo "== With Bedrock players"
[[ "$($C settings bedrock=1 | field ok)" == True ]] || fail "turning Bedrock on was refused"
[[ "$($C status | field bedrock_connect)" == False ]] || fail "status says mount-observe is not connected"
$C start ram_mb=2048 >/dev/null
wait_ready
wait_for_line "Run /geyser help"
sudo grep -q "Built-in signaling started" "$CONSOLE" || fail "NetherNet signaling did not start"
python3 - <<'EOF'
# A Bedrock "unconnected ping" (RakNet), as a phone's server list sends it.
import socket, struct, sys, time
magic = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5)
for _ in range(10):
    sock.sendto(b"\x01" + struct.pack(">q", int(time.time() * 1000)) + magic + struct.pack(">q", 2),
                ("127.0.0.1", 19132))
    try:
        print("Bedrock ping answered:", sock.recv(2048)[35:].decode(errors="replace")[:60])
        sys.exit(0)
    except socket.timeout:
        pass
sys.exit("::error::no answer to a Bedrock ping on UDP 19132")
EOF
stop_cleanly
echo "All good on $(uname -m)."

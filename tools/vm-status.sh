set -eu
printf '\n--- Guest console ---\n'
tail -55 /DATA/harbor/vm/serial.log | sed -E 's/(First-time setup code: ).*/\1[redacted]/'
printf '\n--- Guest HTTPS endpoint ---\n'
python3 - <<'PY'
import socket
s=socket.create_connection(('127.0.0.1',18443), timeout=3)
print('Guest forwarded port is reachable.')
s.close()
PY

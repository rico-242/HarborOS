import json
import socket
import time
socket_path = '/DATA/harbor/vm/qmp.sock'
client = socket.socket(socket.AF_UNIX)
client.connect(socket_path)
stream = client.makefile('rwb', buffering=0)
stream.readline()
for command in ('qmp_capabilities', 'quit'):
    stream.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line = stream.readline()
        if not line or 'return' in json.loads(line):
            break
client.close()
time.sleep(1)

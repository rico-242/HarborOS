"""Authenticated, same-origin WebSocket to loopback-only libvirt VNC."""
import base64
import hashlib
import socket
import struct
import threading
import time

def bridge(handler, address, valid):
    key=handler.headers.get('Sec-WebSocket-Key','')
    try:
        if len(base64.b64decode(key,validate=True))!=16:raise ValueError()
    except ValueError:raise handler.app.virtual_machines.error('Invalid console handshake.',400)
    upstream=socket.create_connection(address,timeout=10)
    handler.send_response(101)
    handler.send_header('Upgrade','websocket');handler.send_header('Connection','Upgrade')
    handler.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode())
    handler.end_headers();handler.close_connection=True
    handler.connection.settimeout(30);upstream.settimeout(2)
    stopped=threading.Event();lock=threading.Lock()
    def send(op,payload):
        n=len(payload);header=bytes([0x80|op])+(bytes([n]) if n<126 else b'\x7e'+struct.pack('!H',n) if n<65536 else b'\x7f'+struct.pack('!Q',n))
        with lock:handler.connection.sendall(header+payload)
    def output():
        last_ping=time.monotonic()
        try:
            while not stopped.is_set() and valid():
                if time.monotonic()-last_ping>10:
                    send(9,b'');last_ping=time.monotonic()
                try:data=upstream.recv(65536)
                except socket.timeout:continue
                if not data:break
                send(2,data)
        except (OSError,ValueError):pass
        finally:
            stopped.set()
            try:handler.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
    thread=threading.Thread(target=output,daemon=True);thread.start()
    def read(n):
        result=bytearray()
        while len(result)<n:
            part=handler.rfile.read(n-len(result))
            if not part:raise EOFError()
            result.extend(part)
        return result
    try:
        while not stopped.is_set() and valid():
            a,b=read(2);op=a&15;n=b&127
            if a&0x70 or not b&128:break
            if n==126:n=struct.unpack('!H',read(2))[0]
            elif n==127:n=struct.unpack('!Q',read(8))[0]
            if n>1024*1024 or (op>=8 and (n>125 or not a&128)):break
            mask=read(4);data=read(n);data=bytes(v^mask[i%4] for i,v in enumerate(data))
            if op==8:break
            if op==9:send(10,data)
            elif op in (0,2):upstream.sendall(data)
            elif op!=10:break
    except (OSError,EOFError,ValueError):pass
    finally:
        stopped.set();upstream.close();thread.join(3)

"""Private localhost forwarding to the NAS's VM-only graphical test service."""
import os,socketserver,sys,threading,select
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.local/pylibs'))
import paramiko
client=paramiko.SSHClient();client.load_system_host_keys(str(Path.home()/'.ssh/known_hosts'));client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('192.168.1.97',username='rico',password=os.environ['HARBOR_SSH_PASSWORD'],look_for_keys=False,allow_agent=False)
class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        channel=client.get_transport().open_channel('direct-tcpip',('127.0.0.1',20608),self.client_address)
        try:
            while True:
                readable,_,_=select.select([self.request,channel],[],[],30)
                for source in readable:
                    data=source.recv(65536)
                    if not data:return
                    (channel if source is self.request else self.request).sendall(data)
        finally:channel.close()
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
with Server(('127.0.0.1',20608),Forward) as server:
    print('Private VM viewer ready on localhost:20608',flush=True);server.serve_forever()

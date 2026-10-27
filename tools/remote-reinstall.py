#!/usr/bin/env python3
"""Temporary owner SSH bridge for headless Harbour reinstallation."""
import argparse,getpass,io,json,os,re,socketserver,sys,threading,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.local/pylibs'))
import paramiko
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def client_key(folder):
 folder.mkdir(mode=0o700,parents=True,exist_ok=True);folder.chmod(0o700)
 if os.name=='nt':
  import subprocess
  identity=os.environ.get('USERDOMAIN','')+'\\'+os.environ['USERNAME']
  subprocess.run(['icacls',str(folder),'/inheritance:r','/grant:r',identity+':(OI)(CI)F','SYSTEM:(OI)(CI)F'],check=True,stdout=subprocess.DEVNULL)
 path=folder/'client-key'
 if not path.exists():
  key=Ed25519PrivateKey.generate();path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption()));path.chmod(0o600)
 key=paramiko.Ed25519Key.from_private_key_file(str(path));return key,key.get_name()+' '+key.get_base64()

def existing(host,user,password,known_hosts):
 client=paramiko.SSHClient();client.load_system_host_keys(str(known_hosts));client.set_missing_host_key_policy(paramiko.RejectPolicy());client.connect(host,username=user,password=password,look_for_keys=False,allow_agent=False,timeout=10);return client

def sudo(client,password,action,data=None):
 command="sudo -S -p '' python3 /opt/harbor/remote_recovery.py "+action
 inp,out,err=client.exec_command(command);inp.write(password+'\n')
 if data is not None:inp.write(json.dumps(data)+'\n')
 inp.flush();inp.channel.shutdown_write();raw=out.read().decode();errors=err.read().decode();code=out.channel.recv_exit_status()
 if code:raise RuntimeError(errors+raw)
 return json.loads(raw.strip().splitlines()[-1])

def recovery_connection(host,key,server_key,sock=None):
 parts=server_key.split();assert parts[0]=='ssh-ed25519'
 public=paramiko.Ed25519Key(data=__import__('base64').b64decode(parts[1]))
 client=paramiko.SSHClient();client.get_host_keys().add(host,'ssh-ed25519',public);client.set_missing_host_key_policy(paramiko.RejectPolicy());client.connect(host,username='root',pkey=key,look_for_keys=False,allow_agent=False,timeout=5,sock=sock);return client

def agent(client,command,data=None,stream=False):
 inp,out,err=client.exec_command(command)
 if data is not None:inp.write(json.dumps(data)+'\n')
 inp.flush();inp.channel.shutdown_write();lines=[]
 for line in out:
  lines.append(line)
  if stream:print(line.rstrip(),flush=True)
 errors=err.read().decode();code=out.channel.recv_exit_status()
 if not lines and not errors:raise EOFError('SSH closed before the command returned a result.')
 if code:raise RuntimeError(errors+''.join(lines))
 return json.loads(lines[-1])

def wait_connection(host,key,record,timeout=240,phase=None):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  try:
   client=recovery_connection(host,key,record['server_key'])
   if phase and agent(client,'status')['phase']!=phase:client.close();time.sleep(15);continue
   return client
  except (paramiko.BadHostKeyException,paramiko.AuthenticationException):raise RuntimeError('The NAS returned with another OS identity or rejected the recovery key. No install command was sent.') from None
  except (EOFError,OSError,paramiko.SSHException):
   if 'client' in locals():client.close()
   time.sleep(15)
 raise RuntimeError('Recovery SSH did not become available. No install command was sent.')

def forward_setup(client,port=17080,duration=3600):
 transport=client.get_transport()
 class Handler(socketserver.BaseRequestHandler):
  def handle(self):
   import select
   channel=transport.open_channel('direct-tcpip',('127.0.0.1',17080),self.request.getpeername())
   try:
    while True:
     ready,_,_=select.select([self.request,channel],[],[],30)
     if self.request in ready:
      data=self.request.recv(65536)
      if not data:break
      channel.sendall(data)
     if channel in ready:
      data=channel.recv(65536)
      if not data:break
      self.request.sendall(data)
   finally:channel.close()
 class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
 server=Server(('127.0.0.1',port),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 print('Remote graphical owner setup: http://127.0.0.1:'+str(port)+'/',flush=True)
 try:
  deadline=time.monotonic()+duration
  while time.monotonic()<deadline and transport.is_active():time.sleep(1)
 finally:server.shutdown();server.server_close()

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['stage','boot','status','install','setup']);p.add_argument('--host',required=True);p.add_argument('--user');p.add_argument('--confirmation');p.add_argument('--pool',choices=['hybrid1']);p.add_argument('--pool-confirmation');p.add_argument('--known-hosts',type=Path,default=Path.home()/'.ssh/known_hosts');p.add_argument('--state',type=Path,default=ROOT/'.local/remote-reinstall');args=p.parse_args()
 if not re.fullmatch('[A-Za-z0-9.-]+',args.host):raise ValueError('Use an IP address or DNS host name.')
 folder=args.state/args.host;key,pub=client_key(folder);record_path=folder/'session.json'
 if args.action=='stage':
  if not args.user:raise ValueError('Supply the existing SSH administrator username.')
  password=os.environ.get('HARBOR_SSH_PASSWORD') or getpass.getpass('Existing SSH password: ')
  with existing(args.host,args.user,password,args.known_hosts) as old:record=sudo(old,password,'stage',{'client_key':pub,'pool':args.pool,'server_ip':old.get_transport().sock.getpeername()[0]})
  record_path.write_text(json.dumps(record,indent=2));record_path.chmod(0o600);print(json.dumps(record['plan'],indent=2));return
 record=json.loads(record_path.read_text())
 if args.action=='boot':
  if args.confirmation!='BOOT REMOTE RECOVERY':raise ValueError('Type BOOT REMOTE RECOVERY using --confirmation; this restarts the NAS but does not erase it.')
  password=os.environ.get('HARBOR_SSH_PASSWORD') or getpass.getpass('Existing SSH password: ')
  with existing(args.host,args.user,password,args.known_hosts) as old:print(sudo(old,password,'arm'))
  time.sleep(8)
  with wait_connection(args.host,key,record,phase='installer') as client:print(json.dumps(agent(client,'status'),indent=2))
 elif args.action=='status':
  with recovery_connection(args.host,key,record['server_key']) as client:print(json.dumps(agent(client,'status'),indent=2))
 elif args.action=='install':
  expected='ERASE '+record['plan']['disk']['serial']
  pool=record['plan'].get('pool')
  if pool and args.pool_confirmation!='ERASE POOL '+pool['name']:raise ValueError('Confirm the planned data-pool erase with --pool-confirmation '+repr('ERASE POOL '+pool['name']))
  if args.confirmation!=expected:raise ValueError('Confirm the planned system SSD with --confirmation '+repr(expected))
  with recovery_connection(args.host,key,record['server_key']) as client:
   print(agent(client,'install',{'confirmation':expected},stream=True));print(agent(client,'reboot'))
  time.sleep(10)
  with wait_connection(args.host,key,record,phase='setup') as client:
   if pool:print(agent(client,'create-pool',{'confirmation':args.pool_confirmation},stream=True))
   print(json.dumps(agent(client,'status'),indent=2))
 elif args.action=='setup':
  with recovery_connection(args.host,key,record['server_key']) as client:forward_setup(client)
if __name__=='__main__':main()

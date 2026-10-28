#!/usr/bin/env python3
"""Loopback-only graphical installer for the Harbor live medium."""
import argparse
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time

WEB=Path('/opt/harbor/web')


class Installer:
    def __init__(self,demo=False):
        self.demo=demo;self.sessions={};self.plans={};self.lock=threading.RLock()
        self.status={'phase':'ready','stage':'Choose a disk','log':[],'version':'0.14.0','demo':demo}
        self.logs=deque(maxlen=40)
        if not demo:
            if 'boot=live' not in Path('/proc/cmdline').read_text().split():raise RuntimeError('The installer runs only from the live medium.')
            loader=importlib.machinery.SourceFileLoader('harbor_install','/usr/local/sbin/harbor-install')
            spec=importlib.util.spec_from_loader(loader.name,loader);self.module=importlib.util.module_from_spec(spec);loader.exec_module(self.module)

    def disks(self):
        if self.demo:return [{'id':'demo-disk','serial':'DEMO-ONLY','model':'Preview disk (no device will be changed)','size':256*1024**3}]
        return self.module.inventory()

    def start(self,plan):
        with self.lock:
            if self.status['phase']=='running':raise ValueError('An installation is already running.')
            if self.demo:raise ValueError('This is a design preview. Installation requires the booted live ISO.')
            current=next((d for d in self.disks() if d['id']==plan['disk']['id']),None)
            if not current or self.module.fingerprint(current)!=plan['fingerprint']:raise ValueError('The disk identity changed. Review the destination again.')
            self.status.update(phase='running',stage='Preparing the destination',log=[])
        def execute():
            confirmation='ERASE '+str(current.get('serial') or Path(current['id']).name)
            process=subprocess.Popen(['/usr/local/sbin/harbor-install','--disk',current['id']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,env=dict(os.environ,PYTHONUNBUFFERED='1'))
            process.stdin.write(confirmation+'\n');process.stdin.close()
            for line in process.stdout:
                text=line.strip()
                if not text:continue
                self.logs.append(text[-500:]);self.status['log']=list(self.logs)
                if 'Creating filesystem' in text or 'mke2fs' in text or 'mkfs' in text:self.status['stage']='Formatting the system disk'
                if 'Parallel unsquashfs' in text or 'inodes' in text:self.status['stage']='Copying Harbour OS'
                if 'Installing for' in text:self.status['stage']='Installing the bootloader'
            result=process.wait()
            self.status.update(phase='complete' if result==0 else 'failed',stage='Installation complete' if result==0 else 'Installation stopped')
        def work():
            try:execute()
            except Exception as error:
                self.logs.append('Installation stopped: '+str(error))
                self.status.update(phase='failed',stage='Installation stopped',log=list(self.logs))
        threading.Thread(target=work,daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,value,status=200,cookie=None):
        encoded=json.dumps(value).encode();self.send_response(status);self.headers_common()
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)))
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(encoded)
    def headers_common(self):
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    def check_host(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.client_address[0]!='127.0.0.1' or self.headers.get('Host') not in allowed:raise ValueError('The installer is available only on this computer’s graphical console.')
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers['Host']:raise ValueError('Cross-origin requests are not allowed.')
    def session(self):
        cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
        token=cookies['harbor-installer'].value if 'harbor-installer' in cookies else ''
        session=self.server.app.sessions.get(token)
        if not session or session['expires']<time.monotonic() or self.headers.get('X-Harbor-CSRF')!=session['csrf']:raise ValueError('Refresh the installer and try again.')
        return token
    def do_GET(self):
        try:
            self.check_host();route=self.path.split('?')[0];app=self.server.app
            if route=='/api/session':
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                app.sessions={k:v for k,v in app.sessions.items() if v['expires']>time.monotonic()}
                if len(app.sessions)>=16:app.sessions.pop(next(iter(app.sessions)))
                app.sessions[token]={'csrf':csrf,'expires':time.monotonic()+3600}
                return self.reply({'csrf':csrf,'demo':app.demo},cookie=f'harbor-installer={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
            if route=='/api/disks':return self.reply(app.disks())
            if route=='/api/status':return self.reply(app.status)
            files={'/':'install.html','/install.js':'install.js','/style.css':'style.css','/desktop.css':'desktop.css','/favicon.svg':'favicon.svg','/theme.js':'theme.js','/experience.css':'experience.css','/wallpaper.svg':'wallpaper.svg'}
            if route not in files:return self.reply({'error':'Not found'},404)
            path=WEB/files[route];content=path.read_bytes();self.send_response(200);self.headers_common()
            self.send_header('Content-Type',{'html':'text/html','js':'text/javascript','css':'text/css','svg':'image/svg+xml'}[path.suffix[1:]])
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
        except ValueError as error:self.reply({'error':str(error)},403)
    def do_POST(self):
        try:
            self.check_host();token=self.session()
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192 or self.headers.get_content_type()!='application/json':raise ValueError('Invalid installer request.')
            data=json.loads(self.rfile.read(length));app=self.server.app
            if not isinstance(data,dict):raise ValueError('Invalid installer request.')
            if self.path=='/api/plan':
                disk=next((d for d in app.disks() if d['id']==data.get('disk')),None)
                if not disk:raise ValueError('That destination disk is unavailable.')
                ident=secrets.token_urlsafe(24)
                app.plans[token]={'id':ident,'disk':disk,'expires':time.monotonic()+300,'fingerprint':app.module.fingerprint(disk) if not app.demo else 'demo'}
                return self.reply({'id':ident,'disk':disk})
            if self.path=='/api/install':
                plan=app.plans.get(token)
                if not plan or plan['id']!=data.get('plan') or plan['expires']<time.monotonic() or data.get('erase') is not True:raise ValueError('Review and confirm the destination disk before installing.')
                app.start(plan);app.plans.pop(token,None);return self.reply({'ok':True},202)
            if self.path=='/api/poweroff':
                if app.demo or app.status['phase']!='complete':raise ValueError('Complete installation before shutting down.')
                self.reply({'ok':True});subprocess.Popen(['systemctl','poweroff']);return
            self.reply({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as error:self.reply({'error':str(error)},400)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');parser.add_argument('--port',type=int,default=17081);args=parser.parse_args()
    if args.demo:WEB=Path(__file__).resolve().parents[1]/'harbor/web'
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.app=Installer(args.demo);server.serve_forever()


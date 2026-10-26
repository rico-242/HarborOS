import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('harbor_server', Path(__file__).parents[1] / 'harbor' / 'server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HardwareMetricsTests(unittest.TestCase):
    def test_linux_sensor_and_network_deltas(self):
        test_root = Path(__file__).resolve().parents[1] / '.local' / 'tests'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            root = Path(temporary)
            sensor = root / 'sys/class/hwmon/hwmon0'
            sensor.mkdir(parents=True)
            (sensor / 'name').write_text('coretemp\n')
            (sensor / 'temp1_input').write_text('41500\n')
            (root / 'proc/net').mkdir(parents=True)
            (root / 'proc/net/route').write_text('Iface Destination Gateway\neth0 00000000 0101A8C0\n')
            counters = root / 'proc/net/dev'
            counters.write_text('header\nheader\neth0: 1000 0 0 0 0 0 0 0 2000 0 0 0 0 0 0 0\n')
            app = object.__new__(module.Harbor)
            app.lock = threading.RLock()
            app.previous_network = None
            with patch.object(module, 'Path', side_effect=lambda p: root / p.lstrip('/')), patch.object(module.time, 'monotonic', side_effect=[10, 12, 14]):
                first = app.hardware_metrics()
                self.assertEqual(first['temperature'], 41.5)
                self.assertIsNone(first['network']['receive'])
                counters.write_text('header\nheader\neth0: 3048 0 0 0 0 0 0 0 3024 0 0 0 0 0 0 0\n')
                self.assertEqual(app.hardware_metrics()['network'], {'interface': 'eth0', 'receive': 1024, 'transmit': 512})
                counters.write_text('header\nheader\neth0: 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n')
                self.assertEqual(app.hardware_metrics()['network']['receive'], 0)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / '.local' / 'tests'
        test_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=test_root)
        assert Path(self.directory.name).resolve().is_relative_to(test_root.resolve())
        root = Path(self.directory.name)
        self.app = module.Harbor(root/'state', root/'storage', root/'apps', demo=True)
        self.server = module.make_server(self.app, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.pool.shutdown()
        self.directory.cleanup()

    def request(self, path, data=None, method=None, headers=None, raw=False):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        request_headers = {'Cookie': self.cookie, 'X-Harbor-CSRF': self.csrf}
        if data is not None and not raw:
            data = json.dumps(data)
            request_headers['Content-Type'] = 'application/json'
        request_headers.update(headers or {})
        conn.request(method or ('POST' if data is not None else 'GET'), path, data, request_headers)
        response = conn.getresponse()
        body = response.read()
        status = response.status
        response_headers = dict(response.getheaders())
        conn.close()
        try:
            result = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            result = body
        return status, result, response_headers

    def setup_admin(self):
        status,session,headers=self.request('/api/setup-session')
        self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';')[0]
        self.csrf=session['csrf']
        status, result, headers = self.request('/api/setup', {'username': 'rico', 'password': 'development-test-password'})
        self.assertEqual(status, 200, result)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = result['csrf']
        return result

    def test_system_ssd_namespace_without_a_data_pool(self):
        self.setup_admin()
        self.app.storage_info=lambda:{'mounted':False}
        self.assertEqual(self.request('/api/system-files')[0],200)
        status,result,_=self.request('/api/upload?volume=system&path=Files&name=ssd.txt',b'local SSD data',raw=True)
        self.assertEqual(status,201,result)
        self.assertEqual(self.request('/api/download?volume=system&path=Files/ssd.txt')[1],b'local SSD data')
        self.assertFalse((self.app.storage/'shares/Files/ssd.txt').exists())
        self.assertEqual(self.request('/api/files?volume=system&path=../../etc')[0],403)
        self.assertEqual(self.request('/api/files?path=Files')[0],403)
        self.assertEqual(self.request('/api/summary?volume=system')[0],400)

    def test_members_cannot_access_system_ssd_namespace(self):
        self.setup_admin();token='f'*64;self.app.sessions[token]={'username':'member','role':'member','csrf':'member-csrf','expires':time.monotonic()+600}
        self.cookie='harbor='+token;self.csrf='member-csrf'
        self.assertEqual(self.request('/api/system-files')[0],403)
        self.assertEqual(self.request('/api/files?volume=system&path=Files')[0],403)
        self.assertEqual(self.request('/api/upload?volume=system&path=Files&name=blocked.txt',b'blocked',raw=True)[0],403)

    def test_system_ssd_reserves_os_space(self):
        self.setup_admin();self.app.system_files.prepare()
        original=self.app.system_files.info
        self.app.system_files.info=lambda:dict(original(),available=1)
        status,result,_=self.request('/api/upload?volume=system&path=Files&name=full.txt',b'too large',raw=True)
        self.assertEqual(status,409,result)
        self.assertFalse((self.app.system_files.storage/'shares/Files/full.txt').exists())

    def test_setup_auth_and_logout(self):
        self.assertEqual(self.request('/api/summary')[0], 401)
        self.setup_admin()
        self.assertFalse(self.app.setup_path.exists())
        self.assertEqual(self.request('/api/summary')[0], 200)
        self.assertEqual(self.request('/api/setup', {'code':'anything'})[0], 409)
        self.assertIn('HttpOnly', self.request('/api/login', {'username':'rico','password':'development-test-password'})[2]['Set-Cookie'])
        self.assertEqual(self.request('/api/logout', {})[0], 200)
        self.assertEqual(self.request('/api/summary')[0], 401)

    def test_csrf_origin_and_content_type(self):
        self.setup_admin()
        self.assertEqual(self.request('/api/shares', {'name':'Private'}, headers={'X-Harbor-CSRF':''})[0], 403)
        self.assertEqual(self.request('/api/shares', {'name':'Private'}, headers={'Origin':'https://evil.invalid'})[0], 403)
        self.assertEqual(self.request('/api/login', '{}', raw=True, headers={'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/login', '[]', raw=True, headers={'Content-Type':'application/json'})[0], 400)

    def test_share_upload_and_path_confinement(self):
        self.setup_admin()
        self.assertEqual(self.request('/api/shares', {'name':'Documents'})[0], 201)
        self.assertEqual(self.request('/api/shares', {'name':'documents'})[0], 409)
        self.assertEqual(self.request('/api/shares', {'name':'../escape'})[0], 400)
        self.assertEqual(self.request('/api/files?path=../../')[0], 403)
        status, result, _ = self.request('/api/upload?path=Documents&name=hello.txt', b'hello harbor', raw=True)
        self.assertEqual(status, 201, result)
        self.assertEqual(self.request('/api/download?path=Documents/hello.txt')[1], b'hello harbor')
        self.assertEqual(self.request('/api/upload?path=Documents&name=hello.txt', b'overwrite', raw=True)[0], 409)
        self.assertEqual(self.request('/api/upload?path=Documents&name=../bad', b'bad', raw=True)[0], 400)
        self.assertEqual(self.request('/api/upload?path=&name=bad', b'bad', raw=True)[0], 400)
        self.assertEqual(self.request('/api/folders', {'path':'Documents', 'name':'Photos'})[0], 201)
        self.assertEqual(self.request('/api/folders', {'path':'Documents', 'name':'Photos'})[0], 409)

    def test_auth_expiry_and_login_throttling(self):
        self.setup_admin()
        token = self.cookie.split('=',1)[1]
        self.app.sessions[token]['expires'] = time.monotonic() - 1
        self.assertEqual(self.request('/api/summary')[0], 401)
        for _ in range(8):
            self.assertEqual(self.request('/api/login', {'username':'rico','password':'wrong'})[0], 401)
        self.assertEqual(self.request('/api/login', {'username':'rico','password':'development-test-password'})[0], 429)

    def test_demo_does_not_claim_real_operations(self):
        self.setup_admin()
        self.assertEqual(self.request('/api/app-action', {'id':'jellyfin','action':'install'})[0], 409)
        self.assertEqual(self.request('/api/app-action', {'id':'bad;reboot','action':'install'})[0], 400)
        status, job, _ = self.request('/api/snapshots', {'share':'Welcome'})
        self.assertEqual(status, 202)
        for _ in range(50):
            if self.app.jobs[job['id']]['state'] == 'failed':
                break
            time.sleep(.02)
        self.assertEqual(self.app.jobs[job['id']]['state'], 'failed')

    def test_static_content_headers(self):
        for path in ('/', '/app.js', '/style.css', '/favicon.svg','/process.js','/widgets.js','/refinements.css','/theme.js','/experience.js','/experience.css','/wallpaper.svg','/catalog/icons/featured-blinko.png'):
            status, _, headers = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.request('/../../README.md')[0], 404)

    def test_persistence(self):
        self.setup_admin()
        self.request('/api/shares', {'name':'Persistent'})
        app = module.Harbor(self.app.state, self.app.storage, self.app.apps, demo=True)
        try:
            self.assertEqual(app.config['shares'][0]['name'],'Persistent')
            self.assertTrue(module.verify_password(app.admin,'development-test-password'))
            self.assertFalse(module.verify_password(app.admin,'wrong'))
        finally:
            app.pool.shutdown()

    def test_refuses_network_without_tls(self):
        with self.assertRaises(RuntimeError):
            module.make_server(self.app, host='0.0.0.0', port=0)


if __name__ == '__main__':
    unittest.main()

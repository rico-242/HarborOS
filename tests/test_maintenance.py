import base64,hashlib,io,json,sys,tarfile,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'.local/pylibs'))
import test_server as fixtures
from networking import validate,configuration
from release_bundle import inspect_bundle
from releases import github_open
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

class BondPlanTests(unittest.TestCase):
    def setUp(self):self.interfaces=[{'name':'eth'+str(i),'eligible':True,'permanent_mac':'02:00:00:00:00:0'+str(i)} for i in range(2)]
    def data(self):return {'mode':'active-backup','interfaces':['eth0','eth1'],'primary':'eth0','method':'dhcp'}
    def test_two_physical_adapters_and_explicit_lacp_switch_ack(self):
        data=self.data();self.assertEqual(validate(data,self.interfaces)['primary'],'eth0')
        data['interfaces']=['eth0']
        with self.assertRaises(ValueError):validate(data,self.interfaces)
        data=self.data();data['mode']='802.3ad'
        with self.assertRaises(ValueError):validate(data,self.interfaces)
        data['switch_ready']=True;self.assertEqual(validate(data,self.interfaces)['mode'],'802.3ad')
        self.interfaces[1]['eligible']=False
        with self.assertRaises(ValueError):validate(self.data(),self.interfaces)
    def test_generated_port_files_have_no_addresses_and_bond_gets_dhcp(self):
        files=configuration(validate(self.data(),self.interfaces))
        ports=[value for name,value in files.items() if 'port-' in name]
        self.assertEqual(len(ports),2)
        for text in ports:self.assertIn('DHCP=no',text);self.assertIn('Bond=bond0',text);self.assertNotIn('\nAddress=',text)
        self.assertIn('DHCP=yes',files['05-harbour-bond.network'])
    def test_invalid_static_address_and_duplicate_mac_are_rejected(self):
        data=self.data();data.update(method='static',address='192.168.1.10/24',gateway='10.0.0.1',dns=['1.1.1.1'])
        with self.assertRaises(ValueError):validate(data,self.interfaces)
        self.interfaces[1]['permanent_mac']=self.interfaces[0]['permanent_mac']
        with self.assertRaises(ValueError):validate(self.data(),self.interfaces)
    def test_dns_configuration_injection_and_mismatched_lacp_speeds_are_rejected(self):
        data=self.data();data.update(method='static',address='192.168.1.10/24',gateway='192.168.1.1',dns=['fe80::1%bond0\nDNS=evil'])
        with self.assertRaises(ValueError):validate(data,self.interfaces)
        data=self.data();data.update(mode='802.3ad',switch_ready=True);self.interfaces[0]['speed_mbps']=1000;self.interfaces[1]['speed_mbps']=2500
        with self.assertRaises(ValueError):validate(data,self.interfaces)

class SignedBundleTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).parents[1]/'.local/tests';root.mkdir(parents=True,exist_ok=True);self.directory=tempfile.TemporaryDirectory(dir=root);self.root=Path(self.directory.name);self.key=Ed25519PrivateKey.generate();self.public=self.root/'public.pem';self.public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    def tearDown(self):self.directory.cleanup()
    def bundle(self,extra=None,tamper=False):
        files={'app/server.py':b"VERSION = '0.4.0'\n",'app/web/index.html':b'<html>Harbour</html>'}
        if extra:files.update(extra)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            for name,data in files.items():
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
        payload=stream.getvalue();manifest={'format':1,'product':'harbour','version':'0.4.0','minimum_version':'0.3.1','architecture':'amd64','base':'debian13','payload_sha256':hashlib.sha256(payload).hexdigest(),'files':{name:{'sha256':hashlib.sha256(data).hexdigest(),'mode':0o644} for name,data in files.items()}}
        raw=json.dumps(manifest).encode();signature=self.key.sign(raw)
        if tamper:raw=raw.replace(b'0.4.0',b'9.9.9')
        path=self.root/'test.harbour-update'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('manifest.json',raw);archive.writestr('manifest.sig',signature);archive.writestr('payload.tar.gz',payload)
        return path
    def test_signed_bundle_and_downgrade_protection(self):
        path=self.bundle();self.assertEqual(inspect_bundle(path,self.public,'0.3.1')[0]['version'],'0.4.0')
        with self.assertRaisesRegex(ValueError,'newer'):inspect_bundle(path,self.public,'0.4.0')
    def test_tampered_manifest_and_wrong_trust_key_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Signature'):inspect_bundle(self.bundle(tamper=True),self.public,'0.3.1')
        wrong=self.root/'wrong.pem';wrong.write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaisesRegex(ValueError,'Signature'):inspect_bundle(self.bundle(),wrong,'0.3.1')
    def test_signed_traversal_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'path'):inspect_bundle(self.bundle({'app/../../etc/passwd':b'bad'}),self.public,'0.3.1')
    def test_non_github_download_urls_are_rejected_before_network_access(self):
        for url in ('http://github.com/a/b','https://127.0.0.1/','https://github.com@evil.example/a'):
            with self.assertRaises(ValueError):github_open(url)

class MaintenanceAuthorizationTests(unittest.TestCase):
    setUp=fixtures.ServiceTests.setUp
    tearDown=fixtures.ServiceTests.tearDown
    request=fixtures.ServiceTests.request
    setup_admin=fixtures.ServiceTests.setup_admin
    def test_member_cannot_access_network_or_release_controls(self):
        self.setup_admin();self.request('/api/members',{'username':'member','password':'member-test-password'})
        status,value,headers=self.request('/api/login',{'username':'member','password':'member-test-password'});self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=value['csrf']
        for path in ('/api/network','/api/os-updates'):self.assertEqual(self.request(path)[0],403)
        for path in ('/api/network-plan','/api/network-action','/api/os-updates/action'):self.assertEqual(self.request(path,{})[0],403)
        self.assertEqual(self.request('/api/os-updates/upload',b'bad',raw=True)[0],403)
    def test_network_revalidates_adapter_identity_before_spawning_worker(self):
        self.setup_admin();self.app.demo=False;network=self.app.networking
        interfaces=[{'name':'eth'+str(i),'eligible':True,'permanent_mac':'02:00:00:00:00:0'+str(i)} for i in range(2)];network.inventory=lambda:interfaces
        calls=[]
        def run(*args,**kwargs):calls.append(args);return type('R',(),{'returncode':0,'stdout':''})()
        network.run=run
        plan=network.plan({'mode':'active-backup','interfaces':['eth0','eth1'],'primary':'eth0','method':'dhcp'})
        interfaces[1]['permanent_mac']='02:00:00:00:11:22'
        with self.assertRaisesRegex(Exception,'identities changed'):network.action({'action':'apply','token':plan['token'],'confirmation':'APPLY'})
        self.assertFalse(any(args[0]=='systemd-run' for args in calls))

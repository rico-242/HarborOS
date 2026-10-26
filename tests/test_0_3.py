import test_server as fixtures
import unittest
import json
import time
import io
import zipfile


class NewFeatureTests(unittest.TestCase):
    setUp=fixtures.ServiceTests.setUp
    tearDown=fixtures.ServiceTests.tearDown
    request=fixtures.ServiceTests.request
    setup_admin=fixtures.ServiceTests.setup_admin
    def test_archive_roundtrip_and_symlink_confinement(self):
        self.setup_admin();self.request('/api/shares',{'name':'Files'})
        self.request('/api/upload?path=Files&name=hello.txt',b'archive content',raw=True)
        status,encoded,_=self.request('/api/archive?path=Files')
        self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(encoded)) as archive:
            self.assertEqual(archive.read('Files/hello.txt'),b'archive content')
        self.assertEqual(self.request('/api/archive?path=../../etc')[0],403)
        self.assertEqual(self.request('/api/system-action',{'action':'reboot','confirmation':'anything'})[0],409)

    def test_setup_requires_local_session_and_rejects_rebinding(self):
        self.assertEqual(self.request('/api/setup',{'username':'rico','password':'development-test-password'})[0],403)
        self.assertEqual(self.request('/api/setup-session',headers={'Host':'evil.example'})[0],403)
        self.server.local_console=False
        self.assertEqual(self.request('/api/setup-session')[0],403)
        self.server.local_console=True
        self.setup_admin()
        self.assertFalse(self.app.setup_path.exists())

    def test_member_default_deny_read_only_and_owner_boundary(self):
        self.setup_admin();self.request('/api/shares',{'name':'Private'});self.request('/api/shares',{'name':'Shared'})
        self.assertEqual(self.request('/api/members',{'username':'guest','password':'member-test-password'})[0],201)
        owner_cookie,owner_csrf=self.cookie,self.csrf
        status,user,headers=self.request('/api/login',{'username':'guest','password':'member-test-password'})
        self.assertEqual(status,200);self.assertEqual(user['role'],'member')
        member_cookie=headers['Set-Cookie'].split(';')[0];member_csrf=user['csrf']
        self.cookie,self.csrf=member_cookie,member_csrf
        self.assertEqual(self.request('/api/files')[1]['entries'],[])
        self.assertEqual(self.request('/api/files?path=./')[1]['entries'],[])
        self.assertEqual(self.request('/api/files?path=Private')[0],403)
        self.assertEqual(self.request('/api/members')[0],403)
        self.assertEqual(self.request('/api/app-action',{'id':'syncthing','action':'install'})[0],403)
        self.assertEqual(self.request('/api/storage/create',{})[0],403)
        self.cookie,self.csrf=owner_cookie,owner_csrf
        self.assertEqual(self.request('/api/share-access',{'share':'Shared','access':{'guest':'read'}})[0],200)
        self.cookie,self.csrf=member_cookie,member_csrf
        self.assertEqual([e['name'] for e in self.request('/api/files')[1]['entries']],['Shared'])
        self.assertEqual(self.request('/api/files?path=Shared')[0],200)
        self.assertEqual(self.request('/api/upload?path=Shared&name=no.txt',b'no',raw=True)[0],403)
        self.cookie,self.csrf=owner_cookie,owner_csrf
        self.assertEqual(self.request('/api/share-access',{'share':'Shared','access':{'guest':'write'}})[0],200)
        self.cookie,self.csrf=member_cookie,member_csrf
        self.assertEqual(self.request('/api/upload?path=Shared&name=yes.txt',b'yes',raw=True)[0],201)
        self.cookie,self.csrf=owner_cookie,owner_csrf
        self.assertEqual(self.request('/api/member-state',{'username':'guest','enabled':False})[0],200)
        self.cookie,self.csrf=member_cookie,member_csrf
        self.assertEqual(self.request('/api/files')[0],401)

    def test_file_recycle_restore_and_no_overwrite(self):
        self.setup_admin();self.request('/api/shares',{'name':'Files'})
        self.request('/api/upload?path=Files&name=one.txt',b'original',raw=True)
        self.request('/api/upload?path=Files&name=two.txt',b'existing',raw=True)
        def action(data):
            status,job,_=self.request('/api/file-action',data);self.assertEqual(status,202)
            for _ in range(100):
                if self.app.jobs[job['id']]['state'] in ('completed','failed'):break
                time.sleep(.01)
            return self.app.jobs[job['id']]
        self.assertEqual(action({'operation':'rename','path':'Files/one.txt','name':'two.txt'})['state'],'failed')
        self.assertEqual(self.request('/api/download?path=Files/two.txt')[1],b'existing')
        self.assertEqual(action({'operation':'trash','path':'Files/one.txt'})['state'],'completed')
        items=self.request('/api/trash')[1];self.assertEqual(len(items),1)
        self.assertEqual(self.request('/api/trash-restore',{'id':items[0]['id']})[0],200)
        self.assertEqual(self.request('/api/download?path=Files/one.txt')[1],b'original')
        self.assertEqual(self.request('/api/file-action',{'operation':'trash','path':'../../x'})[0],403)



import base64,copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'harbor'),str(root/'.local/pylibs')]
from recovery import canonical,verify_manifest,grub_configuration,Recovery
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
class Error(Exception):
 def __init__(self,message,status=400):super().__init__(message)
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  (root/'.local/tests').mkdir(parents=True,exist_ok=True)
  tmp=tempfile.TemporaryDirectory(dir=root/'.local/tests');self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
  self.key=Ed25519PrivateKey.generate();self.public=self.folder/'public.pem';self.public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
  self.manifest=dict(product='harbour-recovery',architecture='amd64',version='0.8.0',size=1024**3,sha256='a'*64,url='https://github.com/rico-242/HarborOS/releases/download/v0.8.0/harbour-0.8.0-amd64.iso')
 def envelope(self):return dict(manifest=copy.deepcopy(self.manifest),signature=base64.b64encode(self.key.sign(canonical(self.manifest))).decode())
 def test_signed_manifest_verifies(self):
  with patch('recovery.subprocess.run',side_effect=FileNotFoundError):self.assertEqual(verify_manifest(self.envelope(),self.public),self.manifest)
 def test_changed_checksum_rejected(self):
  value=self.envelope();value['manifest']['sha256']='b'*64
  with patch('recovery.subprocess.run',side_effect=FileNotFoundError),self.assertRaisesRegex(ValueError,'trusted'):verify_manifest(value,self.public)
 def test_arbitrary_download_host_rejected_even_when_signed(self):
  self.manifest['url']='https://evil.invalid/installer.iso'
  with self.assertRaisesRegex(ValueError,'URL'):verify_manifest(self.envelope(),self.public)
 def test_oversize_image_rejected(self):
  self.manifest['size']=8*1024**3
  with self.assertRaisesRegex(ValueError,'size'):verify_manifest(self.envelope(),self.public)
 def test_one_time_boot_retains_normal_entry_and_is_idempotent(self):
  uuid='00000000-0000-0000-0000-000000000001'
  original='set timeout=5\nset default=0\nmenuentry Harbour {\n linux /boot/harbor-vmlinuz root=UUID='+uuid+' rw\n initrd /boot/harbor-initrd\n}\n'
  once=grub_configuration(original,uuid);twice=grub_configuration(once,uuid)
  self.assertEqual(once,twice);self.assertIn('save_env next_entry',once);self.assertIn('else\n  set default=0',once)
  self.assertIn('toram findiso=',once);self.assertEqual(once.count('--id harbour-recovery'),1);self.assertIn('root=UUID='+uuid,once)
 def test_other_bootloader_rejected(self):
  with self.assertRaisesRegex(ValueError,'verified'):grub_configuration('menuentry something {}','00000000-0000-0000-0000-000000000001')
 def test_reboot_requires_exact_confirmation_and_local_screen(self):
  run=Mock();app=SimpleNamespace(state=self.folder,demo=True);recovery=Recovery(app,run,Error,'0.8.0');recovery.supported=Mock(return_value={})
  for value in ({'confirmation':'BOOT RECOVERY','local_screen':False},{'confirmation':'yes','local_screen':True}):
   with self.assertRaisesRegex(Error,'Confirm'):recovery.boot(value)
  run.assert_not_called()
 def test_recovery_installer_refuses_disk_writes_without_ram_source(self):
  import importlib.machinery,importlib.util
  loader=importlib.machinery.SourceFileLoader('guarded_installer',str(root/'os/harbor-install.py'));spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module)
  command=Mock();command.read_text.return_value='boot=live harbour.recovery=1'
  run=Mock(return_value='ext4')
  with patch.object(module,'Path',side_effect=lambda path:command if path=='/proc/cmdline' else Path(path)),patch.object(module,'run',run):
   with self.assertRaisesRegex(RuntimeError,'RAM'):module.install({})
  self.assertEqual(run.call_count,1);self.assertEqual(run.call_args.args[0],'findmnt')

 def test_legacy_boot_retains_zima_and_normal_harbour_policy(self):
  uuid='00000000-0000-0000-0000-000000000001'
  original='set timeout=5\nload_env\nset default=1\nset harbor_default=1\nset harbor_once=0\nsave_env harbor_once\nmenuentry Harbour --id harbor {\n linux /harbor/rootfs/boot/harbor-vmlinuz root=UUID='+uuid+' rw harbor.subdir=harbor/rootfs\n}\nmenuentry Zima --id zima {}\n'
  generated=grub_configuration(original,uuid,'/harbor/rootfs',True)
  self.assertTrue(generated.startswith(original.split('menuentry ')[0]))
  self.assertIn('set harbor_default=1',generated);self.assertIn('menuentry Zima --id zima {}',generated)
  self.assertIn('findiso=/harbor/rootfs/boot/harbour-recovery/recovery.iso',generated)
  self.assertIn('save_env harbour_recovery_once',generated)
  self.assertEqual(generated,grub_configuration(generated,uuid,'/harbor/rootfs',True))
 def test_unsupported_subdirectory_root_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'filesystem root'):grub_configuration('root=UUID=00000000-0000-0000-0000-000000000001 /boot/harbor-vmlinuz','00000000-0000-0000-0000-000000000001','/other',True)

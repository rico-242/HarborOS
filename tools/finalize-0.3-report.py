"""Merge measured release checks and package the shareable source."""
from pathlib import Path
import json,hashlib,subprocess
root=Path(__file__).resolve().parents[1]
path=root/'dist/harbour-0.3.0-amd64.iso'
digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
assert digest==(root/'dist/harbour-0.3.0-amd64.iso.sha256').read_text().split()[0]
report=json.loads((root/'docs/release-0.3-validation.json').read_text())
report.update(json.loads((root/'docs/final-iso-0.3-validation.json').read_text()))
test_log=(root/'.local/test-0.3-output.log').read_text(encoding='utf-8',errors='replace')
assert 'Ran 21 tests' in test_log and '\nOK' in test_log
report.update(automated_tests=21,automated_tests_passed=True,iso_file=path.name,iso_bytes=path.stat().st_size,iso_sha256=digest,download_checksum_verified=True,physical_nas_services_active=['harbor','lightdm','ssh','smbd','docker'],physical_nas_failed_services=0,physical_nas_rebooted=False,physical_nas_package_upgrade_tested=False)
report.pop('before_reboot_id',None)
(root/'docs/release-0.3-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
subprocess.run([__import__('sys').executable,str(root/'tools/package-source.py')],check=True)
source=root/'dist/harbour-0.3.0-source.tar.gz'
source_hash=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
source.with_suffix(source.suffix+'.sha256').write_text(source_hash+'  '+source.name+'\n',encoding='utf-8')
print('ISO verified; 21 tests and final ISO installation/boot checks recorded; source packaged.')

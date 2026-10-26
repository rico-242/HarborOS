"""Exercise the boot-recovery handler using a VM-only interrupted journal fixture."""
import json,shutil,subprocess
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
core=Path('/usr/local/lib/harbour-updater/release_worker.py');source=Path('/tmp/harbour-latest-release-worker.py');compile(source.read_bytes(),str(source),'exec');shutil.copyfile(source,core)
root=Path('/var/lib/harbor/release-updates');journal=root/'activation.json';original=journal.read_bytes();record=json.loads(original);assert record['phase'] in ('committed','restored')
assert Path(record['old_path']).is_dir()
ident='0000000000000007';job=root/'jobs'/(ident+'.json');assert not job.exists()
try:
    record['phase']='activating';journal.write_text(json.dumps(record))
    job.write_text(json.dumps({'id':ident,'state':'running','boot_id':'previous-vm-test-boot','actor':'vm-test','title':'Disposable interrupted update fixture'}))
    subprocess.run(['/usr/local/sbin/harbour-release-update','recover'],check=True)
    assert json.loads(job.read_text())['state']=='failed'
    assert json.loads(journal.read_text())['phase']=='restored'
    report_path=Path('/root/harbour-maintenance-validation.json');report=json.loads(report_path.read_text());report['interrupted_update_recovery_handler']=True;report['interrupted_jobs_do_not_block_future_updates']=True;report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
finally:
    job.unlink(missing_ok=True)
    journal.write_bytes(original)

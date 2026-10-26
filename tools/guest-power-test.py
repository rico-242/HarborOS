import http.client,json,socket
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());conn=http.client.HTTPConnection('127.0.0.1',17080)
conn.request('POST','/api/login',json.dumps({'username':accounts['owner'],'password':accounts['owner_password']}),{'Content-Type':'application/json'})
response=conn.getresponse();session=json.loads(response.read());assert response.status==200
headers={'Cookie':response.getheader('Set-Cookie').split(';')[0],'X-Harbor-CSRF':session['csrf'],'Content-Type':'application/json'}
report_path=Path('/root/harbour-0.3-acceptance.json');report=json.loads(report_path.read_text());report['before_reboot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip();report_path.write_text(json.dumps(report,indent=2))
conn.request('POST','/api/system-action',json.dumps({'action':'reboot','confirmation':socket.gethostname()}),headers)
response=conn.getresponse();value=json.loads(response.read());assert response.status==202 and value['scheduled'];print('Owner-confirmed VM reboot scheduled.')

import json,urllib.request
value=json.load(urllib.request.urlopen('http://127.0.0.1:17081/api/status'))
assert value['phase']=='complete',value
print('Final ISO offline installation completed successfully.')

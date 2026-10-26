"""Owner-managed networkd bonds with independent timed rollback."""
import ipaddress,json,re,secrets,time
from pathlib import Path

MODES={'active-backup':'Active / backup','802.3ad':'LACP (802.3ad)'}
IFACE=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}\Z')
MAC=re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z')

def validate(data,interfaces):
    mode=data.get('mode');names=data.get('interfaces')
    if mode not in MODES or not isinstance(names,list) or not 2<=len(names)<=8 or len(set(names))!=len(names):raise ValueError('Choose two to eight different Ethernet adapters and a supported bond mode.')
    selected=[]
    for name in names:
        item=next((i for i in interfaces if i['name']==name and i['eligible']),None)
        if not item or not IFACE.fullmatch(name):raise ValueError('An adapter is unavailable, wireless, virtual, or already in use.')
        if not MAC.fullmatch(item['permanent_mac']):raise ValueError('An adapter has no reliable hardware address.')
        selected.append(item)
    primary=data.get('primary')
    if len({i['permanent_mac'] for i in selected})!=len(selected):raise ValueError('Bond members must have different permanent MAC addresses.')
    if primary not in names:raise ValueError('Choose the primary adapter from the selected adapters.')
    if mode=='802.3ad' and data.get('switch_ready') is not True:raise ValueError('Configure the switch ports as one LACP group before applying.')
    if mode=='802.3ad':
        speeds={i.get('speed_mbps') for i in selected if i.get('speed_mbps')}
        if len(speeds)>1 or any(i.get('duplex')=='half' for i in selected):raise ValueError('LACP members must use the same link speed and full duplex.')
    method=data.get('method','dhcp');address='';gateway='';dns=[]
    if method=='static':
        address=str(ipaddress.IPv4Interface(data.get('address','')))
        gateway=str(ipaddress.IPv4Address(data.get('gateway','')))
        if ipaddress.IPv4Address(gateway) not in ipaddress.IPv4Interface(address).network:raise ValueError('The gateway must be in the same IPv4 subnet.')
        if not isinstance(data.get('dns'),list) or not 1<=len(data['dns'])<=3:raise ValueError('Choose one to three DNS server addresses.')
        if any(not isinstance(value,str) or '%' in value or any(c in value for c in '\r\n\x00') for value in data['dns']):raise ValueError('Use plain IP addresses for DNS servers.')
        dns=[str(ipaddress.ip_address(value)) for value in data['dns']]
    elif method!='dhcp':raise ValueError('Choose DHCP or a static IPv4 address.')
    return {'mode':mode,'interfaces':[{'name':i['name'],'mac':i['permanent_mac']} for i in selected], 'primary':primary,
            'mac':next(i['permanent_mac'] for i in selected if i['name']==primary),'method':method,'address':address,'gateway':gateway,'dns':dns}

def configuration(plan):
    files={'05-harbour-bond.netdev':f'[NetDev]\nName=bond0\nKind=bond\nMACAddress={plan["mac"]}\n\n[Bond]\nMode={plan["mode"]}\nMIIMonitorSec=100ms\n'+('LACPTransmitRate=fast\nTransmitHashPolicy=layer3+4\n' if plan['mode']=='802.3ad' else '')}
    for item in plan['interfaces']:
        files['04-harbour-port-'+item['mac'].replace(':','')+'.network']=f'[Match]\nPermanentMACAddress={item["mac"]}\n\n[Link]\nRequiredForOnline=no\n\n[Network]\nBond=bond0\nDHCP=no\nLinkLocalAddressing=no\nIPv6AcceptRA=no\n'+('PrimarySlave=yes\n' if item['name']==plan['primary'] and plan['mode']=='active-backup' else '')
    content='[Match]\nName=bond0\n\n[Network]\nMulticastDNS=yes\nIPv6AcceptRA=yes\n'
    if plan['method']=='dhcp':content+='DHCP=yes\n\n[DHCPv4]\nClientIdentifier=mac\nUseHostname=no\n'
    else:content+=f'DHCP=no\nAddress={plan["address"]}\nGateway={plan["gateway"]}\n'+''.join('DNS='+v+'\n' for v in plan['dns'])
    files['05-harbour-bond.network']=content
    return files

class Networking:
    def __init__(self,app,run,error,atomic):
        self.app,self.run,self.error,self.atomic=app,run,error,atomic
        self.root=app.state/'network';self.root.mkdir(exist_ok=True)
        self.status_file=self.root/'status.json';self.config_file=self.root/'config.json';self.plans={}

    def inventory(self):
        if self.app.demo:return []
        links=json.loads(self.run('ip','-j','-d','link','show').stdout);addresses={v['ifname']:v.get('addr_info',[]) for v in json.loads(self.run('ip','-j','address','show').stdout)}
        result=[]
        owned=json.loads(self.config_file.read_text()) if self.config_file.exists() else None
        owned_names={i['name'] for i in (owned or {}).get('interfaces',[])}
        for item in links:
            name=item['ifname'];device=Path('/sys/class/net')/name;physical=(device/'device').exists() and not (device/'wireless').exists()
            if not IFACE.fullmatch(name):continue
            permanent=''
            speed=None;duplex=None
            if physical:
                try:
                    speed=int((device/'speed').read_text().strip());speed=speed if speed>0 else None
                    duplex=(device/'duplex').read_text().strip()
                except (OSError,ValueError):pass
                output=self.run('ethtool','-P',name,check=False).stdout.strip().split()
                if output and MAC.fullmatch(output[-1].lower()):permanent=output[-1].lower()
                elif 'master' not in item:permanent=item.get('address','').lower()
            result.append({'name':name,'mac':item.get('address',''),'permanent_mac':permanent,'speed_mbps':speed,'duplex':duplex,'carrier':'LOWER_UP' in item.get('flags',[]),'state':item.get('operstate','UNKNOWN'),'physical':physical,
                'eligible':physical and not item.get('master') and bool(MAC.fullmatch(permanent)),'master':item.get('master'),'addresses':[a['local']+'/'+str(a['prefixlen']) for a in addresses.get(name,[]) if a.get('scope')=='global'],'owned':name in owned_names})
        return result

    def status(self):
        value=json.loads(self.status_file.read_text()) if self.status_file.exists() else None
        if value:self.app.jobs[value['id']]=value
        return value

    def info(self):
        adapters=self.inventory();status=self.status()
        return {'interfaces':adapters,'modes':MODES,'config':json.loads(self.config_file.read_text()) if self.config_file.exists() else None,'transaction':status,
                'supported':not self.app.demo and self.run('systemctl','is-active','systemd-networkd',check=False).returncode==0,'eligible_count':sum(i['eligible'] for i in adapters),'rollback_seconds':120}

    def plan(self,data):
        if self.app.demo:raise self.error('Network changes are available on an installed Harbour appliance.',409)
        if self.config_file.exists():raise self.error('Remove the existing Harbour bond before choosing another configuration.',409)
        if any(i['name']=='bond0' for i in self.inventory()):raise self.error('bond0 already exists and is not managed by Harbour.',409)
        if self.run('systemctl','is-active','systemd-networkd',check=False).returncode:raise self.error('Bonding requires systemd-networkd to manage these adapters.',409)
        try:value=validate(data,self.inventory())
        except (ValueError,TypeError) as error:raise self.error(str(error))
        token=secrets.token_urlsafe(24);self.plans={k:v for k,v in self.plans.items() if v['expires']>time.monotonic()}
        if len(self.plans)>=16:self.plans.pop(next(iter(self.plans)))
        self.plans[token]={'plan':value,'expires':time.monotonic()+300}
        return {'token':token,'plan':value,'warning':'Connectivity will briefly stop. Reconnect and keep this configuration within 120 seconds or Harbour restores the previous settings.'}

    def action(self,data):
        if self.app.demo:raise self.error('Network changes are disabled in the preview.',409)
        action=data.get('action')
        if action in ('keep','revert'):
            state=self.status()
            if not state or state['id']!=data.get('id') or state.get('phase')!='awaiting_confirmation':raise self.error('There is no pending network configuration to confirm.',409)
            self.run('/usr/local/sbin/harbour-network-change',action,state['id'],timeout=40)
            return self.status()
        if action not in ('apply','remove') or data.get('confirmation')!='APPLY':raise self.error('Review the network change and type APPLY to continue.')
        with self.app.lock:
            self.app.system_settings.external_status()
            if any(j['state'] in ('queued','running') for j in self.app.jobs.values()):raise self.error('Wait for the current operation to finish.',409)
            if action=='apply':
                record=self.plans.pop(data.get('token',''),None)
                if not record or record['expires']<time.monotonic():raise self.error('The network plan expired. Review the adapters again.',409)
                plan=record['plan'];inventory=self.inventory()
                for item in plan['interfaces']:
                    if not any(i['name']==item['name'] and i['permanent_mac']==item['mac'] and i['eligible'] for i in inventory):raise self.error('Adapter identities changed. No network settings were modified.',409)
            else:
                if not self.config_file.exists():raise self.error('No Harbour bond is configured.',409)
                plan=json.loads(self.config_file.read_text())
            ident=secrets.token_hex(8);job={'id':ident,'title':'Create network bond' if action=='apply' else 'Remove network bond','kind':'network','state':'queued','phase':'queued','actor':self.app.admin['username'],'created':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'stage':'Preparing network change','external':True}
            request={'id':ident,'action':action,'plan':plan,'job':job};self.atomic(self.root/'request.json',request);self.atomic(self.status_file,job)
            try:self.run('systemd-run','--collect','--on-active=3s','--unit=harbour-network-change-'+ident,'/usr/local/sbin/harbour-network-change','apply',ident)
            except Exception:
                job.update(state='failed',phase='failed');self.atomic(self.status_file,job);raise
            self.app.jobs[ident]=job;return job

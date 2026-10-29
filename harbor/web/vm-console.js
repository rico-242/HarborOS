import RFB from '/vendor/novnc/core/rfb.js';
const name=new URLSearchParams(location.search).get('name')||'';
document.querySelector('#name').textContent=name;
let client;
export { client };
async function connect(){
  if(client)client.disconnect();
  const status=document.querySelector('#status');status.textContent='Connecting…';
  try{
    const response=await fetch('/api/session');
    if(!response.ok)throw new Error('Sign in to Harbour as the owner, then reconnect.');
    if((await response.json()).role!=='owner')throw new Error('The owner account is required.');
    client=new RFB(document.querySelector('#screen'),`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/vm-console?name=${encodeURIComponent(name)}`);
    client.scaleViewport=true;
    client.addEventListener('connect',()=>{status.textContent='Connected';client.focus();});
    client.addEventListener('disconnect',()=>{status.textContent='Disconnected. Start the VM and reconnect.';});
    client.addEventListener('securityfailure',()=>{status.textContent='Console security negotiation failed.';});
  }catch(error){status.textContent=error.message;}
}
document.querySelector('#reconnect').onclick=connect;
document.querySelector('#keys').onclick=()=>client?.sendCtrlAltDel();
document.querySelector('#fullscreen').onclick=()=>document.querySelector('#screen').requestFullscreen();
window.addEventListener('beforeunload',()=>client?.disconnect());
connect();

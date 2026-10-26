'use strict';
let uploadBusy=false,uploadRequest=null;
function resetTransfers(){uploadRequest?.abort();const panel=document.getElementById('upload-progress');if(panel)panel.hidden=true;}
async function transferFiles(files,destination){
 if(uploadBusy)throw new Error('An import is already running. Wait for it to finish.');
 if(!files.length)return;
 if(files.some(file=>file.size>1024**3))throw new Error('Use SMB to transfer files larger than 1 GB.');
 uploadBusy=true;
 const total=files.reduce((n,file)=>n+file.size,0),started=performance.now();let completed=0,count=0;
 let panel=document.getElementById('upload-progress');
 if(!panel){panel=document.createElement('section');panel.id='upload-progress';panel.className='upload-progress';panel.setAttribute('aria-label','File import progress');document.body.append(panel);}
 panel.hidden=false;
 const render=(file,loaded,saving=false,error='')=>{
  const sent=completed+loaded,percent=total?Math.floor(100*sent/total):0,rate=sent/Math.max(1,(performance.now()-started)/1000);
  panel.innerHTML=`<header><strong>Importing files</strong><span>${count+1} / ${files.length}</span></header><p class="upload-name">${E(file.name)}</p><progress max="100" value="${saving?Math.min(99,percent):percent}" aria-label="Import progress"></progress><p role="status">${error?E(error):saving?'Saving to drive…':`${percent}% · ${bytes(sent)} / ${bytes(total)} · ${bytes(rate)}/s`}</p><small>Destination: ${E(destination)}</small>${error?'<button class="button secondary" data-upload-close>Close</button>':''}`;
  panel.querySelector('[data-upload-close]')?.addEventListener('click',()=>panel.hidden=true);
 };
 try{
  for(const file of files){
   render(file,0);
   await new Promise((resolve,reject)=>{
    const request=uploadRequest=new XMLHttpRequest();
    request.open('POST','/api/upload?path='+encodeURIComponent(destination)+'&name='+encodeURIComponent(file.name));
    request.setRequestHeader('X-Harbor-CSRF',csrf);request.setRequestHeader('Content-Type','application/octet-stream');
    request.upload.onprogress=event=>render(file,event.loaded,event.loaded>=file.size);
    request.upload.onload=()=>render(file,file.size,true);
    request.onerror=()=>reject(new Error('Connection lost. Check the destination before retrying; completed files are retained.'));
    request.onabort=()=>reject(new Error('Import interrupted. Completed files are retained.'));
    request.onload=()=>{let result;try{result=JSON.parse(request.responseText);}catch{reject(new Error('The server returned an unreadable response.'));return;}if(request.status>=200&&request.status<300)resolve(result);else{if(request.status===401)showAuth();reject(new Error(result.error||'Import failed.'));}};
    request.send(file);
   });
   completed+=file.size;count++;
  }
  panel.innerHTML=`<header><strong>Import complete</strong><button class="icon-button" aria-label="Close import progress">×</button></header><progress max="100" value="100" aria-label="Import complete"></progress><p role="status">${count} file${count===1?'':'s'} saved · ${bytes(total)}</p><small>${E(destination)}</small>`;
  panel.querySelector('button').onclick=()=>panel.hidden=true;
 }catch(error){render(files[count],0,false,`${count} completed. ${error.message}`);throw error;}
 finally{uploadBusy=false;uploadRequest=null;}
}
window.addEventListener('beforeunload',event=>{if(uploadBusy){event.preventDefault();event.returnValue='';}});

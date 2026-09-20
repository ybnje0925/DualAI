const $=s=>document.querySelector(s), keys=["chatgpt","gemini"];
let connected=false,busy=false,results={},request={id:crypto.randomUUID(),prompt:null,attachments:[]},probing=false;
let attachments=[];
const pending=new Map();
function rpc(command,payload={},timeout=25000) {
  const id=crypto.randomUUID();
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error(command==="send"?"응답 연결이 끊겼습니다. 서비스 화면에서 전송 여부를 확인하세요.":"확장 프로그램에서 이 웹사이트를 연결해 주세요."));},timeout);
    pending.set(id,{resolve,reject,timer});
    window.postMessage({channel:"dualai-request",id,command,payload},location.origin);
  });
}
window.addEventListener("message",event=>{
  if(event.source!==window || event.origin!==location.origin || event.data?.channel!=="dualai-response") return;
  const p=pending.get(event.data.id);if(!p)return;
  clearTimeout(p.timer);pending.delete(event.data.id);
  event.data.response?.ok ? p.resolve(event.data.response) : p.reject(Error(event.data.response?.error||"연결 실패"));
});
function controls() {
  for(const button of document.querySelectorAll("button:not(#help)")) button.disabled=!connected||busy;
  for(const key of keys) document.querySelector('[data-retry="'+key+'"]').disabled=busy||!connected||results[key]?.state!=="failed";
}
function setBusy(value) {busy=value;controls();}
function layout(){return {ratio:0.5,screen:{left:screen.availLeft||0,top:screen.availTop||0,width:screen.availWidth,height:screen.availHeight}};}
function fileData(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error("파일을 읽지 못했습니다."));reader.onload=()=>resolve({name:file.name,type:file.type||"application/octet-stream",data:String(reader.result).split(",",2)[1]});reader.readAsDataURL(file);});}
function renderFiles(){const list=$("#file-list");list.textContent=attachments.length?attachments.map(f=>`${f.name} (${(f.size/1024/1024).toFixed(1)}MB)`).join(" · "):"파일은 최대 10개, 전체 15MB까지";}
function fileKey(files=[]){return files.map(f=>`${f.name}:${f.size}:${f.lastModified}`).join("|");}
function display(key,result) {
  const el=$("#"+key+"-result");el.textContent=result.message;el.className=result.warning?"partial":result.state;
}
async function send(services,retryKey) {
  if(busy || !connected)return;
  const prompt=retryKey?results[retryKey]?.prompt:$("#prompt").value;
  const chosenFiles=retryKey?results[retryKey]?.attachments:attachments;
  if(!prompt?.trim()) {$("#prompt").focus();return;}
  if(!retryKey && request.prompt!==prompt) request={id:crypto.randomUUID(),prompt,attachments:[]};
  const id=retryKey?results[retryKey].requestId:request.id;
  const selected=services.filter(k=>results[k]?.state!=="unknown" && !(results[k]?.state==="success" && results[k].prompt===prompt && fileKey(results[k].attachments)===fileKey(chosenFiles)));
  if(!selected.length){$("#notice").textContent="이미 전송했거나 전송 여부 확인이 필요합니다. 서비스 화면 확인 후 새 대화를 시작하세요.";return;}
  setBusy(true);$("#notice").textContent="";
  selected.forEach(k=>display(k,{state:"sending",message:"질문 전달 중…"}));
  try{
    const encoded=await Promise.all((chosenFiles||[]).map(fileData));
    const response=await rpc("send",{services:selected,prompt,requestId:id,attachments:encoded},90000);
    for(const key of selected) {
      results[key]={...response.results[key],prompt,requestId:id,attachments:chosenFiles||[]};
      display(key,results[key]);
    }
  }catch(error){
    $("#notice").textContent=error.message;
    for(const key of selected){results[key]={state:"unknown",message:"전송 여부 확인 필요 · 새 대화 전까지 잠김",prompt,requestId:id,attachments:chosenFiles||[]};display(key,results[key]);}
  }finally{setBusy(false);}
}
async function newChat(services){
  if(busy || !confirm("선택한 서비스에서 새 대화를 시작합니다. 서비스 입력창의 작성 중인 글은 사라질 수 있습니다. 계속할까요?"))return;
  setBusy(true);
  try{
    const response=await rpc("newChat",{services});
    for(const key of services){if(response.results[key].state==="ready")delete results[key];display(key,response.results[key]);}
    request={id:crypto.randomUUID(),prompt:null,attachments:[]};
  }catch(error){$("#notice").textContent=error.message;}finally{setBusy(false);}
}
$("#send").onclick=()=>send(keys);
document.querySelectorAll("[data-send]").forEach(b=>b.onclick=()=>send([b.dataset.send]));
document.querySelectorAll("[data-new]").forEach(b=>b.onclick=()=>newChat([b.dataset.new]));
document.querySelectorAll("[data-retry]").forEach(b=>b.onclick=()=>send([b.dataset.retry],b.dataset.retry));
$("#new").onclick=()=>newChat(keys);
$("#prompt").addEventListener("input",()=>$("#count").textContent=$("#prompt").value.length.toLocaleString()+" / 100,000");
$("#files").addEventListener("change",()=>{const chosen=[...$("#files").files];const total=[...attachments,...chosen].reduce((n,f)=>n+f.size,0);if(attachments.length+chosen.length>10||total>15*1024*1024){$("#notice").textContent="첨부 파일은 한 번에 최대 10개, 전체 15MB까지 가능합니다.";$("#files").value="";return;}attachments.push(...chosen);request={id:crypto.randomUUID(),prompt:$("#prompt").value,attachments:[]};renderFiles();$("#files").value="";});
$("#prompt").addEventListener("keydown",e=>{if(!e.isComposing && e.key==="Enter" && (e.ctrlKey||e.metaKey)){e.preventDefault();send(keys);}});
for(const action of ["open","arrange"]) $("#"+action).onclick=async()=>{
  setBusy(true);
  try{const response=await rpc(action,layout());document.body.classList.add("workspace");$("#notice").textContent=response.warning||"각 서비스에 직접 로그인해 주세요. 질문과 답변은 별도 서버에 저장하지 않습니다.";}
  catch(error){$("#notice").textContent=error.message;}finally{setBusy(false);}
};
$("#help").onclick=()=>document.body.classList.toggle("show-help");
async function probe(){
  if(busy||probing)return;probing=true;
  try{
    await rpc("ping",{},1500);connected=true;
    document.body.classList.add("connected");
    $("#connection").textContent="브라우저 연결됨";
    $("#notice").textContent="";
    const response=await rpc("status",{},6000);
    for(const key of keys) $("#"+key+"-status").textContent=response.results[key].message;
  }catch{
    connected=false;document.body.classList.remove("connected");
    const mobile=/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    $("#connection").textContent=mobile?"데스크톱 브라우저 필요":"Chrome/Edge 연결 필요";
    $("#notice").textContent=mobile
      ? "휴대폰 브라우저에서는 확장 연결을 지원하지 않습니다. 컴퓨터의 Chrome 또는 Edge에서 이 주소를 여세요."
      : "앱 안 미리보기에서는 브라우저 확장이 연결되지 않습니다. 컴퓨터의 Chrome 또는 Edge에서 이 주소를 열고 확장 아이콘에서 연결하세요.";
  }finally{probing=false;controls();}
}
probe();setInterval(probe,3500);

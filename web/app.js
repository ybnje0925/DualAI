const $=s=>document.querySelector(s), keys=["chatgpt","gemini"];
let connected=false,busy=false,results={},request={id:crypto.randomUUID(),prompt:null},probing=false;
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
function layout(){return {ratio:Number($("#ratio").value)/100,screen:{left:screen.availLeft||0,top:screen.availTop||0,width:screen.availWidth,height:screen.availHeight}};}
function display(key,result) {
  const el=$("#"+key+"-result");el.textContent=result.message;el.className=result.state;
}
async function send(services,retryKey) {
  if(busy || !connected)return;
  const prompt=retryKey?results[retryKey]?.prompt:$("#prompt").value;
  if(!prompt?.trim()) {$("#prompt").focus();return;}
  if(!retryKey && request.prompt!==prompt) request={id:crypto.randomUUID(),prompt};
  const id=retryKey?results[retryKey].requestId:request.id;
  const selected=services.filter(k=>results[k]?.state!=="unknown" && !(results[k]?.state==="success" && results[k].prompt===prompt));
  if(!selected.length){$("#notice").textContent="이미 전송했거나 전송 여부 확인이 필요합니다. 서비스 화면 확인 후 새 대화를 시작하세요.";return;}
  setBusy(true);$("#notice").textContent="";
  selected.forEach(k=>display(k,{state:"sending",message:"질문 전달 중…"}));
  try{
    const response=await rpc("send",{services:selected,prompt,requestId:id},45000);
    for(const key of selected) {
      results[key]={...response.results[key],prompt,requestId:id};
      display(key,results[key]);
    }
  }catch(error){
    $("#notice").textContent=error.message;
    for(const key of selected){results[key]={state:"unknown",message:"전송 여부 확인 필요 · 새 대화 전까지 잠김",prompt,requestId:id};display(key,results[key]);}
  }finally{setBusy(false);}
}
async function newChat(services){
  if(busy || !confirm("선택한 서비스에서 새 대화를 시작합니다. 서비스 입력창의 작성 중인 글은 사라질 수 있습니다. 계속할까요?"))return;
  setBusy(true);
  try{
    const response=await rpc("newChat",{services});
    for(const key of services){if(response.results[key].state==="ready")delete results[key];display(key,response.results[key]);}
    request={id:crypto.randomUUID(),prompt:null};
  }catch(error){$("#notice").textContent=error.message;}finally{setBusy(false);}
}
$("#send").onclick=()=>send(keys);
document.querySelectorAll("[data-send]").forEach(b=>b.onclick=()=>send([b.dataset.send]));
document.querySelectorAll("[data-new]").forEach(b=>b.onclick=()=>newChat([b.dataset.new]));
document.querySelectorAll("[data-retry]").forEach(b=>b.onclick=()=>send([b.dataset.retry],b.dataset.retry));
$("#new").onclick=()=>newChat(keys);
$("#prompt").addEventListener("input",()=>$("#count").textContent=$("#prompt").value.length.toLocaleString()+" / 100,000");
$("#prompt").addEventListener("keydown",e=>{if(!e.isComposing && e.key==="Enter" && (e.ctrlKey||e.metaKey)){e.preventDefault();send(keys);}});
for(const action of ["open","arrange"]) $("#"+action).onclick=async()=>{
  setBusy(true);
  try{const response=await rpc(action,layout());document.body.classList.add("workspace");$("#notice").textContent=response.warning||"각 서비스에 직접 로그인해 주세요. 질문과 답변은 별도 서버에 저장하지 않습니다.";}
  catch(error){$("#notice").textContent=error.message;}finally{setBusy(false);}
};
$("#ratio").oninput=()=>$("#ratio-label").textContent=$("#ratio").value+" : "+(100-$("#ratio").value);
$("#ratio").onchange=()=>{if(connected && document.body.classList.contains("workspace"))$("#arrange").click();};
$("#help").onclick=()=>document.body.classList.toggle("show-help");
async function probe(){
  if(busy||probing)return;probing=true;
  try{
    await rpc("ping",{},1500);connected=true;
    document.body.classList.add("connected");
    $("#connection").textContent="브라우저 연결됨";
    const response=await rpc("status",{},6000);
    for(const key of keys) $("#"+key+"-status").textContent=response.results[key].message;
  }catch{
    connected=false;document.body.classList.remove("connected");
    $("#connection").textContent="확장 프로그램 연결 필요";
  }finally{probing=false;controls();}
}
probe();setInterval(probe,3500);

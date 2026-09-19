import {SERVICES,validate,bounds} from "./protocol.js";
const locks = new Set();
let opening = false;
const fail = error => ({ok:false,error});
async function tabFor(key, create=false) {
  const {managed={}}=await chrome.storage.session.get("managed");
  let tab;
  if (managed[key]) tab=await chrome.tabs.get(managed[key]).catch(()=>null);
  if (!tab && create) {
    const win=await chrome.windows.create({url:SERVICES[key].url,type:"popup",focused:false});
    tab=win.tabs[0];
    // Merge fresh state: separate service creations may overlap.
    const latest=(await chrome.storage.session.get("managed")).managed || {};
    latest[key]=tab.id;
    await chrome.storage.session.set({managed:latest});
  }
  return tab;
}
async function content(key, command, payload={}) {
  const tab=await tabFor(key);
  if (!tab) return {state:"failed",message:"비교 화면 열기를 눌러 서비스 창을 열어 주세요."};
  try {
    return await chrome.tabs.sendMessage(tab.id,{type:"dualai-site",command,...payload});
  } catch {
    if (command==="send") return {state:"unknown",message:"전송 여부를 확인하지 못했습니다. 서비스 화면을 확인한 뒤 새 대화를 시작하세요."};
    return {state:"failed",message:"로그인 또는 페이지 로딩을 확인해 주세요."};
  }
}
async function arrange(sender,payload,create) {
  if (opening || locks.size) throw new Error("현재 작업이 끝난 뒤 다시 시도하세요.");
  opening=true;
  try {
    const rect=bounds(payload);
    let warning="";
    const place=async(id,area)=>{try{await chrome.windows.update(id,{state:"normal",...area});}catch{warning="창 자동 정렬이 제한되었습니다. 열린 창을 직접 좌우로 배치해 주세요.";}};
    let controller=await chrome.windows.get(sender.tab.windowId);
    if (create && controller.type!=="popup")
      controller=await chrome.windows.create({tabId:sender.tab.id,type:"popup",focused:true});
    if (controller.type==="popup") await place(controller.id,rect.controller);
    for (const key of Object.keys(SERVICES)) {
      const tab=await tabFor(key,create);
      if (tab) await place(tab.windowId,rect[key]);
    }
    await chrome.windows.update(controller.id,{focused:true});
    return {ok:true,warning};
  } finally { opening=false; }
}
async function sendOne(key,payload) {
  if (locks.has(key) || opening) return {state:"failed",message:"이 서비스의 이전 작업이 끝날 때까지 기다려 주세요."};
  locks.add(key);
  const entryKey="delivery:"+key+":"+payload.requestId;
  try {
    const prior=(await chrome.storage.session.get(entryKey))[entryKey];
    if (prior && prior.state!=="failed")
      return prior.state==="pending" ? {state:"unknown",message:"이전 전송 여부를 화면에서 확인하세요. 자동 재전송하지 않습니다."} : prior;
    const ready=await content(key,"status");
    if (ready.state!=="ready") return {state:"failed",message:ready.message};
    await chrome.storage.session.set({[entryKey]:{state:"pending",message:"전송 확인 중",at:Date.now()}});
    const result=await content(key,"send",{prompt:payload.prompt,requestId:payload.requestId});
    await chrome.storage.session.set({[entryKey]:{...result,at:Date.now()}});
    return result;
  } catch {
    return {state:"unknown",message:"전송 결과 연결이 끊겼습니다. 실제 서비스 화면을 확인하세요."};
  } finally { locks.delete(key); }
}
chrome.runtime.onMessage.addListener((m,sender,respond)=>{
  if(m?.type!=="dualai") return;
  (async()=>{
    const {siteOrigin}=await chrome.storage.local.get("siteOrigin");
    if (!siteOrigin || !sender.tab || new URL(sender.url).origin!==siteOrigin) return fail("이 웹사이트는 연결되지 않았습니다. 확장 프로그램에서 연결하세요.");
    const payload=validate(m.command,m.payload);
    if(m.command==="ping") return {ok:true,version:chrome.runtime.getManifest().version};
    if(m.command==="open" || m.command==="arrange") return arrange(sender,payload,m.command==="open");
    if(m.command==="status") {
      const results={};
      for(const key of Object.keys(SERVICES)) results[key]=await content(key,"status");
      return {ok:true,results};
    }
    if(m.command==="send") {
      const pairs=await Promise.all(payload.services.map(async key=>[key,await sendOne(key,payload)]));
      return {ok:true,results:Object.fromEntries(pairs)};
    }
    if(m.command==="newChat") {
      const results={};
      for(const key of payload.services) {
        if(locks.has(key) || opening) {results[key]={state:"failed",message:"전송이 끝난 뒤 새 대화를 시작하세요."};continue;}
        locks.add(key);
        try {
          const tab=await tabFor(key,true);
          await chrome.tabs.update(tab.id,{url:SERVICES[key].url});
          results[key]={state:"ready",message:"새 대화를 열었습니다."};
        } catch {results[key]={state:"failed",message:"새 대화 화면을 열지 못했습니다."};}
        finally {locks.delete(key);}
      }
      return {ok:true,results};
    }
  })().then(respond).catch(error=>respond(fail(error.message || "작업에 실패했습니다.")));
  return true;
});

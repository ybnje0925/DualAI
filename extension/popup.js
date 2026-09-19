const status = document.querySelector("#status");
let tab;
(async () => {
  [tab] = await chrome.tabs.query({active:true,currentWindow:true});
  document.querySelector("#origin").textContent = tab?.url ? new URL(tab.url).origin : "웹사이트 탭을 선택하세요.";
})();
document.querySelector("#connect").onclick = async () => {
  try {
    const url = new URL(tab.url);
    if (!(url.protocol === "https:" || (url.protocol === "http:" && ["localhost","127.0.0.1"].includes(url.hostname))))
      throw new Error("HTTPS 웹사이트 또는 로컬 테스트 주소에서 연결해 주세요.");
    if (["chatgpt.com","gemini.google.com"].includes(url.hostname)) throw new Error("AI 서비스가 아닌 DualAI 웹사이트 탭에서 연결하세요.");
    const pattern = url.origin + "/*";
    const granted = await chrome.permissions.request({origins:[pattern]});
    if (!granted) throw new Error("이 웹사이트 연결 권한이 필요합니다.");
    const old = await chrome.storage.local.get("siteOrigin");
    await chrome.scripting.unregisterContentScripts({ids:["dualai-bridge"]}).catch(()=>{});
    await chrome.scripting.registerContentScripts([{id:"dualai-bridge",matches:[pattern],js:["bridge.js"],runAt:"document_idle",persistAcrossSessions:true}]);
    await chrome.storage.local.set({siteOrigin:url.origin});
    if (old.siteOrigin && old.siteOrigin !== url.origin) await chrome.permissions.remove({origins:[old.siteOrigin+"/*"]});
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:["bridge.js"]});
    status.textContent = "연결되었습니다. 웹사이트에서 비교 화면 열기를 누르세요.";
  } catch (error) { status.textContent = error.message || "연결하지 못했습니다. 페이지를 새로고침하세요."; }
};
document.querySelector("#disconnect").onclick = async () => {
  const {siteOrigin} = await chrome.storage.local.get("siteOrigin");
  await chrome.storage.local.remove("siteOrigin");
  await chrome.scripting.unregisterContentScripts({ids:["dualai-bridge"]}).catch(()=>{});
  if (siteOrigin) await chrome.permissions.remove({origins:[siteOrigin+"/*"]});
  status.textContent = "연결 해제되었습니다.";
};

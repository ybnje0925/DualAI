const WEB_APP_URL = "https://gptgeminiyoung.vercel.app/";
const $ = selector => document.querySelector(selector);
const status = $("#status");
let tab;
let savedOrigin = "";
let activeOrigin = "";
function candidateOrigin(raw) {
  try {
    const url = new URL(raw);
    if (url.hostname === "chatgpt.com" || url.hostname === "gemini.google.com") return null;
    if (url.protocol === "https:") return url.origin;
    if (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)) return url.origin;
  } catch {}
  return null;
}
function render() {
  $("#origin").textContent = activeOrigin || "브라우저 새 탭 또는 내부 페이지";
  $("#saved").textContent = savedOrigin ? `저장된 연결: ${savedOrigin}` : "";
  $("#disconnect").hidden = !savedOrigin;
  $("#connect").textContent = activeOrigin ? "이 웹사이트 연결" : "DualAI 웹앱 열기";
}
(async () => {
  try {
    [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    activeOrigin = candidateOrigin(tab?.url);
    ({siteOrigin:savedOrigin=""} = await chrome.storage.local.get("siteOrigin"));
    render();
    if (!activeOrigin) status.textContent = "연결할 수 없는 탭입니다. DualAI 웹앱을 열고 그 탭에서 확장 아이콘을 누르세요.";
    else if (activeOrigin === savedOrigin) status.textContent = "이 웹사이트에 연결되어 있습니다.";
    else status.textContent = "웹앱에서 확장 아이콘을 누른 뒤 이 웹사이트 연결을 선택하세요.";
  } catch {
    status.textContent = "브라우저 탭을 확인할 수 없습니다. DualAI 웹앱 탭에서 확장을 열어 주세요.";
  }
})();
$("#connect").onclick = async () => {
  try {
    if (!activeOrigin) {
      await chrome.tabs.create({url:WEB_APP_URL,active:true});
      status.textContent = "DualAI 웹앱을 열었습니다. 웹앱 탭에서 확장 아이콘을 한 번 더 누르세요.";
      return;
    }
    const granted = await chrome.permissions.request({origins:[activeOrigin+"/*"]});
    if (!granted) throw new Error("이 웹사이트 연결 권한이 필요합니다.");
    await chrome.scripting.unregisterContentScripts({ids:["dualai-bridge"]}).catch(()=>{});
    await chrome.scripting.registerContentScripts([{id:"dualai-bridge",matches:[activeOrigin+"/*"],js:["bridge.js"],runAt:"document_idle",persistAcrossSessions:true}]);
    const oldOrigin = savedOrigin;
    await chrome.storage.local.set({siteOrigin:activeOrigin});
    if (oldOrigin && oldOrigin !== activeOrigin) await chrome.permissions.remove({origins:[oldOrigin+"/*"]});
    await chrome.scripting.executeScript({target:{tabId:tab.id},files:["bridge.js"]});
    savedOrigin = activeOrigin;
    render();
    status.textContent = "연결되었습니다. 웹앱에서 비교 화면 열기를 누르세요.";
  } catch {
    status.textContent = "연결하지 못했습니다. DualAI 웹앱 탭에서 확장을 열고 다시 연결하세요.";
  }
};
$("#disconnect").onclick = async () => {
  try {
    if (savedOrigin) await chrome.permissions.remove({origins:[savedOrigin+"/*"]});
    await chrome.storage.local.remove("siteOrigin");
    await chrome.scripting.unregisterContentScripts({ids:["dualai-bridge"]}).catch(()=>{});
    savedOrigin = "";
    render();
    status.textContent = "연결을 해제했습니다.";
  } catch {
    status.textContent = "연결을 해제하지 못했습니다. 확장 프로그램 설정을 확인하세요.";
  }
};

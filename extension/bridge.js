(() => {
  if (window.__dualaiBridge) return;
  window.__dualaiBridge = true;
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const m = event.data;
    if (!m || m.channel !== "dualai-request" || typeof m.id !== "string" || m.id.length > 100) return;
    let response;
    try {
      response = await chrome.runtime.sendMessage({type:"dualai",command:m.command,payload:m.payload});
    } catch { response = {ok:false,error:"확장 프로그램 연결이 끊겼습니다. 페이지를 새로고침하고 다시 연결하세요."}; }
    window.postMessage({channel:"dualai-response",id:m.id,response}, location.origin);
  });
})();

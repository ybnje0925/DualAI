(() => {
  if (window.__dualaiSiteAdapter) return;
  window.__dualaiSiteAdapter=true;
  const isChat = location.hostname==="chatgpt.com";
  const spec=isChat ? {
    editors:['#prompt-textarea','[contenteditable="true"][data-placeholder]','textarea[placeholder]'],
    send:['[data-testid="send-button"]','button[aria-label="Send prompt"]'],
    stop:['[data-testid="stop-button"]','button[aria-label="Stop streaming"]'],
    messages:['[data-message-author-role="user"]']
  } : {
    editors:['rich-textarea [contenteditable="true"]','[contenteditable="true"][role="textbox"]','textarea[aria-label]'],
    send:['button.send-button','button[aria-label="Send message"]','button[aria-label="메시지 보내기"]'],
    stop:['button[aria-label="Stop response"]','button[aria-label="응답 중지"]','button.stop-button'],
    messages:['user-query','[data-test-id="user-query"]']
  };
  const visible=e=>!!e && e.getClientRects().length>0 && getComputedStyle(e).visibility!=="hidden";
  const find=list=>list.flatMap(s=>[...document.querySelectorAll(s)]).find(visible);
  const read=e=>e instanceof HTMLTextAreaElement || e instanceof HTMLInputElement ? e.value : e.innerText;
  const exact=s=>s.replace(/\r\n/g,"\n").replace(/\n+$/,"");
  const normalized=s=>s.replace(/\s+/g," ").trim();
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  let busy=false;
  const seen=new Map();
  function status() {
    if(find(spec.stop)) return {state:"busy",message:"이전 답변 생성 중"};
    if(!find(spec.editors)) return {state:"failed",message:"로그인과 페이지 로딩을 확인해 주세요."};
    return {state:"ready",message:"입력창 준비됨"};
  }
  function sendButton() {
    return find(spec.send) || [...document.querySelectorAll('button,[role="button"]')].find(e=>visible(e) && /^(send|send message|send prompt|submit|보내기|전송|메시지 보내기|프롬프트 보내기)$/i.test(e.getAttribute("aria-label")||e.textContent.trim()));
  }
  function count(prompt) {
    const nodes=spec.messages.flatMap(s=>[...document.querySelectorAll(s)]);
    return [...new Set(nodes)].filter(e=>normalized(e.innerText)===normalized(prompt)).length;
  }
  function fill(editor,prompt) {
    editor.focus();
    if(editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement) {
      const proto=editor instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,"value").set.call(editor,prompt);
      editor.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:prompt}));
      return;
    }
    const selection=getSelection(), range=document.createRange();
    range.selectNodeContents(editor);selection.removeAllRanges();selection.addRange(range);
    const lines=prompt.replace(/\r\n/g,"\n").split("\n");
    document.execCommand("delete",false);
    if(lines[0]) document.execCommand("insertText",false,lines[0]);
    for(const line of lines.slice(1)) {
      document.execCommand("insertLineBreak",false);
      if(line) document.execCommand("insertText",false,line);
    }
  }
  async function send(prompt,id) {
    if(seen.has(id) && seen.get(id).state!=="failed") return seen.get(id);
    if(busy) return {state:"failed",message:"현재 질문 전송이 끝날 때까지 기다려 주세요."};
    busy=true;
    let clicked=false,result;
    try {
      if(typeof prompt!=="string" || !prompt.trim() || prompt.length>100000) throw Error("질문 내용을 확인해 주세요.");
      const ready=status();
      if(ready.state!=="ready") throw Error(ready.message);
      const editor=find(spec.editors);
      if(read(editor).trim() && exact(read(editor))!==exact(prompt)) throw Error("서비스 입력창에 작성 중인 글이 있습니다. 먼저 정리해 주세요.");
      const before=count(prompt);
      fill(editor,prompt);
      await sleep(150);
      if(exact(read(editor))!==exact(prompt)) throw Error("질문 입력을 정확히 확인하지 못했습니다. 서비스 화면을 확인하세요.");
      let button;
      for(let i=0;i<25;i++) {
        button=sendButton();
        if(button && !button.disabled && button.getAttribute("aria-disabled")!=="true") break;
        await sleep(150);
      }
      if(!button || button.disabled || button.getAttribute("aria-disabled")==="true") throw Error("전송 버튼이 준비되지 않았습니다.");
      // Refuse hidden/covered buttons: do not click through login/cookie dialogs.
      const box=button.getBoundingClientRect(), hit=document.elementFromPoint(box.x+box.width/2,box.y+box.height/2);
      if(!hit || !button.contains(hit)) throw Error("로그인 또는 안내 창을 먼저 닫아 주세요.");
      clicked=true;
      seen.set(id,{state:"unknown",message:"전송 여부 확인 필요"});
      button.click();
      for(let i=0;i<40;i++) {
        const current=find(spec.editors);
        if(count(prompt)>before || (current && !read(current).trim() && find(spec.stop))) {
          result={state:"success",message:"전송 확인됨 · 서비스 화면에서 답변 확인"};
          break;
        }
        await sleep(250);
      }
      result ||= {state:"unknown",message:"전송 여부 확인 필요 · 중복 방지를 위해 재시도를 잠갔습니다."};
    } catch(error) {
      result=clicked ? {state:"unknown",message:"전송 여부를 서비스 화면에서 확인해 주세요."} : {state:"failed",message:error.message||"입력 준비에 실패했습니다."};
    } finally {busy=false;}
    seen.set(id,result);
    return result;
  }
  chrome.runtime.onMessage.addListener((m,sender,respond)=>{
    if(sender.id!==chrome.runtime.id || m?.type!=="dualai-site") return;
    if(m.command==="status") {respond(status());return;}
    if(m.command==="send") {send(m.prompt,m.requestId).then(respond);return true;}
  });
})();

export const SERVICES = {
  chatgpt:{name:"ChatGPT",url:"https://chatgpt.com/"},
  gemini:{name:"Gemini",url:"https://gemini.google.com/app"}
};
export function validate(command, payload={}) {
  if (!["ping","status","open","arrange","send","newChat"].includes(command)) throw new Error("지원하지 않는 작업입니다.");
  if (["send","newChat"].includes(command)) {
    if (!Array.isArray(payload.services) || !payload.services.length || payload.services.some(k=>!Object.hasOwn(SERVICES,k)) || new Set(payload.services).size !== payload.services.length) throw new Error("서비스 선택을 확인하세요.");
  }
  if (command === "send") {
    if (typeof payload.prompt !== "string" || !payload.prompt.trim() || payload.prompt.length > 100000) throw new Error("질문은 1~100,000자까지 입력할 수 있습니다.");
    if (typeof payload.requestId !== "string" || !/^[a-zA-Z0-9-]{8,100}$/.test(payload.requestId)) throw new Error("질문 식별자가 올바르지 않습니다.");
    if (payload.attachments !== undefined) {
      if (!Array.isArray(payload.attachments) || payload.attachments.length > 10) throw new Error("파일은 한 번에 최대 10개까지 첨부할 수 있습니다.");
      let total = 0;
      for (const file of payload.attachments) {
        if (!file || typeof file.name !== "string" || file.name.length > 255 || typeof file.type !== "string" || typeof file.data !== "string") throw new Error("첨부 파일을 읽지 못했습니다.");
        total += Math.floor(file.data.length * 3 / 4);
      }
      if (total > 15 * 1024 * 1024) throw new Error("첨부 파일 전체 크기는 15MB 이하여야 합니다.");
    }
  }
  return payload;
}
export function bounds(payload) {
  const s=payload.screen || {};
  const finite=(v,fallback)=>Number.isFinite(v)?Math.round(v):fallback;
  const x=finite(s.left,0), y=finite(s.top,0);
  const width=Math.max(800,Math.min(10000,finite(s.width,1400)));
  const height=Math.max(600,Math.min(10000,finite(s.height,900)));
  const ratio=Math.max(.3,Math.min(.7,Number(payload.ratio)||.5));
  const top=Math.min(350,Math.round(height*.42)), left=Math.round(width*ratio);
  return {controller:{left:x,top:y,width,height:top},
    chatgpt:{left:x,top:y+top,width:left,height:height-top},
    gemini:{left:x+left,top:y+top,width:width-left,height:height-top}};
}

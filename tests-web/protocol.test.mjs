import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {validate,bounds} from "../extension/protocol.js";
test("rejects unsupported commands and services",()=>{
 assert.throws(()=>validate("execute",{code:"arbitrary"}));
 assert.throws(()=>validate("send",{services:["constructor"],prompt:"hello",requestId:"request-123"}));
 assert.throws(()=>validate("send",{services:["other"],prompt:"hello",requestId:"request-123"}));
 assert.throws(()=>validate("send",{services:["chatgpt","chatgpt"],prompt:"hello",requestId:"request-123"}));
});
test("accepts long multilingual prompt without alteration",()=>{
 const prompt='한글\n\nEnglish <code> & "quote"\n    indent 🧪'.repeat(1000);
 assert.equal(validate("send",{services:["chatgpt","gemini"],prompt,requestId:"request-123"}).prompt,prompt);
 assert.throws(()=>validate("send",{services:["chatgpt"],prompt:"x".repeat(100001),requestId:"request-123"}));
});
test("layout respects negative monitor coordinates and bounded ratio",()=>{
 const r=bounds({screen:{left:-1920,top:0,width:1920,height:1080},ratio:.5});
 assert.equal(r.chatgpt.left,-1920);assert.equal(r.gemini.left,-960);
 assert.equal(r.chatgpt.width+r.gemini.width,1920);
 assert.equal(r.controller.height+r.chatgpt.height,1080);
 assert.equal(bounds({ratio:99}).chatgpt.width,980);
});
test("Vercel explicitly overrides erroneous Python preset",async()=>{
 const config=JSON.parse((await readFile("vercel.json","utf8")).replace(/^\uFEFF/,""));
 assert.equal(config.framework,null);assert.equal(config.installCommand,"");assert.equal(config.outputDirectory,"web-dist");
});
test("extension has no blanket installed access or cookies/debugger permissions",async()=>{
 const m=JSON.parse((await readFile("extension/manifest.json","utf8")).replace(/^\uFEFF/,""));
 assert.deepEqual(m.host_permissions,["https://chatgpt.com/*","https://gemini.google.com/*"]);
 assert.ok(!m.permissions.includes("cookies"));assert.ok(!m.permissions.includes("debugger"));
 assert.ok(!m.externally_connectable);
 assert.equal(m.version,"0.2.1");
});

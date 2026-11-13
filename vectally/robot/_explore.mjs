import path from 'node:path';import {createRequire} from 'node:module';
const gateway='D:/Codex/cusbe-remote-mcp';const require=createRequire(path.join(gateway,'package.json'));
const {Client}=require('@modelcontextprotocol/client');const {StdioClientTransport,getDefaultEnvironment}=require('@modelcontextprotocol/client/stdio');
const t=new StdioClientTransport({command:process.execPath,args:[path.join(gateway,'dist/gateway.js')],cwd:gateway,env:getDefaultEnvironment(),stderr:'pipe'});
const c=new Client({name:'explore',version:'0'});const T0=Date.now();try{await c.connect(t,{timeout:240000});}catch(e){console.log('CONNECT_FAIL',Date.now()-T0,e.message);process.exit(1);}console.log('connected',Date.now()-T0);
const tool=async(n,a)=>{console.log('call',n,Date.now()-T0);const r=await c.callTool({name:n,arguments:a},undefined,{timeout:120000});const x=(r.content||[]).map(x=>x.text||'').join('\n');if(r.isError)throw new Error(x.slice(0,400));return x;};
const ev=async(code,title)=>{const raw=await tool('browser__browser_evaluate',{function:`async (...a)=>JSON.stringify(await (${code})(...a))`,...(title?{target:`iframe[title="${title}"] >> internal:control=enter-frame >> body`}:{})});const m=raw.match(/### Result\n([\s\S]*?)(?=\n###|$)/);const r=JSON.parse(m[1]);return typeof r==='string'?JSON.parse(r):r;};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
await tool('browser__browser_resize',{width:1500,height:1000});
await tool('browser__browser_navigate',{url:'https://www.canva.com/design/DAHaxB2U5e4/rfCmsb4QrPmnc0x4GP7w9g/edit'});
for(let i=0;i<60;i++){try{if(await ev("() => document.querySelectorAll('[role=\"tab\"]').length>5"))break;}catch{}await sleep(1000);}
await ev("() => {const t=Array.from(document.querySelectorAll('[role=\"tab\"]')).find(t=>t.textContent==='TypeCraft');t.click();return true}");
for(let i=0;i<40;i++){try{if(await ev("e=>!!e.querySelector('textarea')", 'TypeCraft'))break;}catch{}await sleep(1000);}
console.log('BEFORE',JSON.stringify(await ev("e=>Array.from(e.querySelectorAll('button')).map(b=>(b.textContent||'')+'|'+(b.getAttribute('aria-label')||'')).slice(0,40)",'TypeCraft')));
const dumpOutline=(e)=>{const el=Array.from(e.querySelectorAll('*')).find(x=>x.textContent==='Efek garis tepi'&&x.children.length===0);if(!el)return 'none';let n=el;for(let k=0;k<3;k++)n=n.parentElement;return n.outerHTML.replace(/class="[^"]*"/g,'').replace(/<svg[\s\S]*?<\/svg>/g,'<svg/>').slice(0,2500);};
for(const k of [1]){
 const clickOpt=new Function('e','k',"const el=Array.from(e.querySelectorAll('*')).find(x=>x.textContent==='Efek garis tepi'&&x.children.length===0);let n=el;for(let i=0;i<3;i++)n=n.parentElement;const bs=n.querySelectorAll('button[data-selected]');bs[k].click();return bs.length");
 await ev(`e=>(${clickOpt.toString()})(e,${k})`,'TypeCraft');await sleep(1500);
 const dumpCtl=(e)=>{const el=Array.from(e.querySelectorAll('*')).find(x=>x.textContent==='Efek garis tepi'&&x.children.length===0);let n=el;for(let i=0;i<3;i++)n=n.parentElement;const box=e;return {texts:Array.from(box.querySelectorAll('p,label,span')).map(x=>x.textContent).filter(t=>t&&t.length<40),inputs:Array.from(box.querySelectorAll('input')).map(i=>[i.type,i.value,i.min,i.max,i.step,i.getAttribute('aria-label')]),buttons:Array.from(box.querySelectorAll('button')).map(b=>b.getAttribute('aria-label')).filter(Boolean)};};
 console.log('OPT',k,JSON.stringify(await ev(dumpCtl.toString(),'TypeCraft')));
}
await tool('browser__browser_press_key',{key:'Escape'});
await c.close();

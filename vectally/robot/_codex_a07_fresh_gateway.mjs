import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import crypto from 'node:crypto';
import {setMesh} from './typecraft_ui_geometry.mjs';
const gateway=process.env.CUSBE_GATEWAY_ROOT||'D:/Codex/cusbe-remote-mcp';
const require=createRequire(path.join(gateway,'package.json'));
const {Client}=require('@modelcontextprotocol/client');
const {StdioClientTransport,getDefaultEnvironment}=require('@modelcontextprotocol/client/stdio');
const root=path.resolve('outputs/VECTALLY_A07_FROM_BLANK');
const job=JSON.parse(await fs.readFile(path.join(root,'A07_FRESH_JOB.json'),'utf8'));
const dir=path.join(root,'runs',new Date().toISOString().replace(/[:.]/g,'-'));
await fs.mkdir(dir,{recursive:true});
const client=new Client({name:'a07-fresh-cusbe-gateway',version:'0.1.0'});
// Use the complete gateway, including its policy checks and allowlisted upload paths.
const transport=new StdioClientTransport({command:process.execPath,args:[path.join(gateway,'dist/gateway.js')],cwd:gateway,env:getDefaultEnvironment(),stderr:'pipe'});
transport.stderr?.on('data',()=>{});
const events=[];
const full=process.argv.includes('--full');
let info;
async function tool(name,args){
 const started=Date.now();const r=await client.callTool({name,arguments:args},undefined,{timeout:120000});
 events.push({name,ms:Date.now()-started,error:!!r.isError});
 await fs.writeFile(path.join(dir,'TOOL_EVENTS.json'),JSON.stringify(events,null,2));
 const text=(r.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');
 if(r.isError)throw new Error(text.replace(/https?:\/\/\S+/g,'[URL]').slice(0,1500));
 return text;
}
async function evaluate(code,title){
 const raw=await tool('browser__browser_evaluate',{function:`async (...args) => JSON.stringify(await (${code})(...args))`,...(title?{target:`iframe[title="${title}"] >> internal:control=enter-frame >> body`}:{})});
 const m=raw.match(/### Result\n([\s\S]*?)(?=\n###|$)/);if(!m)throw new Error('Missing browser result');
 const r=JSON.parse(m[1]);return typeof r==='string'?JSON.parse(r):r;
}
async function wait(code,title,timeout=30000){
 const end=Date.now()+timeout;let error;
 while(Date.now()<end){try{const r=await evaluate(code,title);if(r)return r;}catch(e){error=e.message;}await new Promise(r=>setTimeout(r,400));}
 throw new Error('UI not ready'+(error?': '+error:''));
}
async function openImporter(){
 await wait("() => Array.from(document.querySelectorAll('[role=\"tab\"]')).some(t=>t.textContent==='cusbe-importer')");
 await evaluate("() => {const t=Array.from(document.querySelectorAll('[role=\"tab\"]')).find(t=>t.textContent==='cusbe-importer');if(t.getAttribute('aria-selected')!=='true')t.click();return true}");
 await wait("e => !!e.querySelector('[role=\"region\"][aria-label=\"Unggah paket desain\"]')",'cusbe-importer');
}
async function inspect(name){
 await openImporter();
 const old=await evaluate("async e => {const a=e.querySelector('a[download=\"CUSBE_CANVA_INSPECTION.json\"]');return a?(await(await fetch(a.href)).json()).observedAt:null}",'cusbe-importer');
 await evaluate("e => {Array.from(e.querySelectorAll('button')).find(b=>b.textContent==='Inspeksi halaman saat ini').click();return true}",'cusbe-importer');
 const meta=await wait(`async e => {const a=e.querySelector('a[download="CUSBE_CANVA_INSPECTION.json"]');if(!a)return false;const raw=await(await fetch(a.href)).text();const r=JSON.parse(raw);return r.observedAt!==${JSON.stringify(old)}?{observedAt:r.observedAt,length:raw.length}:false}`,'cusbe-importer');
 const parts=[];
 // Page the visible inspection download to stay within normal gateway output limits.
 for(let offset=0;offset<meta.length;offset+=2000){
  parts.push(await evaluate(`async e => {const a=e.querySelector('a[download="CUSBE_CANVA_INSPECTION.json"]');const raw=await(await fetch(a.href)).text();return raw.slice(${offset},${offset+2000})}`,'cusbe-importer'));
 }
 const report=JSON.parse(parts.join(''));
 if(report.observedAt!==meta.observedAt)throw new Error('Inspection changed during reading');
 await fs.writeFile(path.join(dir,name+'.json'),JSON.stringify(report,null,2));return report;
}
async function typecraft(){
 await evaluate("() => {const t=Array.from(document.querySelectorAll('[role=\"tab\"]')).find(t=>t.textContent==='TypeCraft');if(!t)throw new Error('TypeCraft unavailable');if(t.getAttribute('aria-selected')!=='true')t.click();return true}");
 await wait("() => !!document.querySelector('iframe[title=\"TypeCraft\"]')");
}
async function buildWarp(){
 await typecraft();
 const initial=await wait("e => {const t=e.querySelector('textarea#multi-line-text-input');return t?{text:t.value,buttons:Array.from(e.querySelectorAll('button')).map(b=>b.textContent)}:false}",'TypeCraft');
 await fs.writeFile(path.join(dir,'NEW_TYPECRAFT_INITIAL.json'),JSON.stringify(initial,null,2));
 await evaluate("e => {const b=Array.from(e.querySelectorAll('button')).find(b=>b.textContent==='New Amsterdam'||b.textContent.includes('League Gothic'));if(!b)throw new Error('Font picker not ready');b.click();return true}",'TypeCraft');
 await wait("e => !!e.querySelector('img[alt=\"League Gothic Condensed Regular\"]')",'TypeCraft');
 await evaluate("e => {e.querySelector('img[alt=\"League Gothic Condensed Regular\"]').click();return true}",'TypeCraft');
 await tool('browser__browser_type',{target:'iframe[title="TypeCraft"] >> internal:control=enter-frame >> textarea#multi-line-text-input',text:'TIMING',slowly:false});
 await wait("e => e.querySelector('textarea#multi-line-text-input')?.value==='TIMING'&&Array.from(e.querySelectorAll('button')).some(b=>b.textContent==='League Gothic Condensed Regular')",'TypeCraft');
 if(!await evaluate("e => !!e.querySelector('button[aria-label=\"#091522\"]')",'TypeCraft')){
  await evaluate("e => {const b=Array.from(e.querySelectorAll('button')).find(b=>/^#[0-9a-fA-F]{6}$/.test(b.getAttribute('aria-label')||''));if(!b)throw new Error('Fill control absent');b.click();return true}",'TypeCraft');
  await wait("() => !!document.querySelector('button[aria-label=\"#091522\"]')");
  await evaluate("() => {document.querySelector('button[aria-label=\"#091522\"]').click();return true}");
  await tool('browser__browser_press_key',{key:'Escape'});
 }
 await wait("e => !!e.querySelector('button[aria-label=\"#091522\"]')",'TypeCraft');
 await evaluate("e => {e.querySelector('button[aria-label=\"Distorsi kustom\"]').click();return true}",'TypeCraft');
 await wait("e => Array.from(e.querySelectorAll('button')).some(b=>b.textContent==='Atur ulang bentuk')",'TypeCraft');
 await evaluate("e => {Array.from(e.querySelectorAll('button')).find(b=>b.textContent==='Atur ulang bentuk').click();return true}",'TypeCraft');
 await new Promise(r=>setTimeout(r,1500));
 const mesh=await evaluate(`async e => (${setMesh.toString()})(e,${JSON.stringify(job.warpQuad)})`,'TypeCraft');
 await fs.writeFile(path.join(dir,'NEW_TYPECRAFT_MESH.json'),JSON.stringify(mesh,null,2));
 if(mesh.maxError>3)throw new Error('Visible warp handle positions do not match job');
 await evaluate("e => {const b=Array.from(e.querySelectorAll('button')).find(b=>b.textContent==='Tambahkan ke desain');if(!b||b.disabled)throw new Error('Not a new TypeCraft object');b.click();return true}",'TypeCraft');
 await wait("() => !!document.querySelector('main img[alt=\"Type Craft element\"]')");
 await wait("() => Array.from(document.querySelectorAll('main button')).some(b=>b.textContent==='Posisi')");
 await evaluate("() => {const b=Array.from(document.querySelectorAll('main button')).find(b=>b.textContent==='Posisi');if(b.getAttribute('aria-label')!=='Panel posisi terbuka')b.click();return true}");
 await wait("() => Array.from(document.querySelectorAll('[role=\"tab\"]')).some(t=>t.textContent==='AturAtur')");
 await evaluate("() => {const t=Array.from(document.querySelectorAll('[role=\"tab\"]')).find(t=>t.textContent==='AturAtur');if(t.getAttribute('aria-selected')!=='true')t.click();return true}");
 for(const [label,value] of Object.entries(job.warpBox)){
  const id=await wait(`() => Array.from(document.querySelectorAll('label[for]')).find(l=>l.textContent===${JSON.stringify(label)})?.htmlFor||false`);
  let filled=false;
  for(let attempt=0;attempt<2;attempt++){
   await evaluate(`() => {const i=document.getElementById(${JSON.stringify(id)});i.focus();i.select();return true}`);
   await new Promise(r=>setTimeout(r,300));
   await tool('browser__browser_type',{target:`input[id="${id}"]`,text:String(value),slowly:false});
   filled=await evaluate(`() => document.getElementById(${JSON.stringify(id)}).value===${JSON.stringify(String(value))}`);
   if(filled)break;
  }
  if(!filled)throw new Error('Position field did not replace old value: '+label);
  await tool('browser__browser_press_key',{key:'Enter'});
  await wait(`() => Math.abs(parseFloat(document.getElementById(${JSON.stringify(id)}).value)-${value})<0.1`);
 }
 await wait("() => !!document.querySelector('[aria-label=\"Semua perubahan disimpan\"]')");
 console.log('NEW_TYPECRAFT_CREATED_AND_POSITIONED');
}
async function verifyWarpEditable(){
 await tool('browser__browser_navigate',{url:job.url});
 await wait("() => !!document.querySelector('[role=\"button\"][aria-label=\"Titik awal kanvas\"]')");
 if(!await evaluate("() => Array.from(document.querySelectorAll('main button')).some(b=>b.textContent==='Posisi')")){
  await evaluate("() => {const e=document.querySelector('[role=\"button\"][aria-label=\"Titik awal kanvas\"]');e.click();e.focus();return true}");
  await tool('browser__browser_press_key',{key:'Enter'});
 }
 await wait("() => Array.from(document.querySelectorAll('main button')).some(b=>b.textContent==='Posisi')");
 await evaluate("() => {const b=Array.from(document.querySelectorAll('main button')).find(b=>b.textContent==='Posisi');if(b.getAttribute('aria-label')!=='Panel posisi terbuka')b.click();return true}");
 await wait("() => Array.from(document.querySelectorAll('[role=\"tab\"]')).some(t=>t.textContent==='LapisanLapisan')");
 await evaluate("() => {const t=Array.from(document.querySelectorAll('[role=\"tab\"]')).find(t=>t.textContent==='LapisanLapisan');if(t.getAttribute('aria-selected')!=='true')t.click();return true}");
 await wait("() => !!document.querySelector('button[aria-label=\"Kelompokkan\"]')");
 await evaluate("() => {document.querySelector('button[aria-label=\"Kelompokkan\"]').click();return true}");
 await wait("() => !!document.querySelector('main button[aria-label=\"Edit\"]')");
 await evaluate("() => {document.querySelector('main button[aria-label=\"Edit\"]').click();return true}");
 await typecraft();
 return await wait("e => {const t=e.querySelector('textarea#multi-line-text-input');return t?.value==='TIMING'&&Array.from(e.querySelectorAll('button')).some(b=>b.textContent==='Perbarui elemen')?{text:t.value,updateAvailable:true}:false}",'TypeCraft');
}
async function exportPng(){
 await evaluate("() => {Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Bagikan').click();return true}");
 await wait("() => !!document.querySelector('button[aria-label=\"Unduh\"]')");
 await evaluate("() => {document.querySelector('button[aria-label=\"Unduh\"]').click();return true}");
 await wait("() => document.querySelector('button[aria-label=\"Jenis file\"]')?.textContent.includes('PNG')");
 const size=await evaluate("() => {const t=document.body.innerText,i=t.indexOf('Jenis file');return t.slice(i,i+500)}");
 if(!/1[,.]?122\s*×\s*1[,.]?402/.test(size))throw new Error('PNG export dimensions are not the source dimensions');
 const began=Date.now();
 await evaluate("() => {const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Unduh'&&!b.getAttribute('aria-label'));if(!b||b.disabled)throw new Error('PNG download not ready');b.click();return true}");
 const deadline=Date.now()+90000;let file;
 while(Date.now()<deadline){
  const names=await fs.readdir(job.downloadDirectory);
  for(const name of names.filter(n=>n.startsWith(job.designTitle)&&n.toLowerCase().endsWith('.png'))){const p=path.join(job.downloadDirectory,name),s=await fs.stat(p);if(s.mtimeMs>=began-1000){const b=await fs.readFile(p);if(b.length>24&&b.subarray(b.length-8,b.length-4).toString()==='IEND'){file={path:p,bytes:b};break;}}}
  if(file)break;await new Promise(r=>setTimeout(r,500));
 }
 if(!file)throw new Error('No completed PNG download found');
 if(file.bytes.readUInt32BE(16)!==1122||file.bytes.readUInt32BE(20)!==1402)throw new Error('Downloaded PNG dimensions differ');
 await fs.writeFile(path.join(dir,'CANVA_EXPORT.png'),file.bytes);
 return {file:'CANVA_EXPORT.png',width:1122,height:1402,sha256:crypto.createHash('sha256').update(file.bytes).digest('hex')};
}
try{
 await client.connect(transport);
 const names=(await client.listTools()).tools.map(t=>t.name);
 if(!names.includes('browser__browser_drop'))throw new Error('Gateway does not expose the official file-drop action');
 const creating=full||process.argv.includes('--create-fresh');
 await tool('browser__browser_navigate',{url:creating?job.createUrl:job.url});
 await wait("() => document.querySelectorAll('[role=\"tab\"]').length>5");
 info=await evaluate("() => ({url:location.href,title:document.title,pages:Array.from(document.querySelectorAll('[role=\"button\"][aria-label^=\"Halaman \"]')).map(e=>e.getAttribute('aria-label'))})");
 if(creating){
  const id=info.url.match(/\/design\/([^/]+)\//)?.[1];
  if(!id||['DAHasOPhPpw','DAHaabeSID4','DAHaawX9Fm8','DAHatoZUVbE'].includes(id))throw new Error('Creation did not produce a new design');
  job.url=info.url;job.designId=id;job.designTitle='VECTALLY A07 FRESH AUTO '+new Date().toISOString().replace(/[^0-9]/g,'').slice(0,14);
  await tool('browser__browser_type',{target:'input[aria-label="Judul desain"]',text:job.designTitle,slowly:false,submit:true});
 }
 if(!info.url.includes('/'+job.designId+'/')||info.pages.length!==1)throw new Error('Unexpected target design or page collection');
 const audit=process.argv.includes('--audit-only');
 const before=await inspect(audit?'CURRENT_NATIVE_BASE':'BEFORE_EMPTY');
 if(audit){
  await fs.writeFile(path.join(dir,'AUDIT_RESULT.json'),JSON.stringify({job,breakdown:before.breakdown,rootCount:before.elements.length,completeDesign:false},null,2));
  console.log('AUDIT',JSON.stringify(before.breakdown));
  await client.close();process.exit(0);
 }
 if(before.elements.length!==0)throw new Error('Refuse to assemble onto a nonempty page');
 console.log('VERIFIED blank page through complete CUSBE gateway');
 const bytes=await fs.readFile(job.packageFile);
 if(crypto.createHash('sha256').update(bytes).digest('hex')!==job.packageSha256)throw new Error('Package changed since preparation');
 await tool('browser__browser_drop',{target:'iframe[title="cusbe-importer"] >> internal:control=enter-frame >> [role="region"][aria-label="Unggah paket desain"]',paths:[job.packageFile]});
 await wait("e => Array.from(e.querySelectorAll('button')).some(b=>b.textContent==='Susun di halaman yang sedang dibuka'&&!b.disabled)",'cusbe-importer');
 console.log('VERIFIED package staged by official drag and drop');
 if(full||process.argv.includes('--assemble')){
  await evaluate("e => {Array.from(e.querySelectorAll('button')).find(b=>b.textContent==='Susun di halaman yang sedang dibuka').click();return true}",'cusbe-importer');
  const log=await wait("e => {const p=Array.from(e.querySelectorAll('p')).map(p=>p.textContent);return p.some(t=>t.startsWith('Selesai:'))?p:false}",'cusbe-importer',90000);
  await fs.writeFile(path.join(dir,'IMPORT_LOG.json'),JSON.stringify(log,null,2));
  if(log.some(t=>t.includes('GAGAL')||t.includes('Impor dihentikan')||t.includes('Error:')))throw new Error('Importer reported a rejected element or font');
  const after=await inspect('AFTER_NATIVE_BASE');
  if(Object.entries(job.expectedBase).some(([k,v])=>after.breakdown[k]!==v)||after.elements.some(e=>e.classification==='manual_review_required'))throw new Error('Native asset inventory differs from prepared package');
  const result={job,info,stage:'NATIVE_BASE_ASSEMBLED_FROM_EMPTY',beforeCount:before.elements.length,after:after.breakdown,completeDesign:false,pending:['New TypeCraft TIMING object','Actual Canva export and source comparison','Full buyer edit/recovery test']};
  await fs.writeFile(path.join(dir,'RESULT.json'),JSON.stringify(result,null,2));console.log('NATIVE_BASE_PASS',JSON.stringify(after.breakdown));
  if(full){
   await buildWarp();
   const editable=await verifyWarpEditable();
   const final=await inspect('FINAL_INSPECTION');
   if(Object.entries({...job.expectedBase,manual_review_required:1}).some(([k,v])=>final.breakdown[k]!==v))throw new Error('Final native/app inventory differs');
   const appElement=final.elements.find(e=>e.classification==='manual_review_required'),box=appElement?.bboxInParent;
   if(!box||Math.abs(box[0]-539)>0.2||Math.abs(box[1]-934)>0.2||Math.abs(box[2]-519)>0.2||box[3]<270||box[3]>345)throw new Error('TypeCraft position/size differs from job');
   const png=await exportPng();
   const output={job,completedAt:new Date().toISOString(),stage:'FULL_CONSTRUCTION_EXPORTED_NOT_YET_FIDELITY_PASSED',emptyBefore:true,inventory:final.breakdown,editable,appBox:box,export:png,fidelity:'NOT_TESTED',allDesignsSupported:false,runtimeUsesAI:false};
   await fs.writeFile(path.join(dir,'FULL_RESULT.json'),JSON.stringify(output,null,2));
   console.log('FULL_CONSTRUCTION_PASS_FIDELITY_PENDING',job.url);
  }
 }
}catch(e){await fs.writeFile(path.join(dir,'FAILED.json'),JSON.stringify({error:e.message},null,2));console.error('FRESH_STAGE_FAILED',e.message);process.exitCode=1;}
finally{console.log('EVIDENCE',dir);await client.close().catch(()=>{});}

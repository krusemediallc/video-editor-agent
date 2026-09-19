import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,existsSync,rmSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {buildCanvas} from '../scripts/build-canvas.mjs';
import {readNotes} from '../scripts/read-notes.mjs';
import {framePin,replayReviews,revisionExport,createLocalStore,createRemoteStore} from '../assets/review-model.mjs';

const comment = {id:'note-1',createdAt:'2026-09-18T10:00:00Z',data:{version:'v1',t:1.0333333333333334,text:'Fix <this> & "that"',author:'Reviewer'}};
const event = (id,kind,data={},at='2026-09-18T10:01:00Z') => ({id,createdAt:at,data:{commentId:'note-1',kind,author:'Editor',...data}});
function tmp(t){const dir=mkdtempSync(path.join(os.tmpdir(),'review-test-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));return dir;}
const metadata={duration:5,fps:30,fpsNumerator:30,fpsDenominator:1,width:1080,height:1920};
function build(t,cfg){const dir=tmp(t);for(const f of ['v1.mp4','v2.mp4','master.mp4'])writeFileSync(path.join(dir,f),'stub-media');writeFileSync(path.join(dir,'config.json'),JSON.stringify(cfg));return {dir,...buildCanvas(path.join(dir,'config.json'),{probe:()=>metadata})};}

test('exact frame pins preserve the frame chosen instead of rounding to tenths',()=>{
  assert.deepEqual(framePin(31/30,30),{frame:31,t:31/30,fps:30});
  assert.equal(framePin(12/(30000/1001),30000/1001).frame,12);
  assert.equal(framePin(100,30,5).frame,149);
  assert.equal(framePin(-1,30).frame,0);
});

test('legacy comments default open; ordered events resolve/reopen and retain replies/evidence',()=>{
  const evidence=event('evidence','evidence',{text:'Fixed',beforeVersion:'v1',beforeT:1,afterVersion:'v2',afterT:.5});
  const close=event('close','status',{status:'resolved'}), reopen=event('reopen','status',{status:'open'},'2026-09-18T10:02:00Z');
  const reply=event('reply','reply',{text:'Keep <b> literally'});
  const [note]=replayReviews([comment],[reopen,close,reply,evidence,reply,event('orphan','reply',{commentId:'missing',text:'Ignore'})]);
  assert.equal(note.status,'open');assert.equal(note.replies.length,1);assert.equal(note.replies[0].text,'Keep <b> literally');
  assert.equal(note.evidence[0].afterVersion,'v2');assert.equal(note.history.length,4);
  assert.equal(replayReviews([comment],[])[0].status,'open');
});

test('status is keyed by stable comment ID, never timestamp/version/list position',()=>{
  const notes=replayReviews([comment,{...comment,id:'note-2'}],[event('close','status',{status:'resolved'})]);
  assert.equal(notes.find(n=>n.id==='note-1').status,'resolved');assert.equal(notes.find(n=>n.id==='note-2').status,'open');
});

test('local adapter persists across instances and does not reseed or duplicate a retry',async()=>{
  const disk=new Map(),storage={getItem:k=>disk.get(k)??null,setItem:(k,v)=>disk.set(k,v)};
  const first=createLocalStore(storage,'demo',{comments:[comment]});
  await first.append('events',{commentId:'note-1',kind:'status',status:'resolved'},'same-request');
  await first.append('events',{commentId:'note-1',kind:'status',status:'resolved'},'same-request');
  const second=createLocalStore(storage,'demo',{comments:[]});const state=await second.read();
  assert.equal(state.comments.length,1);assert.equal(state.events.length,1);
  assert.equal(replayReviews(state.comments,state.events)[0].status,'resolved');
  storage.setItem('bad','broken');await assert.rejects(createLocalStore(storage,'bad').read());
});

test('remote adapter follows pagination and supports pre-v2 sites without events',async()=>{
  const calls=[];
  const fetcher=async(url,opts)=>{calls.push([url,opts]);
    if(url.includes('reviewEvents'))return {status:404,ok:false};
    return {ok:true,json:async()=>url.includes('cursor=next')?{records:[{...comment,id:'note-2'}]}:{records:[comment],nextCursor:'next'}};
  };
  const data=await createRemoteStore(fetcher).read();assert.equal(data.comments.length,2);assert.equal(data.events.length,0);
  assert.ok(calls.some(([url])=>url.includes('cursor=next')));
});

test('remote append uses an idempotency key and never credentials',async()=>{
  let captured;const store=createRemoteStore(async(url,options)=>{captured={url,options};return {ok:true,json:async()=>({id:'reply'})};});
  await store.append('events',{commentId:'note-1',kind:'reply',text:'Great'},'request-1');
  assert.equal(captured.options.headers['Idempotency-Key'],'request-1');assert.equal(captured.options.headers.Authorization,undefined);
  assert.ok(captured.url.endsWith('reviewEvents'));
});

test('old single-video configs preserve both existing download variants and bold notes',t=>{
  const {outDir,config}=build(t,{video:'v1.mp4',outDir:'review',title:'Old format',version:'v1',download:'master.mp4',downloadLabel:'Master',
    downloads:[{file:'v2.mp4',name:'clean.mp4',label:'Clean'}],notes:[{n:'Change',b:'Keep <b>bold</b>; remove <img src=x onerror=alert(1)>'}]});
  assert.equal(config.versions.length,1);assert.equal(config.storage.mode,'remote');assert.ok(existsSync(path.join(outDir,'master.mp4')));assert.ok(existsSync(path.join(outDir,'clean.mp4')));
  const html=readFileSync(path.join(outDir,'index.html'),'utf8');assert.ok(html.includes('id="downloadbtn"'));assert.ok(html.includes('<b>bold</b>'));assert.ok(!html.includes('<img src=x'));
});

test('multi-version output probes and copies both media; hostile strings cannot terminate config script',t=>{
  const dangerous='Quotes " & <script>alert(1)</script> {{TITLE}}';
  const {outDir,config}=build(t,{outDir:'review',title:dangerous,version:'v2',author:dangerous,storage:{mode:'local',key:'demo'},
    versions:[{version:'v1',video:'v1.mp4',label:dangerous,beats:[{t:1,n:dangerous}]},{version:'v2',video:'v2.mp4'}],reviewData:{comments:[comment],events:[]}});
  const html=readFileSync(path.join(outDir,'index.html'),'utf8');
  const embedded=html.match(/<script id="review-config" type="application\/json">([\s\S]*?)<\/script>/)[1];
  assert.equal(JSON.parse(embedded).title,dangerous);assert.ok(!embedded.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));
  for(const v of config.versions)assert.ok(existsSync(path.join(outDir,v.file)));
  assert.equal(config.version,'v2');assert.equal(config.versions[0].fps,30);
  assert.ok(existsSync(path.join(outDir,'review-model.mjs')));assert.ok(existsSync(path.join(outDir,'review-app.mjs')));
});

test('builder refuses duplicate versions, output traversal, and active-version mistakes',t=>{
  const cases=[{versions:[{version:'v1',video:'v1.mp4'},{version:'v1',video:'v2.mp4'}]},
    {video:'v1.mp4',download:'master.mp4',downloadName:'../escaped.mp4'},
    {version:'v3',versions:[{version:'v1',video:'v1.mp4'}]},
    {video:'v1.mp4',accents:['red;}</style><script>bad</script>','#fff','#000']}];
  for(const cfg of cases)assert.throws(()=>build(t,{outDir:'review',...cfg}));
});

test('machine export/readback retains original records, derived status, evidence and legacy CLI formatting',async t=>{
  const dir=tmp(t),file=path.join(dir,'review.json');
  const data={comments:[comment],events:[event('close','status',{status:'resolved'}),event('proof','evidence',{beforeVersion:'v1',beforeT:1,afterVersion:'v2',afterT:.5,text:'Fixed'})]};
  writeFileSync(file,JSON.stringify(revisionExport(data,{title:'Test'})));
  const result=JSON.parse(await readNotes(['--file',file,'v1','--json']));
  assert.equal(result.comments[0].id,'note-1');assert.equal(result.notes[0].status,'resolved');assert.equal(result.notes[0].evidence[0].afterT,.5);
  assert.match(await readNotes(['--file',file]),/RESOLVED/);
  assert.equal(JSON.parse(await readNotes(['--file',file,'v2','--json'])).notes.length,0);
});


test('all version hashes are preflighted before a rebuild writes anything',t=>{
  const cfg={outDir:'review',title:'Protected',version:'v2',versions:[{version:'v1',video:'v1.mp4'},{version:'v2',video:'v2.mp4'}]};
  const {dir,outDir,config}=build(t,cfg);
  const priorFiles=['index.html','review-config.json','review-app.mjs','review-model.mjs',...config.versions.map(v=>v.file)];
  const before=new Map(priorFiles.map(name=>[name,readFileSync(path.join(outDir,name))]));
  writeFileSync(path.join(dir,'v2.mp4'),'changed media');
  writeFileSync(path.join(dir,'config.json'),JSON.stringify({...cfg,author:'Changed author'}));
  assert.throws(()=>buildCanvas(path.join(dir,'config.json'),{probe:()=>metadata}),/Version v2 already contains different media/);
  for(const name of priorFiles)assert.deepEqual(readFileSync(path.join(outDir,name)),before.get(name));
});

test('identical bytes can be republished while page copy changes',t=>{
  const cfg={outDir:'review',title:'Protected',video:'v1.mp4',version:'v1'};
  const {dir,outDir,config}=build(t,cfg);
  writeFileSync(path.join(dir,'config.json'),JSON.stringify({...cfg,blurb:'Updated review instructions'}));
  const result=buildCanvas(path.join(dir,'config.json'),{probe:()=>metadata});
  assert.equal(result.config.versions[0].sha256,config.versions[0].sha256);
  assert.match(readFileSync(path.join(outDir,'index.html'),'utf8'),/Updated review instructions/);
});

test('version identity remains protected when title changes or source is inside output',t=>{
  const cfg={outDir:'review',title:'Protected',video:'v1.mp4',version:'v1'};
  const {dir,outDir,config}=build(t,cfg);
  const target=path.join(outDir,config.versions[0].file);
  writeFileSync(target,'media modified in place');
  writeFileSync(path.join(dir,'config.json'),JSON.stringify({...cfg,title:'A new title',video:target}));
  assert.throws(()=>buildCanvas(path.join(dir,'config.json'),{probe:()=>metadata}),/Version v1 already contains different media/);
  assert.ok(!existsSync(path.join(outDir,'a-new-title-v1.mp4')));
});


test('hidden version IDs and media cannot later be replaced through a renamed title or download alias',t=>{
  const cfg={outDir:'review',title:'Protected',video:'v1.mp4',version:'v1'};
  const {dir,config}=build(t,cfg),cfgPath=path.join(dir,'config.json');
  writeFileSync(cfgPath,JSON.stringify({...cfg,version:'v2',video:'v2.mp4'}));
  buildCanvas(cfgPath,{probe:()=>metadata});
  writeFileSync(path.join(dir,'v1.mp4'),'new incompatible version bytes');
  writeFileSync(cfgPath,JSON.stringify({...cfg,title:'Different title'}));
  assert.throws(()=>buildCanvas(cfgPath,{probe:()=>metadata}),/Version v1 already contains different media/);
  writeFileSync(cfgPath,JSON.stringify({...cfg,version:'v2',video:'v2.mp4',download:'v1.mp4',downloadName:config.versions[0].file}));
  assert.throws(()=>buildCanvas(cfgPath,{probe:()=>metadata}),/belongs to version v1/);
});

import {framePin, replayReviews, revisionExport, createLocalStore, createRemoteStore} from './review-model.mjs';

const config = JSON.parse(document.getElementById('review-config').textContent);
const $ = id => document.getElementById(id);
const video = $('vid'), compare = $('compare-video');
let active = config.versions.find(v => v.version === config.version), comparison = null;
let records = {comments:[],events:[]}, stamp = null, refreshSerial = 0;
const store = config.storage.mode === 'local'
  ? createLocalStore(localStorage, config.storage.key, config.reviewData)
  : createRemoteStore(fetch.bind(globalThis));
const error = message => {$('review-error').textContent = message || '';};
const author = () => $('review-author').value.trim() || config.author;
$('review-author').value = config.author;
$('storage-note').textContent = config.storage.mode === 'local'
  ? 'Local review: notes persist in this browser only. Export review JSON to back up or share with your editor.'
  : 'Shared review: notes, replies, evidence and status changes save to this page. Anyone with this review link can contribute.';

const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const button = (text, action, className='btn btn-sm') => {
  const node = el('button', text, className);
  node.type = 'button'; node.addEventListener('click', action); return node;
};
const fmt = time => `${Math.floor(time/60)}:${(time%60).toFixed(3).padStart(6,'0')}`;
const currentPin = () => framePin(video.currentTime, active.fps, active.duration);
const findVersion = version => config.versions.find(v => v.version === version);
function options(select, includeOff=false) {
  select.replaceChildren();
  if (includeOff) select.add(new Option('Off',''));
  for (const v of config.versions) select.add(new Option(v.label, v.version));
}
options($('version-picker')); options($('compare-picker'),true);
$('version-picker').value = active.version;

function syncCompare(force=false) {
  if (!comparison || compare.readyState < 1) return;
  const desired = video.currentTime + (Number($('compare-offset').value) || 0);
  const time = Math.max(0, Math.min(comparison.duration-1/comparison.fps,desired));
  if (force || Math.abs(compare.currentTime-time) > Math.max(.06,2/comparison.fps)) compare.currentTime = time;
  compare.playbackRate = video.playbackRate;
  if (!video.paused && desired >= 0 && desired < comparison.duration) {
    if (compare.paused) compare.play().catch(e => error(`Comparison playback: ${e.message}`));
  } else compare.pause();
}
function setComparison(id) {
  comparison = findVersion(id) || null;
  $('compare-picker').value = comparison?.version || '';
  $('compare-panel').hidden = !comparison;
  video.closest('.player').classList.toggle('comparing',Boolean(comparison));
  if (!comparison) {compare.pause(); compare.removeAttribute('src'); compare.load(); return;}
  $('compare-label').textContent = comparison.label + ' · muted';
  compare.src = comparison.file; compare.load();
}
function seek(version, t) {
  if (!findVersion(version)) {error(`Version ${version} is not included in this review.`); return;}
  video.pause();
  if (active.version !== version) selectVersion(version,t);
  else video.currentTime = framePin(t,active.fps,active.duration).t;
}
function selectVersion(id, time=0) {
  active = findVersion(id); video.pause();
  $('version-picker').value = id; $('version-label').textContent = active.label; $('primary-label').textContent = active.label;
  $('composer').classList.remove('open'); stamp=null;
  video.src = active.file;
  video.addEventListener('loadedmetadata', () => {video.currentTime=framePin(time,active.fps,active.duration).t;syncCompare(true);},{once:true});
  video.load(); renderBeats(); renderNotes();
}
$('version-picker').addEventListener('change', () => selectVersion($('version-picker').value));
$('compare-picker').addEventListener('change', () => setComparison($('compare-picker').value));
$('compare-offset').addEventListener('input', () => syncCompare(true));
compare.addEventListener('loadedmetadata', () => syncCompare(true));
for (const event of ['seeked','play','pause','ratechange','timeupdate','ended']) video.addEventListener(event, () => syncCompare(event==='seeked'));
video.addEventListener('error', () => error('This video could not load. Check that the served review directory includes its media.'));

function renderBeats() {
  $('beats').replaceChildren(); $('beatmarks').replaceChildren();
  for (const b of active.beats) {
    const node = button('',() => seek(active.version,b.t),'beat'); node.dataset.tone=b.tone;
    node.append(el('span',fmt(b.t),'bt'));
    const detail=el('span',undefined,'bd');detail.append(el('span',b.n,'bn'),el('span',b.s,'bs'));node.append(detail);
    $('beats').append(node);
    const mark=el('i');mark.style.left=`${b.t/active.duration*100}%`;$('beatmarks').append(mark);
  }
}
function tick() {
  const pin=currentPin(), fraction=Math.max(0,Math.min(1,video.currentTime/active.duration));
  $('played').style.width=`${fraction*100}%`;$('playhead').style.left=`${fraction*100}%`;
  $('tltime').textContent=`${fmt(pin.t)} · f${pin.frame} / ${fmt(active.duration)}`;
  let index=-1;active.beats.forEach((b,i)=>{if(video.currentTime>=b.t)index=i;});
  $('tllabel').textContent=active.beats[index]?.n || '';
  [...$('beats').children].forEach((node,i)=>node.classList.toggle('on',i===index));
  requestAnimationFrame(tick);
}
function togglePlay(){video.paused?video.play().catch(e=>error(e.message)):video.pause();}
$('playbtn').addEventListener('click',togglePlay);video.addEventListener('click',togglePlay);
video.addEventListener('play',()=>{$('playbtn').textContent='⏸ Pause';});
video.addEventListener('pause',()=>{$('playbtn').textContent='▶ Play';});
function step(frames){video.pause();const pin=currentPin();video.currentTime=framePin((pin.frame+frames)/active.fps,active.fps,active.duration).t;}
$('backbtn').addEventListener('click',()=>step(-1));$('fwdbtn').addEventListener('click',()=>step(1));
$('tl').addEventListener('click',event=>{
  if(event.target.closest('.pin'))return;
  const rect=$('tl').getBoundingClientRect();seek(active.version,(event.clientX-rect.left)/rect.width*active.duration);
});
function openComposer(){
  video.pause(); stamp={...currentPin(),version:active.version}; video.currentTime=stamp.t;
  $('stamp-t').textContent=`${fmt(stamp.t)} · f${stamp.frame} · ${active.label}`;
  $('composer').classList.add('open');$('ctext').focus();
}
$('commentbtn').addEventListener('click',openComposer);
$('cancelbtn').addEventListener('click',()=>{$('composer').classList.remove('open');$('ctext').value='';});
document.addEventListener('keydown',event=>{
  if(event.target.closest('input,textarea,select,button,summary,[contenteditable="true"]'))return;
  if(event.key==='c'||event.key==='C'){event.preventDefault();openComposer();}
  if(event.key===' '){event.preventDefault();togglePlay();}
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();step((event.key==='ArrowLeft'?-1:1)*(event.shiftKey?Math.round(active.fps):1));}
});
async function save(collection,data,node){
  if(node)node.disabled=true;error('');
  try{await store.append(collection,data);await refresh();return true;}
  catch(e){error(`Review was not saved: ${e.message}`);return false;}
  finally{if(node)node.disabled=false;}
}
$('sendbtn').addEventListener('click',async()=>{
  const text=$('ctext').value.trim();if(!text||!stamp)return;
  if(text.length>1000){error('Notes must be 1,000 characters or fewer.');return;}
  if(await save('comments',{...stamp,text,author:author()},$('sendbtn'))){$('ctext').value='';$('composer').classList.remove('open');}
});
function eventData(note,kind,data){return {commentId:note.id,kind,author:author(),...data};}
function comparisonEvidence(evidence){
  const before=findVersion(evidence.beforeVersion),after=findVersion(evidence.afterVersion);
  if(!before||!after){error('Both evidence versions must be included in this review to compare them.');return;}
  $('compare-offset').value=String((evidence.afterT||0)-(evidence.beforeT||0));
  setComparison(after.version);seek(before.version,evidence.beforeT||0);
}
function addEvidenceForm(body,note){
  const details=el('details'),summary=el('summary','Attach before / after evidence');details.append(summary);
  const form=el('div',undefined,'evidence-form');
  const beforeSelect=el('select'),afterSelect=el('select');options(beforeSelect);options(afterSelect);
  beforeSelect.value=findVersion(note.version)?note.version:active.version;afterSelect.value=active.version;
  const beforeFrame=el('input'),afterFrame=el('input');
  for(const input of [beforeFrame,afterFrame]){input.type='number';input.min='0';input.step='1';}
  beforeFrame.value=String(note.frame ?? framePin(note.t,findVersion(note.version)?.fps||active.fps).frame);
  afterFrame.value=String(currentPin().frame);
  const beforeLabel=el('label','Before version / frame');beforeLabel.append(beforeSelect,beforeFrame);
  const afterLabel=el('label','After version / frame');afterLabel.append(afterSelect,afterFrame);
  const text=el('textarea');text.placeholder='What changed, and what does this evidence show?';text.maxLength=1000;
  const submit=button('Save evidence',async()=>{
    const b=findVersion(beforeSelect.value),a=findVersion(afterSelect.value),bf=Number(beforeFrame.value),af=Number(afterFrame.value);
    if(!Number.isInteger(bf)||!Number.isInteger(af)||bf<0||af<0||bf>=Math.ceil(b.duration*b.fps)||af>=Math.ceil(a.duration*a.fps)){
      error('Evidence frames must be whole frame numbers within each selected version.');return;
    }
    await save('events',eventData(note,'evidence',{text:text.value.trim(),beforeVersion:b.version,beforeFrame:bf,beforeT:bf/b.fps,
      afterVersion:a.version,afterFrame:af,afterT:af/a.fps}),submit);
  });
  form.append(beforeLabel,afterLabel,text,submit);details.append(form);body.append(details);
}
function renderNotes(){
  const all=replayReviews(records.comments,records.events);
  const notes=all.filter(n=>($('status-filter').value==='all'||n.status===$('status-filter').value)&&
    ($('notes-version-filter').value==='all'||n.version===active.version));
  $('ccount').textContent=`${all.filter(n=>n.status==='open').length} open · ${all.filter(n=>n.status==='resolved').length} resolved`;
  $('clist').replaceChildren();$('tl').querySelectorAll('.pin').forEach(n=>n.remove());
  if(!notes.length)$('clist').append(el('div','No notes match these filters.','empty'));
  notes.forEach((note,index)=>{
    const row=el('div',undefined,`comment ${note.status}`);
    const frame=note.frame !== undefined?` · f${note.frame}`:'';
    row.append(button(`${note.version} · ${fmt(note.t)}${frame}`,()=>seek(note.version,note.t),'tchip'));
    const body=el('div',undefined,'comment-body');
    body.append(el('div',note.status==='resolved'?'Resolved':'Open','status'),el('div',note.text,'ctext'),el('div',`${note.author||'Reviewer'} · ${note.createdAt||''}`,'cmeta'));
    for(const reply of note.replies){const thread=el('div',undefined,'thread');thread.append(el('p',reply.text),el('span',reply.author||'Reviewer','cmeta'));body.append(thread);}
    for(const evidence of note.evidence){
      const block=el('div',undefined,'evidence');block.append(el('div',evidence.text||'Rendered evidence','ctext'),
        el('div',`${evidence.beforeVersion} f${evidence.beforeFrame??'?'} → ${evidence.afterVersion} f${evidence.afterFrame??'?'}`,'cmeta'),
        button('Compare this change',()=>comparisonEvidence(evidence)));body.append(block);
    }
    const actions=el('div',undefined,'note-actions');
    const status=button(note.status==='resolved'?'Reopen':'Mark resolved',()=>save('events',eventData(note,'status',{status:note.status==='resolved'?'open':'resolved'}),status));actions.append(status);body.append(actions);
    const replyForm=el('details',undefined,'reply-form');replyForm.append(el('summary','Reply'));
    const replyText=el('textarea');replyText.placeholder='Reply to this note';replyText.maxLength=1000;
    const replyButton=button('Save reply',()=>{if(replyText.value.trim())save('events',eventData(note,'reply',{text:replyText.value.trim()}),replyButton);});
    replyForm.append(replyText,replyButton);body.append(replyForm);addEvidenceForm(body,note);row.append(body);$('clist').append(row);
    if(note.version===active.version){
      const pin=button(String(index+1),()=>seek(note.version,note.t),`pin ${note.status}`);pin.style.left=`${note.t/active.duration*100}%`;pin.title=note.text;$('tl').append(pin);
    }
  });
}
for(const id of ['status-filter','notes-version-filter'])$(id).addEventListener('change',renderNotes);
async function refresh(){
  const serial=++refreshSerial;
  try{const data=await store.read();if(serial===refreshSerial){records=data;renderNotes();error('');}}
  catch(e){error(`Could not load review: ${e.message}. Existing notes have not been replaced.`);}
}
$('export-review').addEventListener('click',async()=>{
  try{
    const data=await store.read(),json=revisionExport(data,{title:config.title,versions:config.versions});
    const url=URL.createObjectURL(new Blob([JSON.stringify(json,null,2)+'\n'],{type:'application/json'}));
    const link=el('a');link.href=url;link.download='review-revisions.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){error(`Export failed: ${e.message}`);}
});
window.addEventListener('storage',event=>{if(event.key===config.storage.key)refresh();});
renderBeats();requestAnimationFrame(tick);refresh();
// Avoid discarding a reply/evidence draft while the reviewer is typing.
setInterval(()=>{if(!document.activeElement?.closest('input,textarea,select,details'))refresh();},30000);

#!/usr/bin/env node
/** Build a review directory. Existing single-video configs and download(s) remain supported. */
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, statSync, openSync, readSync, closeSync, realpathSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(HERE, '..', 'assets');
export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Historical editor notes permit <b>; no other tags or attributes are accepted.
const basicHTML = value => escapeHTML(value).replace(/&lt;(\/?)b&gt;/g, '<$1b>');
export const scriptJSON = value => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
const safeName = name => {
  if (!name || name !== path.basename(name) || /[\x00-\x1f\\]/.test(name) || name === '.' || name === '..') throw new Error('Download name must be a filename');
  return name;
};

function fileHash(file) {
  const hash = createHash('sha256'), buffer = Buffer.alloc(1024 * 1024), fd = openSync(file,'r');
  try {
    let count;
    while ((count=readSync(fd,buffer,0,buffer.length,null)) > 0) hash.update(buffer.subarray(0,count));
    return hash.digest('hex');
  } finally { closeSync(fd); }
}

export function buildCanvas(cfgPath, {probe: suppliedProbe} = {}) {
  const cfg = JSON.parse(readFileSync(cfgPath, 'utf8'));
  const cfgDir = path.dirname(path.resolve(cfgPath));
  const resolve = p => path.isAbsolute(p) ? p : path.resolve(cfgDir, p);
  if (!cfg.outDir) throw new Error('outDir is required');
  const outDir = resolve(cfg.outDir);
  const ffprobe = process.env.FFPROBE || ['/opt/homebrew/bin/ffprobe','/usr/local/bin/ffprobe'].find(existsSync) || 'ffprobe';
  const probe = suppliedProbe || (file => {
    const json = JSON.parse(execFileSync(ffprobe, ['-v','error','-select_streams','v:0','-show_entries',
      'format=duration:stream=r_frame_rate,avg_frame_rate,width,height','-of','json',file], {encoding:'utf8'}));
    const stream = json.streams[0], [num, den] = stream.r_frame_rate.split('/').map(Number);
    return {duration:Number(json.format.duration), fps:num/den, fpsNumerator:num, fpsDenominator:den,
      width:stream.width, height:stream.height, variableFrameRate:stream.avg_frame_rate !== stream.r_frame_rate};
  });
  const version = String(cfg.version || cfg.versions?.at(-1)?.version || 'v1');
  const inputs = cfg.versions?.length ? [...cfg.versions] : [{version, video:cfg.video, label:cfg.versionLabel, beats:cfg.beats}];
  if (!inputs.some(v => v.version === version) && cfg.video) inputs.push({version, video:cfg.video, label:cfg.versionLabel, beats:cfg.beats});
  const title = String(cfg.title || 'Cut');
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'') || 'cut';
  const seen = new Set(), copies = [];
  const versions = inputs.map(input => {
    const id = String(input.version || '');
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,19}$/.test(id) || seen.has(id)) throw new Error('Versions need unique, filename-safe IDs');
    seen.add(id);
    if (typeof input.video !== 'string') throw new Error(`Missing video for ${id}`);
    const source = resolve(input.video);
    if (!existsSync(source)) throw new Error(`Video not found: ${source}`);
    const meta = probe(source);
    if (!(meta.fps > 0 && Number.isFinite(meta.fps) && meta.duration > 0)) throw new Error(`Invalid video metadata for ${id}`);
    const file = `${slug}-${id}${path.extname(source)}`;
    copies.push({source, file});
    const beats = (input.beats || (id === version ? cfg.beats : []) || []).map(b => {
      if (!Number.isFinite(b.t) || b.t < 0 || b.t > meta.duration) throw new Error(`Invalid beat time for ${id}`);
      return {t:b.t,n:String(b.n || ''),s:String(b.s || ''),tone:b.tone || ''};
    }).sort((a,b) => a.t-b.t);
    return {version:id, label:String(input.label || id.toUpperCase()), file, ...meta, beats, sha256:fileHash(source)};
  });
  const active = versions.find(v => v.version === version);
  if (!active) throw new Error(`Active version ${version} is not listed`);
  const accents = cfg.accents || ['#4aa8ff','#a033ff','#ff5c87'];
  if (accents.length !== 3 || accents.some(c => !/^#[a-f\d]{3}([a-f\d]{3})?$/i.test(c))) throw new Error('accents must be three hex colors');
  const rgba = (hex, alpha) => {
    let h = hex.slice(1); if (h.length === 3) h = [...h].map(c => c+c).join('');
    const n = parseInt(h,16); return `rgba(${n>>16&255},${n>>8&255},${n&255},${alpha})`;
  };
  const playerWidth = cfg.playerWidth || 'min(52vh,430px)';
  if (!/^[a-z\d\s(),.%+*\/-]+$/i.test(playerWidth)) throw new Error('Invalid playerWidth');
  const downloadInputs = [...(cfg.download ? [{file:cfg.download,name:cfg.downloadName,label:cfg.downloadLabel}] : []), ...(cfg.downloads || [])];
  const occupied = new Set(['index.html','review-config.json','review-model.mjs','review-app.mjs',...copies.map(c => c.file)]);
  const downloads = downloadInputs.map((d, i) => {
    const source = resolve(d.file);
    if (!existsSync(source)) throw new Error(`Download not found: ${source}`);
    const file = safeName(d.name || path.basename(source));
    if (occupied.has(file)) {
      const existing = copies.find(c => c.file === file && c.source === source);
      if (!existing) throw new Error(`Output filename collision: ${file}`);
    } else { copies.push({source,file}); occupied.add(file); }
    const mb = Math.round(statSync(source).size/1048576);
    return `<a class="btn btn-sm" ${i===0?'id="downloadbtn"':''} href="${escapeHTML(encodeURIComponent(file))}" download>${escapeHTML(d.label || `↓ Download${mb?` (${mb} MB)`:''}`)}</a>`;
  }).join('\n');
  const storage = cfg.storage || {mode:'remote'};
  if (!['local','remote'].includes(storage.mode)) throw new Error('storage.mode must be local or remote');
  // Preflight every version before writing any page, receipt, module or media.
  // Retain receipts for hidden versions so their IDs cannot later mean new footage.
  const priorPath = path.join(outDir,'review-config.json');
  const priorConfig = existsSync(priorPath) ? JSON.parse(readFileSync(priorPath,'utf8')) : null;
  const versionReceipts = (priorConfig?.versionReceipts || priorConfig?.versions || []).map(prior => {
    let sha256=prior.sha256;
    if (!sha256 && prior.file && prior.file === path.basename(prior.file)) {
      const priorFile=path.join(outDir,prior.file);
      if (existsSync(priorFile)) sha256=fileHash(priorFile);
    }
    return {version:prior.version,file:prior.file,sha256};
  });
  for (const v of versions) {
    const prior = versionReceipts.find(old => old.version === v.version);
    const target = path.join(outDir,v.file);
    if ((prior?.sha256 && prior.sha256 !== v.sha256) || (existsSync(target) && fileHash(target) !== v.sha256)) {
      throw new Error(`Version ${v.version} already contains different media. Keep the delivered version and use a new version ID and file.`);
    }
    if (!prior) versionReceipts.push({version:v.version,file:v.file,sha256:v.sha256});
  }
  // A download alias must not overwrite a previously published version's media.
  for (const {source,file} of copies) {
    const protectedVersion=versionReceipts.find(prior => prior.file === file);
    if (protectedVersion?.sha256 && fileHash(source) !== protectedVersion.sha256) {
      throw new Error(`Output ${file} belongs to version ${protectedVersion.version}; choose a different download filename.`);
    }
  }
  const browserConfig = {schemaVersion:2,title,version,versions,versionReceipts,author:String(cfg.author || 'Reviewer'),
    storage:{mode:storage.mode,key:String(storage.key || `video-review:${slug}`)},
    reviewData:{comments:cfg.reviewData?.comments || [],events:cfg.reviewData?.events || []}};
  const notesCard = cfg.notes?.length ? `<div class="card"><h2>Editor's notes</h2><p class="hint">${escapeHTML(cfg.notesHint || 'Changes and decisions for this cut.')}</p><div class="notes">${cfg.notes.map(n => `<div class="note" data-tone="${escapeHTML(n.tone || '')}"><span class="nn">${escapeHTML(n.n)}</span><span class="nb">${basicHTML(n.b)}</span></div>`).join('')}</div></div>` : '';
  const subs = {TITLE:escapeHTML(title),VERSION_LABEL:escapeHTML(active.label),EYEBROW:escapeHTML(cfg.eyebrow || 'EDIT REVIEW'),
    BLURB:basicHTML(cfg.blurb || ''),FACTS:(cfg.facts || [`${active.duration.toFixed(2)}s · ${active.width}×${active.height} · ${active.fps.toFixed(3).replace(/\.?0+$/,'')}fps`]).map(f => `<span class="fact">${basicHTML(f)}</span>`).join(''),
    NOTES_CARD:notesCard,DOWNLOAD_BTN:downloads,VIDEO_FILE:escapeHTML(encodeURIComponent(active.file)),
    ACCENT_1:accents[0],ACCENT_2:accents[1],ACCENT_3:accents[2],GLOW_1:rgba(accents[0],.2),GLOW_2:rgba(accents[1],.14),PLAYER_WIDTH:playerWidth,
    CONFIG_JSON:scriptJSON(browserConfig)};
  let html = readFileSync(path.join(ASSETS,'canvas-template.html'),'utf8');
  html = html.replace(/\{\{([A-Z_0-9]+)\}\}/g, (match,key) => {
    if (!(key in subs)) throw new Error(`Unknown template field: ${key}`); return subs[key];
  });
  mkdirSync(path.join(outDir,'.herenow'),{recursive:true});
  writeFileSync(path.join(outDir,'index.html'),html);
  writeFileSync(path.join(outDir,'review-config.json'),JSON.stringify(browserConfig,null,2)+'\n');
  for (const name of ['review-model.mjs','review-app.mjs']) copyFileSync(path.join(ASSETS,name),path.join(outDir,name));
  copyFileSync(path.join(ASSETS,'data.json'),path.join(outDir,'.herenow','data.json'));
  for (const {source,file} of copies) if (path.resolve(source)!==path.resolve(outDir,file)) copyFileSync(source,path.join(outDir,file));
  return {outDir,config:browserConfig};
}

// Compare real paths: when the skill is reached through a symlink (a working repo linking this pack in),
// argv[1] is the link and import.meta.url the target, and a plain path compare silently does nothing.
const isMain = (() => { try { return !!process.argv[1] && realpathSync(path.resolve(process.argv[1])) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } })();
if (isMain) {
  if (!process.argv[2]) {console.error('usage: node build-canvas.mjs <config.json>'); process.exit(1);}
  const result = buildCanvas(process.argv[2]);
  console.log(`canvas built → ${result.outDir}\n  ${result.config.versions.length} version(s), active ${result.config.version}\n  storage: ${result.config.storage.mode}`);
  console.log(result.config.storage.mode === 'local' ? 'Serve this directory with a local HTTP server. Notes persist in this browser; export JSON to share/read back.' : `next: publish ${result.outDir} using here-now (reuse the existing project slug)`);
}

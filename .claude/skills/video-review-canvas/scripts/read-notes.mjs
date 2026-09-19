#!/usr/bin/env node
/** Read shared review records or a local JSON export, replaying append-only review events. */
import {readFileSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRemoteStore,revisionExport} from '../assets/review-model.mjs';

export async function readNotes(args, fetcher=fetch) {
  const positional=[];let file=null,json=false,out=null;
  for(let i=0;i<args.length;i++) {
    if(args[i]==='--file')file=args[++i];
    else if(args[i]==='--json')json=true;
    else if(args[i]==='--out')out=args[++i];
    else if(args[i].startsWith('--'))throw new Error(`Unknown option ${args[i]}`);
    else positional.push(args[i]);
  }
  if((!file&&!positional.length)||args.at(-1)==='--file'||args.at(-1)==='--out')throw new Error('usage: node read-notes.mjs <slug-or-url> [version] [--json] [--out file.json]\n       node read-notes.mjs --file review-revisions.json [version] [--json]');
  const version=file?positional[0]:positional[1];
  let data,metadata={};
  if(file){
    data=JSON.parse(readFileSync(file,'utf8'));
    if(!Array.isArray(data.comments)||!Array.isArray(data.events||[]))throw new Error('Review export must contain comments and optional events arrays');
    metadata={title:data.title,versions:data.versions,source:file};
  } else {
    const arg=positional[0],base=arg.startsWith('http')?arg.replace(/\/$/,''):`https://${arg}.here.now`;
    data=await createRemoteStore(fetcher,`${base}/.herenow/data/`).read();metadata={source:base};
  }
  const exported=revisionExport(data,metadata);
  if(version){
    exported.notes=exported.notes.filter(note=>note.version===version);
    const ids=new Set(exported.notes.map(n=>n.id));
    exported.comments=exported.comments.filter(c=>ids.has(String(c.id??c._id)) || (c.data?.version===version));
    exported.events=exported.events.filter(e=>ids.has(String(e.data?.commentId)));
    exported.version=version;
  }
  const encoded=JSON.stringify(exported,null,2)+'\n';
  if(out)writeFileSync(out,encoded);
  if(json)return encoded;
  if(!exported.notes.length)return `No notes${version?` for ${version}`:''}.\n`;
  return exported.notes.map(note=>{
    const lines=[`${note.id}  [${note.version}] ${Number(note.t).toFixed(3)}s${note.frame!==undefined?` f${note.frame}`:''}  ${note.status.toUpperCase()}  ${note.author||''}`,`  ${note.text}`];
    for(const reply of note.replies)lines.push(`  Reply (${reply.author||'Reviewer'}): ${reply.text}`);
    for(const e of note.evidence)lines.push(`  Evidence: ${e.beforeVersion} ${e.beforeT}s → ${e.afterVersion} ${e.afterT}s — ${e.text||''}`);
    return lines.join('\n');
  }).join('\n\n')+'\n';
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try{process.stdout.write(await readNotes(process.argv.slice(2)));}
  catch(error){console.error(error.message);process.exitCode=1;}
}

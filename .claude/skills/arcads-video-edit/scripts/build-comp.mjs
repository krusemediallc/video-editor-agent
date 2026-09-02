// V7 generator: the locked V5 cut is a character, not a background. Three-wrapper camera
// (#vclip clip-path | #vwrap x/y/scale | #base punch), five full-screen takeovers, the base
// video match-moving into splits / a circle PIP / a montage tile, real Seedance footage in
// cards, and one quote-glyph device for every opinion. Everything is transforms, clip-paths,
// dash offsets and pure proxies so it seeks and renders deterministically.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIR = path.dirname(fileURLToPath(import.meta.url));
const R = (p) => path.join(DIR, "..", p);
const words = JSON.parse(fs.readFileSync(R("mg/words.json"), "utf8"));
const free = JSON.parse(fs.readFileSync(R("mg/freespace.json"), "utf8"));
const shots = JSON.parse(fs.readFileSync(R("qa/v5-timeline.json"), "utf8"));
const sfxDur = JSON.parse(fs.readFileSync(R("mg/comp/assets/sfx/durations.json"), "utf8"));
const PROMPT = fs.existsSync(R("mg/gen/prompt-clay.txt")) ? fs.readFileSync(R("mg/gen/prompt-clay.txt"), "utf8") : "";
const DUR = 93.5;

// --- word lookup -------------------------------------------------------------
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9.%]/g, "");
function W(text, nth = 0) {
  const h = words.filter((w) => norm(w.text) === norm(text));
  if (!h[nth]) throw new Error(`word not found: ${text}#${nth}`);
  return h[nth].start;
}
function WS(sid, text, nth = 0) {
  const h = words.filter((w) => w.seg === sid && norm(w.text) === norm(text));
  if (!h[nth]) throw new Error(`word not found in ${sid}: ${text}#${nth}`);
  return h[nth].start;
}
const shotAt = (t) => shots.find(([a, b]) => t >= a && t < b)?.[2];
const f3 = (n) => +n.toFixed(3);

// --- measured camera facts (full-res frames, 2026-09-01) -----------------------
// face anchors (between the eyes) in canvas px per shot; scales between V5's own crops
const FACE = { hook: [550, 700], split02: [518, 1296], split06: [529, 1296], split13: [550, 1260], elev26: [440, 670] };
const S_SPLIT = 0.5;                    // cam crop (608 src px) vs split crop (1215 src px)
const S_PIP = 0.4;                      // split crop vs the 380px circle (1080 src px -> 380)
const PIP = { cx: 250, cy: 1608, r: 190, face: [270, 1560] };   // V5's own circle; the creator's eyes sit ~50px above centre
const rf = (S, [fx, fy], [qx, qy]) => ({ scale: S, x: f3(qx - 540 - S * (fx - 540)), y: f3(qy - 960 - S * (fy - 960)) });

// --- output accumulators -------------------------------------------------------
const html = [], tw = [], hits = [], css = [];
const spans = [];                       // on-screen text spans for caption muting
const capBand = [];                     // [a,b,y,inv]
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const hit = (name, t, vol) => { if (t >= 0 && t < DUR - 0.05) hits.push({ name, t: f3(t), vol }); };
const say = (a, b, text) => spans.push({ a, b, text });
let uid = 0; const id = (p) => `${p}${uid++}`;

// per-shot face origin for #base punches
const ORIGIN = {};
for (const [a, b, sid] of shots) {
  const f = free[sid]; const [sx, sy, sw, sh] = f.subject;
  ORIGIN[sid] = f.layout === "screen" ? [PIP.cx, PIP.cy] : [Math.round(sx + sw / 2), Math.round(sy + sh * 0.2)];
}
function PUNCH(t, s = 1.035, back = 0.5) {
  const o = ORIGIN[shotAt(t)] || [540, 700];
  tw.push(`tl.set("#base",{transformOrigin:"${o[0]}px ${o[1]}px"},${f3(t - 0.002)});`);
  tw.push(`tl.fromTo("#base",{scale:1},{scale:${s},duration:0.15,ease:"power3.out",immediateRender:false},${f3(t)});`);
  tw.push(`tl.to("#base",{scale:1,duration:${back},ease:"power2.out"},${f3(t + 0.15)});`);
}

// =============================================================================
// 0. HOOK STAMP  [1.12-3.72]
// =============================================================================
{
  const t = W("easiest"), t2 = W("possible"), t3 = W("right"), out = 3.72;
  html.push(`<div id="hook" class="plate cream quoteplate" data-layout-allow-overlap style="left:60px;top:44px;width:960px;font-size:74px">
    <i class="q ql" id="hook-ql">“</i><i class="q qr" id="hook-qr">”</i>
    <div class="ln" data-layout-allow-overlap id="hook-l1">The easiest method</div>
    <div class="lnwrap" data-layout-allow-overlap><div class="ln" data-layout-allow-overlap id="hook-l2a">possible</div><div class="ln alt" data-layout-allow-overlap id="hook-l2b">out there right now</div></div>
  </div>`);
  tw.push(`SLAM("#hook",${t});`, `QUOTES("#hook-ql","#hook-qr",${t});`, `RISEW("#hook-l1",${t + 0.05});`,
          `RISEW("#hook-l2a",${t2});`, `ROLL("#hook-l2a","#hook-l2b",${t3});`, `UPOUT("#hook",${out});`);
  PUNCH(t, 1.06, 0.35);
  hit("thud", t, 0.42); hit("click", t3, 0.22);
  say(t - 0.2, out, "the easiest method possible out there right now");
}

// =============================================================================
// N1. FULLY FINISHED ADS WITH AI  [3.80-6.55]  the creator shrinks, six ads float, the creator slides into the split
// =============================================================================
{
  const tA = W("fully"), tCards = [W("finished"), W("finished"), 4.70, 4.70, W("ads"), W("ads")];
  const tWith = W("with"), tAI = W("AI"), tB = 5.87, CUT = 6.267;
  const clips = ["5panel-corduroy-hat-premium-performance-gear-anime", "5panel-corduroy-hat-premium-performance-gear-cartoon",
                 "roas-ring-cartoon", "pixel-perfect-lego", "conversion-cola-knit", "hat-claymation"];
  const ms = [0, 0.7, 0.7, 0.7, 0.7, 0.7];
  const pos = [[60, 60], [390, 60], [720, 60], [60, 520], [390, 520], [720, 520]];
  const tile = [[0, 0], [360, 0], [720, 0], [0, 480], [360, 480], [720, 480]];
  // ink stage + drifting grid behind the cards
  html.push(`<div id="stage" class="field" data-layout-allow-overlap><i class="grid" id="stage-grid"></i></div>`);
  tw.push(`tl.fromTo("#stage",{opacity:0},{opacity:1,duration:0.2,ease:"power2.out",immediateRender:false},${tA});`,
          `tl.fromTo("#stage-grid",{x:0,y:0},{x:-90,y:-90,duration:${f3(6.30 - tA)},ease:"none",immediateRender:false},${tA});`,
          `tl.set("#stage",{opacity:0},${f3(CUT - 0.006)});`);
  // the creator shrinks into a ringed card
  const a = rf(0.72, FACE.hook, [540, 1400]);
  html.push(`<i id="vring" class="ring" style="left:${Math.round(540 - 1080 * 0.72 / 2)}px;top:${Math.round(960 - 1920 * 0.72 / 2 + a.y)}px;width:${Math.round(1080 * 0.72)}px;height:${Math.round(1920 * 0.72)}px"></i>`);
  tw.push(`tl.to("#vwrap",{scale:${a.scale},x:${a.x},y:${a.y},duration:0.45,ease:"power3.inOut"},${tA});`,
          `tl.to("#vclip",{borderRadius:24,duration:0.45,ease:"power3.inOut"},${tA});`,
          `tl.fromTo("#vring",{opacity:0},{opacity:1,duration:0.25,immediateRender:false},${tA + 0.3});`);
  // six real ads fly in from depth
  clips.forEach((c, i) => {
    const vid = `hk${i}`;
    html.push(`<div class="vcard hk" id="${vid}" style="left:${pos[i][0]}px;top:${pos[i][1]}px;width:300px;height:400px">
      <video id="${vid}-v" src="assets/clips/${c}.mp4" data-start="${tCards[i]}" data-duration="${f3(6.60 - tCards[i])}" data-media-start="${ms[i]}" muted playsinline></video></div>`);
    const ang = i * 2.39996;
    tw.push(`tl.fromTo("#${vid}",{x:${f3(Math.cos(ang) * 420)},y:${f3(Math.sin(ang) * 420)},z:${220 - i * 120},rotationX:${f3(Math.sin(ang) * 60)},rotationY:${f3(Math.cos(ang) * 60)},opacity:0},{x:0,y:0,z:0,rotationX:0,rotationY:0,opacity:1,duration:0.45,ease:"power3.out",immediateRender:false},${tCards[i]});`);
    // phase B: snap to a 3x2 mosaic tiling the top half exactly
    tw.push(`tl.to("#${vid}",{x:${tile[i][0] - pos[i][0]},y:${tile[i][1] - pos[i][1]},scale:1.2,transformOrigin:"0 0",duration:0.4,ease:"power3.inOut"},${tB});`);
  });
  tw.push(`tl.to(".vcard.hk",{y:"-=8",duration:0.37,ease:"none"},5.50);`);
  // WITH / AI type across the gutter
  html.push(`<div id="withai" class="bigword" data-layout-allow-overlap style="left:0;top:430px;width:1080px;text-align:center;font-size:140px"><span id="with-w">WITH</span> <span id="ai-w" class="extrude"><b>AI</b><b data-layout-allow-overlap>AI</b><b data-layout-allow-overlap>AI</b><b data-layout-allow-overlap>AI</b><b data-layout-allow-overlap>AI</b></span></div>`);
  tw.push(`tl.set("#withai",{opacity:1},${tWith - 0.001});`, `tl.fromTo("#with-w",{x:-320,opacity:0},{x:0,opacity:1,duration:0.45,ease:"expo.out",immediateRender:false},${tWith});`,
          `tl.fromTo("#ai-w",{opacity:0,scale:1.4},{opacity:1,scale:1,duration:0.3,ease:"power4.out",immediateRender:false},${tAI});`,
          `EXTRUDE("#ai-w",${tAI});`,
          `tl.to("#withai",{scale:0.6,opacity:0,duration:0.2,ease:"power2.in"},${tB});`, `tl.set("#withai",{opacity:0},${tB + 0.21});`);
  // phase B: the creator slides to the split's face position at the split's scale; full-frame blinds hide the cut
  const b = rf(S_SPLIT, FACE.hook, FACE.split02);
  tw.push(`tl.to("#vwrap",{scale:${b.scale},x:${b.x},y:${b.y},duration:0.38,ease:"power3.inOut"},${tB});`,
          `tl.to("#vclip",{borderRadius:0,duration:0.3},${tB});`, `tl.to("#vring",{opacity:0,duration:0.2},${tB});`,
          `BLINDS(6.02,6.52,.14,.015);`,
          `tl.set("#vwrap",{scale:1,x:0,y:0},${f3(CUT - 0.006)});`, `tl.set("#vclip",{borderRadius:0},${f3(CUT - 0.006)});`);
  clips.forEach((c, i) => tw.push(`tl.set("#hk${i}",{opacity:0},${f3(CUT - 0.006)});`));
  hit("swipe", tA, 0.24); hit("thud", tCards[0], 0.36); hit("click", 4.70, 0.22); hit("pop", tWith, 0.30); hit("thud", tAI, 0.40); hit("swipe", tB, 0.24); hit("swipe", 6.17, 0.22);
  say(tWith - 0.2, tB, "with ai");
}

// =============================================================================
// N2. arcads.ai speech bubble above the creator's head  [7.67-11.40]
// =============================================================================
{
  const t = W("arcads.ai"), out = 11.40;
  html.push(`<div id="bub" class="chip cream mono bubble" style="left:${FACE.split02[0] - 150}px;top:932px;transform-origin:50% 100%"><span class="sheen">arcads.ai</span><i class="tail"></i></div>`);
  tw.push(`tl.fromTo("#bub",{opacity:0,scale:0,y:20},{opacity:1,scale:1,y:0,duration:0.34,ease:"power3.out",immediateRender:false},${t});`,
          `SHEEN("#bub .sheen",${W("log")});`,
          `tl.fromTo("#bub",{rotation:-2},{rotation:0,duration:0.3,ease:"back.out(2)",immediateRender:false},${W("sign")});`,
          `tl.to("#bub",{scale:0,y:20,opacity:0,duration:0.2,ease:"power2.in"},${out});`, `tl.set("#bub",{opacity:0},${out + 0.21});`);
  hit("pop", t, 0.30);
}

// =============================================================================
// "THE CRAZIEST THING" seam chip [11.96-13.08]
// =============================================================================
{
  const t = W("craziest"), t2 = W("thing"), out = 13.08;
  html.push(`<div id="crz" class="chip ink hang" style="left:60px;top:962px">The craziest thing</div>`);
  tw.push(`HANG("#crz",${t});`, `TICK("#crz",${t2});`, `tl.to("#crz",{clipPath:"inset(100% 0 0 0)",duration:0.14,ease:"power2.in"},${out});`, `tl.set("#crz",{opacity:0},${out + 0.15});`);
  PUNCH(t); hit("pop", t, 0.30);
  say(t - 0.2, out, "the craziest thing");
}

// =============================================================================
// N3. NEW MODELS switchboard takeover  [13.10-16.44]
// =============================================================================
{
  const tIn = W("new"), tHead = W("models"), tOut = 16.44;
  const rows = ["Seedance 2.5", "OmniHuman 1.5", "Sora 2 Pro", "Veo 3.1", "Kling 3.0", "GPT Image 2", "Nano Banana Pro", "Seedream"];
  const flips = [13.66, 13.84, 14.10, 14.32, 14.50, 14.66, 14.84, 14.96];
  const tAll = W("literally");
  html.push(`<div id="tk-models" class="tk" data-layout-allow-overlap>
    <i class="grid" id="tkm-grid"></i><i class="scan" id="tkm-scan"></i>
    <div class="kicker" style="top:120px">MODELS · INSIDE ARCADS</div>
    <div class="counter mono" id="tkm-count" style="top:112px;right:80px"><span id="tkm-n">0</span>/8</div>
    <div class="hero extrude" id="tkm-head" style="top:190px"><b>NEW MODELS</b><b data-layout-allow-overlap>NEW MODELS</b><b data-layout-allow-overlap>NEW MODELS</b><b data-layout-allow-overlap>NEW MODELS</b><b data-layout-allow-overlap>NEW MODELS</b><b data-layout-allow-overlap>NEW MODELS</b></div>
    <div class="rows" id="tkm-rows">${rows.map((r, i) => `<div class="tg" id="tg${i}"><span class="tg-name">${esc(r)}</span><span class="tg-track"><i class="tg-ring"></i><i class="tg-knob"></i></span><span class="tg-st mono"><b class="off">OFF</b><b class="on">ON</b></span></div>`).join("")}</div>
    <div class="footchip" id="tkm-foot"><img src="assets/arcads-mark.png" alt="" /><span>ARCADS</span></div>
  </div>`);
  tw.push(`SLICEIN("#tk-models",${tIn});`,
          `tl.fromTo("#tkm-grid",{x:0,y:0},{x:-90,y:-90,duration:${f3(tOut - tIn)},ease:"none",immediateRender:false},${tIn});`,
          `tl.fromTo("#tkm-scan",{y:0},{y:2080,duration:1.6,ease:"none",immediateRender:false},${tIn + 0.1});`,
          `tl.fromTo("#tkm-head",{scale:1.5,opacity:0,filter:"blur(16px)"},{scale:1,opacity:1,filter:"blur(0px)",duration:0.45,ease:"power4.out",immediateRender:false},${tHead});`,
          `EXTRUDE("#tkm-head",${tHead + 0.1});`,
          `tl.fromTo("#tk-models .kicker",{opacity:0,scaleX:1.3},{opacity:0.7,scaleX:1,duration:0.4,ease:"power3.out",immediateRender:false},${tIn + 0.15});`);
  rows.forEach((_, i) => tw.push(`WATER("#tg${i}",${f3(13.40 + i * 0.033)});`, `TOGGLE("#tg${i}",${flips[i]},${i + 1});`));
  tw.push(`tl.fromTo("#tkm-count",{opacity:0},{opacity:1,duration:0.2,immediateRender:false},${tIn + 0.3});`,
          `POPC("#tkm-foot",${W("Arcads", 0)});`,
          `tl.fromTo("#tkm-rows",{filter:"brightness(1)"},{filter:"brightness(1.6)",duration:0.1,yoyo:true,repeat:1,immediateRender:false},${tAll});`,
          `tl.fromTo("#tkm-count",{scale:1},{scale:1.18,duration:0.12,yoyo:true,repeat:1,ease:"power2.out",immediateRender:false},${tAll});`,
          `TICK("#tkm-head",${tAll});`,
          `tl.to("#tk-models",{yPercent:-100,duration:0.45,ease:"power3.inOut"},${tOut});`, `tl.set("#tk-models",{opacity:0,yPercent:0},${tOut + 0.46});`,
          `tl.set("#base",{scale:1.08,transformOrigin:"${ORIGIN["03-craziest"][0]}px ${ORIGIN["03-craziest"][1]}px"},${tOut});`, `tl.to("#base",{scale:1,duration:0.6,ease:"power2.out"},${tOut + 0.01});`);
  capBand.push([tIn, tOut, 1690, true]);
  hit("sub", tIn, 0.34); hit("thud", tIn, 0.42); [0, 1, 3, 6].forEach((i) => hit("click", flips[i], 0.22)); hit("ding", tAll, 0.26); hit("swipe", tOut, 0.24);
  say(tIn - 0.2, tOut, "new models");
}

// =============================================================================
// "A REFERENCE AD" chip + preview thumb [17.20-18.38]  then N4 reference takeover [18.38-21.09]
// =============================================================================
{
  const t = W("reference"), tThumb = W("ad", 0), tRush = W("as", 0), tFull = W("a", 1), tBr = W("video", 0), tBack = 20.75, tThis = W("this"), tHold = 22.88;
  html.push(`<div id="refchip" class="chip cream hang" style="left:60px;top:962px">A reference ad</div>`);
  html.push(`<div class="vcard" id="refthumb" style="left:740px;top:700px;width:280px;height:500px;transform-origin:50% 50%"><video id="refthumb-v" src="assets/ref-nologo.mp4" data-start="${tThumb}" data-duration="${f3(tFull + 0.05 - tThumb)}" data-media-start="1.5" muted playsinline></video></div>`);
  html.push(`<div id="v1chip" class="chip ink mono" style="left:740px;top:640px">[Video1]</div>`);
  tw.push(`HANG("#refchip",${t});`, `POPC("#refthumb",${tThumb});`, `tl.fromTo("#v1chip",{x:-120,opacity:0},{x:0,opacity:1,duration:0.3,ease:"expo.out",immediateRender:false},${tThumb});`,
          `tl.to("#refchip",{clipPath:"inset(100% 0 0 0)",duration:0.14,ease:"power2.in"},${tRush});`, `tl.set("#refchip",{opacity:0},${tRush + 0.15});`,
          `tl.to("#v1chip",{opacity:0,duration:0.12},${tRush});`, `tl.set("#v1chip",{opacity:0},${tRush + 0.13});`);
  PUNCH(t); hit("pop", t, 0.30);
  say(t - 0.2, tRush, "a reference ad");
  // N4: the thumb rushes the lens and IS the frame
  html.push(`<div id="tk-ref" class="tkwrap" data-layout-allow-overlap><div id="tk-ref-in" class="tkin"><video id="ref-full-v" src="assets/ref-nologo.mp4" data-start="${tFull}" data-duration="${f3(21.10 - tFull)}" data-media-start="0.08" muted playsinline></video>
      <i class="br bl" id="br0"></i><i class="br" id="br1" style="left:auto;right:40px"></i><i class="br" id="br2" style="top:auto;bottom:40px"></i><i class="br" id="br3" style="top:auto;bottom:40px;left:auto;right:40px"></i>
      <div class="chip ink mono" id="reftag" style="left:60px;top:120px">[Video1] · REFERENCE</div></div></div>`);
  tw.push(`tl.to("#refthumb",{scale:3.9,x:-340,y:110,duration:0.30,ease:"power4.in"},${tRush});`,
          `tl.set("#tk-ref",{opacity:1},${tFull});`, `tl.set("#refthumb",{opacity:0},${tFull + 0.02});`,
          `tl.fromTo("#tk-ref-in",{scale:1},{scale:1.04,duration:${f3(tBack - tFull)},ease:"none",immediateRender:false},${tFull + 0.02});`,
          `tl.fromTo("#br0",{x:-60,y:-60,opacity:0},{x:0,y:0,opacity:1,duration:0.18,ease:"power4.out",immediateRender:false},${tBr});`,
          `tl.fromTo("#br1",{x:60,y:-60,opacity:0},{x:0,y:0,opacity:1,duration:0.18,ease:"power4.out",immediateRender:false},${tBr});`,
          `tl.fromTo("#br2",{x:-60,y:60,opacity:0},{x:0,y:0,opacity:1,duration:0.18,ease:"power4.out",immediateRender:false},${tBr});`,
          `tl.fromTo("#br3",{x:60,y:60,opacity:0},{x:0,y:0,opacity:1,duration:0.18,ease:"power4.out",immediateRender:false},${tBr});`,
          `POPC("#reftag",${tBr});`,
          // collapse back into the real popup rectangle (x54,y458,457x801): clip on the outer, transform on the inner
          `tl.set("#tk-ref",{clipPath:"inset(0 0 11px 0)"},${tBack - 0.01});`,
          `tl.to("#tk-ref-in",{scale:0.423,x:54,y:458,transformOrigin:"0 0",duration:0.34,ease:"power3.inOut"},${tBack});`,
          `tl.to("#tk-ref",{opacity:0,duration:0.12},${tBack + 0.22});`, `tl.set("#tk-ref",{opacity:0},${tBack + 0.35});`);
  // bracket around the real popup + [Video1] tag, on "this"
  html.push(`<svg id="popbr" class="absvg" viewBox="0 0 1080 1920"><rect id="popbr-r" x="48" y="452" width="469" height="813" rx="16" fill="none" stroke="#F4F2EE" stroke-width="6"/></svg>
    <div id="popchip" class="chip ink mono" style="left:530px;top:458px">[Video1]</div>`);
  tw.push(`tl.set("#popbr",{opacity:1},${tThis});`, `DRAWP("#popbr-r",${tThis},0.34);`, `POPC("#popchip",${tThis});`,
          `tl.to("#popbr",{opacity:0,duration:0.16},${tHold});`, `tl.set("#popbr",{opacity:0},${tHold + 0.17});`, `OUTC("#popchip",${tHold});`);
  capBand.push([tFull, 20.46, 1690, false]);
  hit("sub", tFull, 0.34); hit("thud", tFull, 0.42); hit("pop", tBr, 0.30); hit("swipe", tBack, 0.24);
}

// =============================================================================
// [Image1] -> YOUR PRODUCT tumble-swap  [25.11-28.72]
// =============================================================================
{
  const t1 = W("reference", 1), t2 = W("product", 0), tSwap = W("swap"), out = 28.72;
  html.push(`<div id="swaphost" class="persp" data-layout-allow-overlap><div id="img1" class="chip ink mono hang" style="left:60px;top:962px">[Image1]</div><i id="plus" class="plus">+</i><div id="yourprod" class="chip cream hang" style="left:420px;top:962px">Your product</div></div>`);
  tw.push(`HANG("#img1",${t1});`, `HANG("#yourprod",${t2});`, `tl.fromTo("#plus",{opacity:0,scale:0},{opacity:1,scale:1,duration:0.2,ease:"back.out(2)",immediateRender:false},${t2 + 0.05});`,
          `TUMBLE("#img1","#yourprod",${tSwap});`,
          `tl.to("#swaphost",{clipPath:"inset(100% 0 0 0)",duration:0.14,ease:"power2.in"},${out});`, `tl.set("#swaphost",{opacity:0},${out + 0.15});`);
  PUNCH(tSwap, 1.05); hit("pop", t1, 0.30); hit("scratch", tSwap, 0.34);
  say(t2 - 0.2, out, "your product");
}

// =============================================================================
// PRE-BEAT nodes on the seam [29.59-31.17] -> N5 MCP field takeover with the circle PIP [31.17-35.12]
// =============================================================================
{
  const tLine = W("connect"), tA = WS("06-claudecode", "Arcads"), tB = W("into"), tIn = WS("06-claudecode", "Claude", 0), tCode = W("Code", 0);
  const tAnd = WS("06-claudecode", "and"), tPk = WS("06-claudecode", "Claude", 1), tYou = WS("06-claudecode", "you"), tWrite = W("write");
  const tIns = W("insanely"), tDet = W("detailed"), tPr = W("prompts"), tOut = WS("08-gptimage", "and"), CUT = 35.067;
  html.push(`<i id="seam" class="seamline" style="transform-origin:0 50%"></i>`);
  html.push(`<div id="nodeA" class="node" style="left:200px;top:958px"><img src="assets/arcads-mark.png" alt="" /><span>ARCADS</span></div>
    <div id="nodeB" class="node" style="left:880px;top:958px"><span>CLAUDE CODE</span></div>`);
  tw.push(`tl.fromTo("#seam",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:${f3(tB - tLine)},ease:"power2.out",immediateRender:false},${tLine});`,
          `POPC("#nodeA",${tA});`, `POPC("#nodeB",${tB});`);
  // the field
  const promptLines = (PROMPT || "").split("\n").filter(Boolean).slice(0, 5).map((l) => l.replace(/(\.)\s*;?\s*[a-z][^.]{0,60}\.?$/, "$1").replace(/\s*;\s*[a-z][^.]*$/, "."));
  html.push(`<div id="tk-mcp" class="tk low" data-layout-allow-overlap>
    <div class="persp3" id="mcp-world"><i class="grid dots" id="mcp-grid"></i>
      <i class="radar" id="rd0" style="left:540px;top:300px"></i><i class="radar" id="rd1" style="left:540px;top:300px"></i><i class="radar" id="rd2" style="left:540px;top:300px"></i>
      <i class="radar" id="rd3" style="left:540px;top:560px"></i><i class="radar" id="rd4" style="left:540px;top:560px"></i><i class="radar" id="rd5" style="left:540px;top:560px"></i>
      <svg class="absvg" viewBox="0 0 1080 1920"><path id="wire" d="M 540 380 C 540 500 540 640 540 740" fill="none" stroke="#F4F2EE" stroke-width="5" stroke-linecap="round"/>
        <path id="wire-ghost" d="M 540 380 C 540 500 540 640 540 740" fill="none" stroke="#F4F2EE" stroke-width="2" stroke-dasharray="8 14" opacity="0"/>
        <circle id="pk0" r="9" fill="#F4F2EE" opacity="0"/><circle id="pk1" r="9" fill="#F4F2EE" opacity="0"/><circle id="pk2" r="9" fill="#F4F2EE" opacity="0"/><circle id="pk3" r="9" fill="#F4F2EE" opacity="0"/></svg>
      <div class="bignode" id="bnA" style="top:230px"><i class="halo" id="haloA"></i><img src="assets/arcads-mark.png" alt="" /><span class="extrude"><b>ARCADS</b><b data-layout-allow-overlap>ARCADS</b><b data-layout-allow-overlap>ARCADS</b><b data-layout-allow-overlap>ARCADS</b></span></div>
      <div class="bignode" id="bnB" style="top:750px"><i class="halo" id="haloB"></i><span class="extrude"><b>CLAUDE CODE</b><b data-layout-allow-overlap>CLAUDE CODE</b><b data-layout-allow-overlap>CLAUDE CODE</b><b data-layout-allow-overlap>CLAUDE CODE</b></span></div>
      <div class="chip cream mono pill" id="mcp-pill" style="left:462px;top:526px">MCP</div>
      <div class="term mono" id="term"><span id="term-l1"></span><span id="term-l2"></span><span id="term-l3"></span><i class="caret" id="term-caret"></i></div>
      <div class="promptcard mono" id="pcard" data-layout-allow-overlap><div id="pcard-in">${promptLines.map((l, i) => `<div class="pl" data-layout-allow-overlap id="pl${i}">${esc(l)}</div>`).join("")}</div><i class="pbar" id="pbar"></i></div>
    </div>
    <div class="quoteband" id="idp" data-layout-allow-overlap><i class="q ql">“</i>INSANELY DETAILED PROMPTS<i class="q qr">”</i></div>
  </div>`);
  html.push(`<i id="pipring" class="pipring"><i id="pipflash"></i></i>`);
  const p = rf(S_PIP, FACE.split06, PIP.face);
  tw.push(`tl.set("#tk-mcp",{opacity:1},${tIn - 0.01});`,
          `tl.to("#vclip",{clipPath:"circle(${PIP.r}px at ${PIP.cx}px ${PIP.cy}px)",duration:0.45,ease:"power3.inOut"},${tIn});`,
          `tl.to("#vwrap",{scale:${p.scale},x:${p.x},y:${p.y},duration:0.45,ease:"power3.inOut"},${tIn});`,
          `tl.fromTo("#pipring",{opacity:0},{opacity:1,duration:0.2,immediateRender:false},${tIn + 0.3});`,
          `tl.to("#seam",{opacity:0,duration:0.2},${tIn});`,
          `tl.to("#nodeA",{x:340,y:-700,scale:1.6,duration:0.45,ease:"power3.inOut"},${tIn});`, `tl.to("#nodeB",{x:-340,y:-180,scale:1.6,duration:0.45,ease:"power3.inOut"},${tIn});`,
          `tl.set("#nodeA",{opacity:0},${tIn + 0.46});`, `tl.set("#nodeB",{opacity:0},${tIn + 0.46});`,
          `tl.fromTo("#bnA",{opacity:0},{opacity:1,duration:0.15,immediateRender:false},${tIn + 0.35});`, `tl.fromTo("#bnB",{opacity:0},{opacity:1,duration:0.15,immediateRender:false},${tIn + 0.35});`,
          `tl.fromTo("#mcp-world",{rotationX:8},{rotationX:4,duration:${f3(tOut - tIn)},ease:"none",immediateRender:false},${tIn});`,
          `tl.fromTo("#mcp-grid",{x:0,y:0},{x:-60,y:-60,duration:${f3(tOut - tIn)},ease:"none",immediateRender:false},${tIn});`,
          `RADAR("#rd0","#rd1","#rd2",${tIn});`, `RADAR("#rd3","#rd4","#rd5",${tAnd});`,
          `DRAWP("#wire",${tCode},0.7);`, `tl.set("#wire-ghost",{opacity:0.45},${tAnd});`, `FLOW("#wire-ghost",${tAnd + 0.1},${tOut});`,
          `POPC("#mcp-pill",${tAnd});`,
          `PACKET("#wire","#pk0",${tPk},0.9,false);`, `PACKET("#wire","#pk1",${tPk + 0.18},0.9,false);`, `PACKET("#wire","#pk2",${tPk + 0.36},0.9,false);`, `PACKET("#wire","#pk3",${tYou},0.9,true);`,
          `HALO("#haloA",${tIn + 0.5});`, `HALO("#haloB",${tIn + 0.7});`,
          `tl.fromTo("#term",{opacity:0,y:20},{opacity:1,y:0,duration:0.25,ease:"power3.out",immediateRender:false},${tIn + 0.3});`,
          `TYPE("#term-l1",[[0,"→ mcp.arcads.ai"],[0.12,"→ mcp.arcads.ai ·"],[0.24,"→ mcp.arcads.ai · connecting"]],${tIn + 0.33},${tCode + 0.3});`,
          `TYPE("#term-l2",[[0,"← capabilities"],[0.15,"← capabilities · tools"],[0.3,"← capabilities · tools · prompts"]],${tAnd + 0.1},${tPk});`,
          `TYPE("#term-l3",[[0,"✓ connected"]],${tWrite},${tWrite + 0.05});`, `BLINK("#term-caret",${tIn + 0.3},${tOut});`,
          `tl.fromTo("#pcard",{opacity:0,y:30},{opacity:1,y:0,duration:0.25,ease:"power3.out",immediateRender:false},${tIns});`,
          `STREAM("#pcard-in","#pbar",${promptLines.length},${tIns + 0.05},${tOut - 0.05});`,
          `tl.fromTo("#pcard",{scale:1},{scale:1.02,duration:0.1,yoyo:true,repeat:1,immediateRender:false},${tDet});`,
          `tl.fromTo("#idp",{scale:1.5,opacity:0,filter:"blur(16px)"},{scale:1,opacity:1,filter:"blur(0px)",duration:0.45,ease:"power4.out",immediateRender:false},${tPr});`,
          // whip out; PIP hands off to V5's native circle under a ring flash
          `tl.to("#tk-mcp",{filter:"blur(12px)",skewX:-8,x:-200,opacity:0,duration:0.35,ease:"power3.in"},${tOut});`, `tl.set("#tk-mcp",{opacity:0,filter:"none",skewX:0,x:0},${tOut + 0.36});`,
          `tl.set("#pipflash",{opacity:0.6},${CUT - 0.02});`, `tl.set("#pipflash",{opacity:0},${CUT + 0.045});`,
          `tl.set("#vclip",{clipPath:"none"},${f3(CUT - 0.006)});`, `tl.set("#vwrap",{scale:1,x:0,y:0},${f3(CUT - 0.006)});`,
          `tl.to("#pipring",{opacity:0,duration:0.2},${38.35});`, `tl.set("#pipring",{opacity:0},${38.56});`);
  capBand.push([tIn, tOut, 1150, true]);
  capBand.push([tOut, 38.40, 1296, false]);
  hit("pop", tA, 0.30); hit("pop", tB, 0.30); hit("sub", tIn, 0.34); hit("thud", tIn, 0.42); hit("pop", tAnd, 0.30); hit("click", tPk, 0.22); hit("ding", tWrite, 0.26); hit("thud", tPr, 0.40); hit("swipe", tOut, 0.24);
  say(tPr - 0.2, tOut, "insanely detailed prompts");
}

// =============================================================================
// STARTING FRAMES filmstrip over the example [36.13-38.30]
// =============================================================================
{
  const ts = [W("starting"), W("frames"), W("of", 2), W("GPT Image 2")], tChip = W("GPT Image 2"), tFlip = W("for", 1), out = 38.30;
  const stills = ["hat-clay", "pp-lego", "cc-knit", "rr-pixar"], clips = ["hat-claymation", "pixel-perfect-lego", "conversion-cola-knit", "roas-ring-pixar"];
  stills.forEach((s, i) => {
    html.push(`<div class="vcard fs" id="fs${i}" style="left:${60 + i * 260}px;top:44px;width:220px;height:275px"><img id="fs${i}-i" src="assets/frames/${s}.png" alt="" /><div class="vin" id="fs${i}-w"><video id="fs${i}-v" src="assets/clips/${clips[i]}.mp4" data-start="${tFlip}" data-duration="${f3(out + 0.05 - tFlip)}" data-media-start="0" muted playsinline></video></div></div>`);
    tw.push(`WATER("#fs${i}",${ts[i]});`, `tl.fromTo("#fs${i}-w",{opacity:0},{opacity:1,duration:0.15,immediateRender:false},${tFlip});`, `tl.to("#fs${i}",{y:-400,duration:0.18,ease:"power3.in"},${out});`, `tl.set("#fs${i}",{opacity:0},${out + 0.19});`);
  });
  html.push(`<div id="fschip" class="chip ink mono" style="left:60px;top:340px">Starting frames · GPT Image 2</div>`);
  tw.push(`POPC("#fschip",${tChip});`, `tl.to("#fschip",{y:-400,duration:0.18,ease:"power3.in"},${out});`, `tl.set("#fschip",{opacity:0},${out + 0.19});`);
  hit("click", ts[0], 0.22); hit("click", ts[3], 0.22); hit("pop", tChip, 0.30); hit("click", tFlip, 0.24);
}

// =============================================================================
// "THESE TURNED OUT SO GOOD" quote slam [39.60-40.30]
// =============================================================================
{
  const t = W("so"), t2 = W("good"), out = 40.30;
  html.push(`<div id="sogood" class="plate cream quoteplate" data-layout-allow-overlap style="left:60px;top:40px;width:960px;font-size:66px"><i class="q ql" id="sg-ql">“</i><i class="q qr" id="sg-qr">”</i>
    <div class="ln" data-layout-allow-overlap id="sg-l1">These turned out</div><div class="ln" data-layout-allow-overlap id="sg-l2">so good</div></div>`);
  tw.push(`tl.fromTo("#sogood",{y:90,rotation:6,opacity:0},{y:0,rotation:0,opacity:1,duration:0.55,ease:"circ.out",immediateRender:false},${t});`, `QUOTES("#sg-ql","#sg-qr",${t});`, `RISEW("#sg-l1",${t + 0.05});`, `RISEW("#sg-l2",${t + 0.12});`, `GRAV("#sogood",${out});`);
  PUNCH(t, 1.06, 0.3); PUNCH(t2 + 0.02, 1.12, 0.28);
  hit("thud", t, 0.42); hit("click", t2, 0.22);
  say(t - 0.3, out, "these videos turned out so good");
}

// =============================================================================
// N7. CREDITS card, top half [41.21-48.85]
// =============================================================================
{
  const tIn = W("wrote"), rows = [["SCRIPT", "CLAUDE CODE", W("script")], ["VIDEO", "SEEDANCE 2.5", W("Seedance 2.5")], ["INSIDE", "ARCADS", W("Arcads", 2)], ["SOUND + MUSIC", "SEEDANCE 2.5", W("sound")]];
  const tLit = W("literally", 1), tMus = W("music"), out = 48.85;
  html.push(`<div id="credits" class="plate ink bigcard" data-layout-allow-overlap style="left:60px;top:140px;width:960px;height:700px"><div class="kicker rel" id="cr-k">CREDITS</div>
    ${rows.map(([r, n, t], i) => `<div class="crow" id="cr${i}"><i class="hair" id="cr${i}-h"></i><span class="role mono" id="cr${i}-r">${r}</span><span class="name sheen" id="cr${i}-n">${n === "ARCADS" ? `<img src="assets/arcads-mark.png" alt="" class="mk" />` : ""}${n}</span></div>`).join("")}
    <div class="wave" id="wave">${Array.from({ length: 8 }, (_, i) => `<i id="wv${i}"></i>`).join("")}</div></div>`);
  tw.push(`tl.fromTo("#credits",{clipPath:"inset(0 0 100% 0)",opacity:1},{clipPath:"inset(0 0 0% 0)",opacity:1,duration:0.35,ease:"power3.inOut",immediateRender:false},${tIn});`,
          `tl.fromTo("#cr-k",{opacity:0,scaleX:1.3,transformOrigin:"0 50%"},{opacity:0.7,scaleX:1,duration:0.4,ease:"power3.out",immediateRender:false},${tIn + 0.1});`);
  rows.forEach(([, , t], i) => tw.push(`tl.fromTo("#cr${i}-h",{scaleX:0},{scaleX:1,duration:0.25,ease:"power2.out",immediateRender:false},${t});`, `WATER("#cr${i}-r",${t + 0.02});`, `tl.fromTo("#cr${i}-n",{opacity:0,y:80},{opacity:1,y:0,duration:0.18,ease:"power4.out",immediateRender:false},${t + 0.06});`, `SHEEN("#cr${i}-n",${t + 0.25});`));
  tw.push(`tl.set("#wave",{opacity:1},${tMus - 0.01});`, `SHEEN("#cr0-n",${tLit});`, `SHEEN("#cr1-n",${tLit + 0.05});`, `SHEEN("#cr2-n",${tLit + 0.1});`, `WAVE(${tMus},${out - 0.05});`,
          `tl.to("#credits",{yPercent:-110,duration:0.3,ease:"power3.in"},${out});`, `tl.set("#credits",{opacity:0},${out + 0.31});`);
  rows.forEach(([, , t]) => PUNCH(t));
  hit("swipe", tIn, 0.24); rows.forEach(([, , t]) => hit("click", t, 0.22)); hit("shimmer", tMus, 0.30);
  say(tIn - 0.2, out, "script claude code video seedance 2.5 arcads sound music");
}

// =============================================================================
// N8. CHECKLIST top, four checks, EVERYTHING, then it flips into the quote [49.05-54.20]
// =============================================================================
{
  const tIn = W("every", 0), checks = [["EVERY SHOT", W("shot")], ["EVERY FRAME", W("frame")], ["THE CONCEPT", W("concept")], ["THE STORYBOARD", W("storyboard")]];
  const tEv = W("everything", 0), tFlip = W("I", 0), out = 54.20;
  html.push(`<div id="ckhost" class="persp" data-layout-allow-overlap style="left:60px;top:70px;width:960px;height:660px">
    <div id="ckcard" class="plate ink bigcard face" data-layout-allow-overlap style="left:0;top:0;width:960px;height:660px"><div class="kicker rel">GENERATED</div><div class="counter mono" id="ck-count" style="top:22px;right:30px"><span id="ck-n">0</span>/4</div>
      ${checks.map(([l], i) => `<div class="ck" id="ck${i}"><span class="bx"><i class="bxf"></i><svg viewBox="0 0 40 40" width="40" height="40"><path class="tick" id="ck${i}-t" d="M9 21 L17 29 L31 12"/></svg><i class="ring"></i><i class="dots" id="ck${i}-d"></i></span><span class="lbl">${l}</span></div>`).join("")}
      <svg class="conic" viewBox="0 0 120 120" width="120" height="120"><circle id="ck-ring" cx="60" cy="60" r="52" fill="none" stroke="#F4F2EE" stroke-width="8"/></svg>
      <div class="hero extrude" id="ck-ev" style="top:470px;font-size:120px"><b>EVERYTHING</b><b data-layout-allow-overlap>EVERYTHING</b><b data-layout-allow-overlap>EVERYTHING</b><b data-layout-allow-overlap>EVERYTHING</b><b data-layout-allow-overlap>EVERYTHING</b></div></div>
    <div id="ckback" class="plate cream bigcard face back quoteplate" data-layout-allow-overlap style="left:0;top:0;width:960px;height:660px;font-size:96px;display:flex;flex-direction:column;justify-content:center"><i class="q ql" id="ckb-ql">“</i><i class="q qr" id="ckb-qr">”</i><div class="ln" data-layout-allow-overlap id="ckb-l1">I didn't have to</div><div class="ln" data-layout-allow-overlap id="ckb-l2">do anything</div></div>
  </div>`);
  tw.push(`tl.fromTo("#ckcard",{x:-1100,opacity:1},{x:0,opacity:1,duration:0.4,ease:"power3.out",immediateRender:false},${tIn});`, `tl.fromTo("#ck-count",{opacity:0},{opacity:1,duration:0.2,immediateRender:false},${tIn + 0.3});`);
  checks.forEach(([, t], i) => tw.push(`WATER("#ck${i}",${f3(tIn + 0.12 + i * 0.06)});`, `CHECK("#ck${i}",${t},${i + 1},"#ck-n");`));
  tw.push(`DRAWP("#ck-ring",${tEv},0.4);`, `tl.fromTo("#ck-ev",{scale:1.5,opacity:0,filter:"blur(16px)"},{scale:1,opacity:1,filter:"blur(0px)",duration:0.45,ease:"power4.out",immediateRender:false},${tEv});`, `EXTRUDE("#ck-ev",${tEv + 0.1});`,
          `tl.to("#ckcard",{rotationY:90,duration:0.18,ease:"power2.in"},${tFlip});`, `tl.set("#ckcard",{opacity:0},${tFlip + 0.19});`,
          `tl.fromTo("#ckback",{rotationY:-90,opacity:1},{rotationY:0,opacity:1,duration:0.32,ease:"back.out(1.4)",immediateRender:false},${tFlip + 0.1});`, `RISEW("#ckb-l1",${tFlip + 0.2});`, `RISEW("#ckb-l2",${tFlip + 0.3});`, `QUOTES("#ckb-ql","#ckb-qr",${tFlip + 0.25});`,
          `tl.to("#ckhost",{y:-900,duration:0.25,ease:"power3.in"},${out});`, `tl.set("#ckhost",{opacity:0},${out + 0.26});`);
  checks.forEach(([, t]) => PUNCH(t)); PUNCH(tFlip + 0.1, 1.06); PUNCH(W("anything", 0), 1.10, 0.4);
  hit("swipe", tIn, 0.24); checks.forEach(([, t]) => hit("ding", t, 0.26)); hit("thud", tEv, 0.40); hit("sub", tFlip, 0.32); hit("thud", tFlip + 0.1, 0.42);
  say(tIn - 0.2, tFlip, "every shot every frame the concept the storyboard everything");
  say(tFlip - 0.1, out, "i didn't have to do anything");
}

// =============================================================================
// N9. the seam strip, the creator's own gripe list, quoted [54.27-58.62]
// =============================================================================
{
  const tNo = W("No"), tAnn = W("annoying"), tV = W("vocal"), tD = W("drift"), tC = W("character"), tI = W("inconsistencies"), out = 58.55;
  html.push(`<i id="seam2" class="seamline" style="transform-origin:50% 50%"></i>
    <div id="strip" class="strip" data-layout-allow-overlap><span class="kick mono">“NO MORE ANNOYING THINGS LIKE</span>
      <div class="ck sm" id="sk0"><span class="bx"><i class="bxf"></i><svg viewBox="0 0 40 40" width="40" height="40"><path class="tick" id="sk0-t" d="M9 21 L17 29 L31 12"/></svg><i class="ring"></i><i class="dots" id="sk0-d"></i></span><span class="lbl slice" id="sk0-l">VOCAL DRIFT</span></div>
      <div class="ck sm" id="sk1"><span class="bx"><i class="bxf"></i><svg viewBox="0 0 40 40" width="40" height="40"><path class="tick" id="sk1-t" d="M9 21 L17 29 L31 12"/></svg><i class="ring"></i><i class="dots" id="sk1-d"></i></span><span class="lbl" id="sk1-l">CHARACTER INCONSISTENCIES”</span></div></div>`);
  tw.push(`tl.fromTo("#seam2",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:0.3,ease:"power4.out",immediateRender:false},${tNo});`,
          `tl.fromTo("#strip",{scaleY:0.02,opacity:1},{scaleY:1,opacity:1,duration:0.3,ease:"power3.out",immediateRender:false},${tAnn});`, `tl.set("#seam2",{opacity:0},${tAnn + 0.1});`,
          `WATER("#sk0",${tAnn + 0.2});`, `WATER("#sk1",${tAnn + 0.3});`,
          `JITTER("#sk0-l",${tV},${tD});`, `CHECK("#sk0",${tD},0,null);`, `WEIGHTS("#sk1-l",${tC},${tI});`, `CHECK("#sk1",${tI},0,null);`,
          `tl.to("#strip",{scaleY:0.02,duration:0.2,ease:"power2.in"},${out});`, `tl.to("#strip",{scaleX:0,duration:0.15,ease:"power2.in"},${out + 0.07});`, `tl.set("#strip",{opacity:0},${out + 0.23});`);
  PUNCH(tD, 1.04); PUNCH(tI, 1.04);
  hit("thud", tAnn, 0.38); hit("ding", tD, 0.26); hit("ding", tI, 0.26);
  say(tNo - 0.2, out, "no more annoying things like vocal drift character inconsistencies");
}

// =============================================================================
// WEARING / HOLDING / INTERACTING three slams over the example [60.75-63.50]
// =============================================================================
{
  const t = [61.05, 61.80, 62.40], out = 63.50;
  html.push(`<div id="whi" class="persp" data-layout-allow-overlap style="left:0;top:40px;width:1080px;height:260px"><div class="bigword" id="w0" style="font-size:130px">WEARING</div><div class="bigword" id="w1" style="font-size:130px">HOLDING</div><div class="bigword" id="w2" style="font-size:112px">INTERACTING</div></div>`);
  tw.push(`tl.fromTo("#w0",{x:-320,opacity:0},{x:0,opacity:1,duration:0.45,ease:"expo.out",immediateRender:false},${t[0]});`,
          `tl.to("#w0",{rotationX:-90,y:-60,opacity:0,duration:0.12,ease:"power2.in"},${t[1]});`, `tl.set("#w0",{opacity:0},${t[1] + 0.21});`,
          `tl.fromTo("#w1",{y:90,rotation:6,opacity:0},{y:0,rotation:0,opacity:1,duration:0.4,ease:"circ.out",immediateRender:false},${t[1]});`,
          `tl.to("#w1",{rotationX:-90,y:-60,opacity:0,duration:0.12,ease:"power2.in"},${t[2]});`, `tl.set("#w1",{opacity:0},${t[2] + 0.21});`,
          `tl.fromTo("#w2",{scale:1.5,opacity:0,filter:"blur(16px)"},{scale:1,opacity:1,filter:"blur(0px)",duration:0.45,ease:"power4.out",immediateRender:false},${t[2]});`,
          `tl.to("#whi",{y:-400,duration:0.2,ease:"power3.in"},${out});`, `tl.set("#whi",{opacity:0},${out + 0.21});`);
  PUNCH(t[0], 1.03, 0.4); PUNCH(t[1] + 0.02, 1.05, 0.2); PUNCH(t[2] + 0.02, 1.08, 0.5);
  hit("thud", t[0], 0.40); hit("click", t[1], 0.22); hit("thud", t[2], 0.40);
  say(t[0] - 0.2, out, "wearing holding or interacting");
}

// =============================================================================
// STYLES RAIL with a number wheel [63.66-78.70]
// =============================================================================
{
  const tIn = 63.66, out = 78.70;
  const ticks = [[W("podcast"), "PODCAST"], [W("street"), "STREET INTERVIEW"], [W("claymation"), "CLAYMATION"], [W("cinematic"), "CINEMATIC"], [W("whiteboard"), "WHITEBOARD"], [W("Pixar"), "PIXAR"], [W("Lego"), "LEGO"], [W("anything", 1), "“ANYTHING"], [W("dream"), "YOU CAN DREAM UP”"]];
  const wheel = ["00", "01", "02", "03", "04", "05", "06", "07", "∞"];
  html.push(`<div id="rail" class="rail" data-layout-allow-overlap><span class="kick mono">STYLE</span><div class="wheel mono"><div class="wheel-in" id="wheel-in">${wheel.map((w) => `<b>${w}</b>`).join("")}</div></div><div class="slot" id="slot">${ticks.map(([, n], i) => `<div class="ln sl" data-layout-allow-overlap id="sl${i}">${n === "" ? `<i class="bar"></i>` : esc(n)}</div>`).join("")}</div></div>`);
  tw.push(`tl.fromTo("#rail",{yPercent:-110,opacity:1},{yPercent:0,opacity:1,duration:0.3,ease:"power3.out",immediateRender:false},${tIn});`);
  ticks.forEach(([t], i) => {
    const step = i < 7 ? i + 1 : 8;
    tw.push(`tl.to("#wheel-in",{y:${-step * 130},duration:0.4,ease:"back.out(1.8)"},${t});`, `SLOTSWAP("#slot",${i},${t});`);
    if (i !== 8 || true) PUNCH(t, i === 8 ? 1.06 : 1.03, 0.4);
  });
  tw.push(`SHEENRAIL("#rail",${W("dream")});`, `tl.to("#rail",{yPercent:-110,duration:0.3,ease:"power3.in"},${out});`, `tl.set("#rail",{opacity:0},${out + 0.31});`);
  hit("swipe", tIn, 0.24); [0, 1, 2, 3, 4, 5, 6].forEach((i) => hit("click", ticks[i][0], 0.22)); hit("click", ticks[7][0], 0.24); hit("shimmer", ticks[8][0], 0.30);
  ticks.forEach(([t, n], i) => { if (n) say(t - 0.15, i + 1 < ticks.length ? ticks[i + 1][0] : out, n.replace(/[“”]/g, "")); });
}

// =============================================================================
// THE FRAME closes in (no text) [82.00-83.67] -> N11 generated b-roll inside the frame [83.67-85.59]
// =============================================================================
{
  const tF = 82.00, tHum = W("humans"), tIts = WS("26-elevating", "It's"), tAb = WS("26-elevating", "about"), tCr = W("creativity"), tCreate = W("create"), tOutMove = W("create");
  html.push(`<i class="fbar" id="fb0" style="left:40px;top:40px;width:1000px;height:3px;transform-origin:0 50%"></i><i class="fbar" id="fb1" style="left:1037px;top:40px;width:3px;height:1840px;transform-origin:50% 0"></i><i class="fbar" id="fb2" style="left:40px;top:1877px;width:1000px;height:3px;transform-origin:100% 50%"></i><i class="fbar" id="fb3" style="left:40px;top:40px;width:3px;height:1840px;transform-origin:50% 100%"></i>`);
  html.push(`<div id="tk-broll" class="tkwrap" data-layout-allow-overlap><div class="tkin" id="tk-broll-in"><video id="broll-v" src="assets/broll-elevate-1080.mp4" data-start="${tIts}" data-duration="${f3(tCreate + 0.1 - tIts)}" data-media-start="2.0" muted playsinline></video></div>
    <div class="chip ink mono" id="brchip" style="left:auto;right:60px;top:1560px">SEEDANCE 2.5 · GENERATED IN ARCADS</div></div>`);
  tw.push(`tl.fromTo("#fb0",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:0.24,ease:"power2.inOut",immediateRender:false},${tF});`,
          `tl.fromTo("#fb1",{scaleY:0,opacity:1},{scaleY:1,opacity:1,duration:0.24,ease:"power2.inOut",immediateRender:false},${tF + 0.24});`,
          `tl.fromTo("#fb2",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:0.24,ease:"power2.inOut",immediateRender:false},${tF + 0.48});`,
          `tl.fromTo("#fb3",{scaleY:0,opacity:1},{scaleY:1,opacity:1,duration:0.24,ease:"power2.inOut",immediateRender:false},${tF + 0.72});`,
          `tl.set("#base",{transformOrigin:"${ORIGIN["25-nothumans"][0]}px ${ORIGIN["25-nothumans"][1]}px"},${tF - 0.002});`,
          `tl.fromTo("#base",{scale:1},{scale:1.05,duration:${f3(tIts - tF)},ease:"none",immediateRender:false},${tF});`,
          // frame -> cover -> frame: bars grow to the centre, swap under cover, thin back
          `tl.to("#fb0",{scaleY:${1877 / 3 / 2},transformOrigin:"50% 0",duration:0.22,ease:"power3.in"},${tIts});`, `tl.to("#fb2",{scaleY:${1877 / 3 / 2},transformOrigin:"50% 100%",duration:0.22,ease:"power3.in"},${tIts});`,
          `tl.set("#tk-broll",{opacity:1},${tIts + 0.18});`, `tl.set("#base",{scale:1},${tIts + 0.19});`,
          `tl.to("#fb0",{scaleY:1,duration:0.28,ease:"power3.out"},${tAb});`, `tl.to("#fb2",{scaleY:1,duration:0.28,ease:"power3.out"},${tAb});`,
          `tl.fromTo("#tk-broll-in",{scale:1},{scale:1.06,duration:${f3(tCreate - tIts)},ease:"none",immediateRender:false},${tIts + 0.18});`,
          `tl.fromTo("#brchip",{x:200,opacity:0},{x:0,opacity:1,duration:0.3,ease:"expo.out",immediateRender:false},${tCr});`,
          `tl.to("#fb0",{scaleY:${1877 / 3 / 2},duration:0.13,ease:"power3.in"},${tCreate - 0.13});`, `tl.to("#fb2",{scaleY:${1877 / 3 / 2},duration:0.13,ease:"power3.in"},${tCreate - 0.13});`,
          `tl.set("#tk-broll",{opacity:0},${tCreate});`,
          `tl.set("#base",{scale:1.06,transformOrigin:"${ORIGIN["26-elevating"][0]}px ${ORIGIN["26-elevating"][1]}px"},${tCreate});`, `tl.to("#base",{scale:1,duration:0.45,ease:"power2.out"},${tCreate + 0.01});`,
          `tl.to("#fb0",{y:-1100,duration:0.25,ease:"power3.in"},${tCreate});`, `tl.to("#fb2",{y:1100,duration:0.25,ease:"power3.in"},${tCreate});`, `tl.to("#fb1",{x:1100,duration:0.25,ease:"power3.in"},${tCreate});`, `tl.to("#fb3",{x:-1100,duration:0.25,ease:"power3.in"},${tCreate});`,
          `tl.set(".fbar",{opacity:0},${tCreate + 0.26});`);
  hit("click", tHum, 0.22); hit("sub", tIts, 0.34); hit("pop", tCr, 0.30); hit("thud", tCreate, 0.42);
}

// =============================================================================
// N12. THE MONTAGE, cleaned up: wall with the creator in the centre, three hard cuts, four words in a fixed column
// =============================================================================
{
  const tWall = W("never"), tWithout = W("without"), tIns = W("insane"), tCre = W("creative"), tBud = W("budgets"), tBl = 89.30, CUT = 89.367;
  const tiles = ["mute-button-cartoon", "anime-vs.-the-algorithm", "burn-rate-anime", "pixel-perfect-lego", "algorithm-fuel-claymation", "lookalike-audience-vhs", "pixel-perfect-comic", "conversion-cola-claymation", "roas-ring-pixar"];
  const tms = [4.0, 0.7, 4.0, 4.0, 4.0, 0.7, 4.0, 4.0, 4.0];
  html.push(`<div id="tk-wall" class="tk low" data-layout-allow-overlap>${tiles.map((c, i) => { const col = i % 3, row = Math.floor(i / 3); return `<div class="vcard wl" id="wl${i}" style="left:${10 + col * 360}px;top:${40 + row * 620}px;width:340px;height:600px"><video id="wl${i}-v" src="assets/clips-half/${c}.mp4" data-start="${tWall}" data-duration="${f3(CUT + 0.1 - tWall)}" data-media-start="${tms[i]}" muted playsinline></video></div>`; }).join("")}</div>`);
  const heroes = [["mute-button-cartoon", tIns, tCre, 4.4], ["burn-rate-anime", tBud, CUT + 0.05, 4.0]];
  html.push(`<div id="tk-hero" class="tk low" data-layout-allow-overlap style="z-index:31">${heroes.map(([c, a, b, m], i) => `<div class="hero-v" id="hv${i}"><video id="hv${i}-v" src="assets/clips/${c}.mp4" data-start="${f3(a)}" data-duration="${f3(b - a + 0.1)}" data-media-start="${m}" muted playsinline></video></div>`).join("")}</div>`);
  html.push(`<div id="stack" class="stack" data-layout-allow-overlap>${["WITHOUT", "INSANE", "CREATIVE", "BUDGETS"].map((w, i) => `<div class="bigword extrude sw" id="sw${i}" style="top:${1290 + i * 130}px;left:0;width:1020px;font-size:110px;text-align:right"><b>${w}</b><b data-layout-allow-overlap>${w}</b><b data-layout-allow-overlap>${w}</b><b data-layout-allow-overlap>${w}</b></div>`).join("")}</div>`);
  const tile = rf(0.5, FACE.elev26, [540, 960]), pip = rf(S_PIP, FACE.elev26, PIP.face);
  tw.push(`tl.set("#tk-wall",{opacity:1},${tWall - 0.01});`, `tl.set("#tk-hero",{opacity:1},${tWall - 0.01});`);
  tiles.forEach((_, i) => tw.push(`tl.fromTo("#wl${i}",{y:40,opacity:0},{y:0,opacity:1,duration:0.3,ease:"power3.out",immediateRender:false},${f3(tWall + i * 0.04)});`));
  tw.push(`tl.to("#vclip",{clipPath:"inset(660px 370px 660px 370px)",duration:0.35,ease:"power3.inOut"},${tWall});`,
          `tl.to("#vwrap",{scale:${tile.scale},x:${tile.x},y:${tile.y},duration:0.35,ease:"power3.inOut"},${tWall});`,
          `SLAMW("#sw0",${tWithout});`,
          `tl.set("#hv0",{opacity:1},${tIns});`, `tl.set("#tk-wall",{opacity:0},${tIns});`,
          `tl.set("#vclip",{clipPath:"circle(${PIP.r}px at ${PIP.cx}px ${PIP.cy}px)"},${tIns});`, `tl.set("#vwrap",{scale:${pip.scale},x:${pip.x},y:${pip.y}},${tIns});`, `tl.set("#pipring",{opacity:1},${tIns});`,
          `SLAMW("#sw1",${tIns});`,
          `tl.set("#hv0",{opacity:0},${tCre});`, `tl.set("#tk-wall",{opacity:1},${tCre});`, `SLAMW("#sw2",${tCre});`,
          `tl.set("#tk-wall",{opacity:0},${tBud});`, `tl.set("#hv1",{opacity:1},${tBud});`, `SLAMW("#sw3",${tBud});`,
          `BLINDS(${tBl},${CUT + 0.36});`,
          `tl.set("#vclip",{clipPath:"none"},${f3(CUT - 0.006)});`, `tl.set("#vwrap",{scale:1,x:0,y:0},${f3(CUT - 0.006)});`, `tl.set("#pipring",{opacity:0},${f3(CUT - 0.006)});`,
          `tl.set("#tk-wall",{opacity:0},${f3(CUT - 0.006)});`, `tl.set("#tk-hero",{opacity:0},${f3(CUT - 0.006)});`, `tl.set("#stack",{opacity:0},${f3(CUT - 0.006)});`);
  capBand.push([tIns, CUT, 1296, false]);
  hit("thud", tWall, 0.40); hit("thud", tWithout, 0.42); hit("click", tIns, 0.24); hit("thud", tCre, 0.36); hit("thud", tBud, 0.42); hit("swipe", tBl, 0.24);
  say(tWithout - 0.2, CUT, "without insane creative budgets");
}

// =============================================================================
// N13. END CARD on the seam, border drawn, seam docked [89.42-93.40]
// =============================================================================
{
  const tLink = W("link"), tTool = W("tool"), tCom = W("comment"), tAds = WS("27-cta", "ads"), tSend = W("send");
  html.push(`<i id="seamL" class="seamline half" style="left:0;width:360px;transform-origin:0 50%"></i><i id="seamR" class="seamline half" style="left:720px;width:360px;transform-origin:100% 50%"></i>
    <div id="endbox" class="endbox"><svg class="absvg" viewBox="0 0 340 340" width="340" height="340"><rect id="eb-r" x="6" y="6" width="328" height="328" fill="none" stroke="#0E0E10" stroke-width="12"/></svg><img src="assets/arcads-mark.png" alt="Arcads" /><div class="ecu sheen" id="eb-u">arcads.ai</div></div>
    <div id="cchip" class="chip ink mono" style="left:750px;top:905px"><span id="cchip-t"></span><i class="caret" id="cchip-c"></i></div>`);
  tw.push(`tl.fromTo("#seamL",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:0.34,ease:"power4.out",immediateRender:false},${tLink});`, `tl.fromTo("#seamR",{scaleX:0,opacity:1},{scaleX:1,opacity:1,duration:0.34,ease:"power4.out",immediateRender:false},${tLink});`,
          `tl.fromTo("#endbox",{scale:0,opacity:1},{scale:1,opacity:1,duration:0.34,ease:"back.out(1.6)",immediateRender:false},${tTool});`, `DRAWP("#eb-r",${tTool},0.6);`,
          `tl.to("#seamL",{scaleX:1.083,duration:0.2},${tTool + 0.5});`, `tl.to("#seamR",{scaleX:1.083,duration:0.2},${tTool + 0.5});`,
          `WATER("#eb-u",${tTool + 0.2});`, `SHEEN("#eb-u",${tTool + 0.35});`,
          `tl.fromTo("#cchip",{opacity:0,y:-30},{opacity:1,y:0,duration:0.25,ease:"power3.out",immediateRender:false},${tCom});`,
          `TYPE("#cchip-t",[[0,"A"],[0.05,"AI"],[${f3(tAds - tCom)}," ads"]],${tCom + 0.02},${tAds + 0.2});`, `BLINK("#cchip-c",${tCom},${tSend});`,
          `tl.to("#cchip",{y:-1200,rotation:-3,duration:0.35,ease:"power3.in"},${tSend});`, `tl.set("#cchip",{opacity:0},${tSend + 0.36});`,
          `tl.fromTo("#endbox",{scale:1},{scale:1.03,duration:${f3(DUR - 91.2)},ease:"none",immediateRender:false},91.2);`,
          `tl.set("#base",{transformOrigin:"${ORIGIN["27-cta"][0]}px ${ORIGIN["27-cta"][1]}px"},91.198);`, `tl.fromTo("#base",{scale:1},{scale:1.03,duration:${f3(DUR - 91.2)},ease:"none",immediateRender:false},91.2);`);
  PUNCH(tTool, 1.05);
  hit("click", tLink, 0.22); hit("pop", tTool, 0.30); hit("shimmer", tTool, 0.30); hit("ding", tSend, 0.26);
}
// the "AI ads" chip mirrors the creator's locked VO; the TYPE call above types "AI" then " ads" in two clusters
// (fix the text sequence: first cluster "AI", second " ads")
{
  const i = tw.findIndex((s) => s.startsWith('TYPE("#cchip-t"'));
  const tCom = W("comment"), tAds = WS("27-cta", "ads");
  tw[i] = `TYPE("#cchip-t",[[0,"A"],[0.06,"AI"],[${f3(tAds - tCom)},"AI ad"],[${f3(tAds - tCom + 0.08)},"AI ads"]],${tCom + 0.02},${tAds + 0.2});`;
}

// =============================================================================
// captions: chunks -> clips; band + inversion + muting by window
// =============================================================================
const PLAIN = new Set(["24-99pct"]);
const chunks = [];
for (const w of words) {
  const last = chunks[chunks.length - 1];
  const sid = shotAt(w.start);
  const gap = last ? w.start - last.words.at(-1).end : 0;
  if (!last || last.sid !== sid || last.words.length >= 3 || gap > 0.22 || w.end - last.words[0].start > 1.5) chunks.push({ sid, words: [w] });
  else last.words.push(w);
}
chunks.forEach((c) => { c.start = c.words[0].start; });
chunks.forEach((c, i) => {
  const nextStart = i + 1 < chunks.length ? chunks[i + 1].start : c.words.at(-1).end + 0.5;
  c.end = Math.min(nextStart, c.words.at(-1).end + 0.45);
  if (c.end <= c.start + 0.12) c.end = c.start + 0.12;
  c.plain = PLAIN.has(c.sid); c.layout = free[c.sid].layout;
});
const STOP = new Set(["the", "and", "you", "for", "with", "that", "this", "are", "was", "out", "its", "all", "can", "not", "but", "have", "has", "had", "from", "your", "they", "them", "then", "than", "what", "now", "just", "like", "about", "into", "over", "some", "more", "were", "been", "will", "would", "could"]);
const sig = (t) => t.toLowerCase().replace(/[^a-z0-9]/g, "");
for (const c of chunks) {
  const mine = c.words.map((w) => sig(w.text)).filter((w) => w.length >= 3 && !STOP.has(w));
  c.mute = spans.some((s) => c.start < s.b && c.words.at(-1).end > s.a && mine.some((w) => s.text.split(/\s+/).map(sig).includes(w)));
  const band = capBand.find(([a, b]) => c.start >= a && c.start < b);
  c.y = band ? band[2] : (c.layout === "screen" ? 1296 : 1690);
  c.inv = band ? band[3] : false;
}
for (const [i, c] of chunks.entries()) {
  if (c.mute) continue;
  html.push(`<div id="cap${i}" class="clip cap${c.plain ? " plain" : ""}${c.inv ? " inv" : ""}" data-start="${(c.start - 0.05).toFixed(3)}" data-duration="${(c.end - c.start).toFixed(3)}" style="top:${c.y}px">` +
    c.words.map((w, j) => `<b id="cap${i}w${j}">${esc(w.text)}</b>`).join(" ") + `</div>`);
  tw.push(`CAP("#cap${i}",${c.start});`);
  if (!c.plain) c.words.forEach((w, j) => tw.push(`HIT("#cap${i}w${j}",${w.start},${Math.max(0.1, w.end - w.start)});`));
}

// =============================================================================
// sound
// =============================================================================
hits.sort((a, b) => a.t - b.t);
const audio = hits.map((h, i) => `<audio id="sfx${i}" src="assets/sfx/${h.name}.mp3" data-start="${h.t}" data-duration="${Math.min(sfxDur[h.name], DUR - h.t).toFixed(3)}" data-track-index="${20 + i}" data-volume="${h.vol}"></audio>`);
audio.unshift(`<audio id="bed" src="assets/bed-v8.mp3" data-start="0" data-duration="93.4" data-track-index="12" data-volume="0.24"></audio>`);

// =============================================================================
// page
// =============================================================================
const CSS = `
@font-face{font-family:"InterV";src:url("assets/fonts/inter.woff2") format("woff2");font-weight:100 900;font-style:normal;font-display:block}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0E0E10;font-family:"InterV",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0E0E10;perspective:1400px}
#vclip{position:absolute;inset:0;width:1080px;height:1920px;z-index:35;overflow:hidden;clip-path:circle(2200px at 250px 1608px)}
#vwrap{position:absolute;inset:0;width:1080px;height:1920px;transform-origin:50% 50%}
#base{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;transform-origin:540px 700px}
#prog{position:absolute;left:0;top:0;height:5px;width:1080px;background:#F4F2EE;transform-origin:0 50%;z-index:60}
.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-weight:600;letter-spacing:0}
.absvg{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:0}
.ring{position:absolute;opacity:0;border-radius:24px;box-shadow:0 0 0 6px #0E0E10,0 0 0 12px #F4F2EE;z-index:36;pointer-events:none}
.pipring{position:absolute;left:${PIP.cx - 202}px;top:${PIP.cy - 202}px;width:404px;height:404px;border-radius:50%;box-shadow:0 0 0 5px #0E0E10,0 0 0 11px #F4F2EE;opacity:0;z-index:36}
.pipring i{position:absolute;inset:8px;border-radius:50%;background:#F4F2EE;opacity:0}
/* plates + type */
.plate{position:absolute;opacity:0;padding:26px 32px 30px;letter-spacing:-0.035em;line-height:0.94;font-weight:800;text-transform:uppercase;z-index:40}
.plate.cream{background:#F4F2EE;color:#0E0E10}
.plate.ink{background:#0E0E10;color:#F4F2EE;box-shadow:inset 0 0 0 2px rgba(244,242,238,.30)}
.ln{opacity:0;display:block;white-space:nowrap}
.lnwrap{position:relative;display:block;height:1.02em;overflow:hidden}.lnwrap .ln{position:absolute;left:0;top:0}
.quoteplate{overflow:visible}.q{position:absolute;font-size:120px;font-weight:900;line-height:1;opacity:0;font-family:"InterV";text-transform:none}
.ql{left:-40px;top:-46px}.qr{right:-34px;bottom:-70px}.plate.ink .q{color:#F4F2EE}.plate.cream .q{color:#0E0E10}
.bigword{position:absolute;left:0;width:1080px;text-align:center;font-weight:900;letter-spacing:-0.03em;line-height:1;color:#F4F2EE;opacity:0;text-transform:uppercase;z-index:47}
#withai span{display:inline-block;background:#0E0E10;padding:10px 40px 16px;box-shadow:0 0 0 5px #F4F2EE}
.extrude{position:relative;display:inline-block}.extrude b{font-weight:inherit;display:block}.extrude b+b{position:absolute;left:0;top:0;width:100%;opacity:0;pointer-events:none}
.hero{position:absolute;left:0;width:1080px;text-align:center;font-size:150px;font-weight:900;letter-spacing:-0.03em;line-height:1;color:#F4F2EE;text-transform:uppercase;opacity:0}
.plate.cream .hero{color:#0E0E10}
.kicker{position:absolute;left:0;width:1080px;text-align:center;font-family:ui-monospace,Menlo,monospace;font-size:26px;letter-spacing:.16em;opacity:0;color:#F4F2EE}
.kicker.rel{position:relative;text-align:left;width:auto;margin-bottom:14px}
.counter{position:absolute;font-size:44px;color:#F4F2EE;opacity:0;font-variant-numeric:tabular-nums}
/* chips */
.chip{position:absolute;opacity:0;padding:16px 28px;font-size:38px;font-weight:750;letter-spacing:-0.02em;z-index:45;white-space:nowrap;text-transform:uppercase}
.chip.cream{background:#F4F2EE;color:#0E0E10}.chip.ink{background:#0E0E10;color:#F4F2EE;box-shadow:inset 0 0 0 2px rgba(244,242,238,.30)}
.chip.mono{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-weight:600;letter-spacing:0;text-transform:none}
.chip.hang{transform-origin:50% 0;z-index:47}
.bubble{font-size:44px;padding:14px 30px;z-index:47}.bubble .tail{position:absolute;left:50%;bottom:-13px;width:26px;height:26px;background:#F4F2EE;transform:translateX(-50%) rotate(45deg)}
.sheen{background-image:linear-gradient(100deg,currentColor 0%,currentColor 40%,rgba(128,128,128,.35) 50%,currentColor 60%,currentColor 100%);background-size:300% 100%;background-position:100% 50%;-webkit-background-clip:text;background-clip:text}
.plus{position:absolute;left:376px;top:964px;font-size:56px;font-weight:300;color:#F4F2EE;opacity:0;z-index:47;line-height:1;transform-origin:50% 50%}
.persp{position:absolute;left:0;top:0;width:1080px;height:1920px;perspective:1200px;z-index:47;pointer-events:none}.persp .chip{backface-visibility:hidden}
/* video cards */
.vcard{position:absolute;overflow:hidden;opacity:0;will-change:transform;box-shadow:0 0 0 4px #0E0E10,0 0 0 8px #F4F2EE;z-index:44;transform-style:preserve-3d;background:#0E0E10}
.vcard video,.vcard img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.vcard .vin{position:absolute;inset:0;opacity:0}
/* fields + takeovers */
.field{position:absolute;inset:0;background:#0E0E10;opacity:0;z-index:30;overflow:hidden}
.grid{position:absolute;inset:-120px;background-image:linear-gradient(rgba(244,242,238,.16) 1px,transparent 1px),linear-gradient(90deg,rgba(244,242,238,.16) 1px,transparent 1px);background-size:90px 90px;display:block}
.grid.dots{background-image:radial-gradient(rgba(244,242,238,.28) 1.5px,transparent 1.6px);background-size:60px 60px}
.scan{position:absolute;left:0;top:-160px;width:1080px;height:160px;background:linear-gradient(180deg,rgba(244,242,238,0),rgba(244,242,238,.18),rgba(244,242,238,0));display:block}
.tk{position:absolute;inset:0;background:#0E0E10;color:#F4F2EE;overflow:hidden;opacity:0;z-index:46;will-change:transform,clip-path}
.tk.low{z-index:30}
.tkwrap{position:absolute;inset:0;opacity:0;z-index:46;overflow:hidden}.tkin{position:absolute;inset:0;transform-origin:50% 50%}.tkin video{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}
.br{position:absolute;left:40px;top:40px;width:120px;height:120px;border-top:6px solid #F4F2EE;border-left:6px solid #F4F2EE;opacity:0}
#br1{border-left:0;border-right:6px solid #F4F2EE}#br2{border-top:0;border-bottom:6px solid #F4F2EE}#br3{border-top:0;border-left:0;border-right:6px solid #F4F2EE;border-bottom:6px solid #F4F2EE}
.rows{position:absolute;left:100px;top:560px;width:880px}
.tg{display:flex;align-items:center;gap:28px;font-size:60px;font-weight:800;letter-spacing:-.03em;opacity:0;height:118px}
.tg-name{flex:1;white-space:nowrap}.tg-track{position:relative;width:136px;height:72px;box-shadow:inset 0 0 0 4px #F4F2EE;background:#0E0E10;flex:0 0 136px}
.tg-knob{position:absolute;left:10px;top:10px;width:52px;height:52px;background:#F4F2EE;display:block}
.tg-ring{position:absolute;left:36px;top:36px;width:52px;height:52px;border:3px solid #F4F2EE;border-radius:50%;transform:translate(-50%,-50%) scale(0);opacity:0;display:block}
.tg-st{position:relative;width:110px;font-size:32px}.tg-st b{position:absolute;left:0;top:-18px;font-weight:600}.tg-st .on{opacity:0}
.footchip{position:absolute;left:60px;bottom:330px;display:flex;align-items:center;gap:16px;background:#F4F2EE;color:#0E0E10;padding:14px 26px;font-weight:800;font-size:34px;opacity:0;transform-origin:50% 50%}.footchip img{width:40px;height:40px}
.seamline{position:absolute;left:0;top:958px;width:1080px;height:4px;background:#F4F2EE;opacity:0;z-index:47;display:block}
.node{position:absolute;display:flex;align-items:center;gap:14px;background:#F4F2EE;color:#0E0E10;padding:16px 28px;font-weight:800;font-size:38px;opacity:0;z-index:47;transform:translate(-50%,-50%);box-shadow:0 0 0 5px #0E0E10,0 0 0 9px #F4F2EE}.node img{width:40px;height:40px}
.persp3{position:absolute;inset:0;perspective:1400px;transform-style:preserve-3d;transform-origin:50% 40%}
.radar{position:absolute;width:120px;height:120px;border:3px solid #F4F2EE;border-radius:50%;transform:translate(-50%,-50%) scale(0);opacity:0;display:block}
.bignode{position:absolute;left:0;width:1080px;text-align:center;font-size:96px;font-weight:900;letter-spacing:-.03em;opacity:0;line-height:1}.bignode img{display:block;width:80px;height:80px;margin:0 auto 14px}
.halo{position:absolute;left:50%;top:50%;width:520px;height:520px;transform:translate(-50%,-50%);background:radial-gradient(circle,rgba(244,242,238,.35),rgba(244,242,238,0) 70%);opacity:0;display:block;pointer-events:none}
.pill{z-index:47;font-size:44px;padding:14px 34px;box-shadow:0 0 0 5px #0E0E10,0 0 0 9px #F4F2EE}
.term{position:absolute;left:60px;top:920px;width:960px;height:140px;font-size:30px;color:#F4F2EE;opacity:0;line-height:1.5}.term span{display:block;white-space:pre;min-height:44px}
.caret{position:absolute;width:16px;height:34px;background:#F4F2EE;display:inline-block;opacity:0;vertical-align:middle}
.promptcard{position:absolute;left:480px;top:1270px;width:540px;height:510px;overflow:hidden;font-size:22px;line-height:1.35;color:#F4F2EE;opacity:0;padding:22px 26px;box-shadow:inset 0 0 0 2px rgba(244,242,238,.35)}
.promptcard .pl{opacity:0;white-space:pre-wrap;word-break:break-word;margin-bottom:6px}
.pbar{position:absolute;right:8px;top:12px;width:6px;height:120px;background:#F4F2EE;opacity:.7;display:block;transform-origin:50% 0}
.quoteband{position:absolute;left:0;top:1100px;width:1080px;text-align:center;font-size:84px;font-weight:900;letter-spacing:-.03em;color:#F4F2EE;opacity:0;z-index:47;line-height:1;text-transform:uppercase}.quoteband .q{position:relative;font-size:84px;opacity:1;top:0;left:0;right:auto;bottom:auto;display:inline}
/* credits / checklist */
.bigcard{padding:34px 40px}
.crow{position:relative;display:flex;align-items:baseline;gap:28px;height:128px;padding-top:20px}
.hair{position:absolute;left:0;top:0;width:100%;height:2px;background:rgba(244,242,238,.5);transform-origin:0 50%;transform:scaleX(0);display:block}
.role{font-size:26px;letter-spacing:.14em;width:250px;opacity:0;flex:0 0 250px}
.name{font-size:76px;font-weight:900;letter-spacing:-.03em;opacity:0;white-space:nowrap;display:inline-flex;align-items:center;gap:16px}.name .mk{width:64px;height:64px}
.wave{position:absolute;right:40px;bottom:40px;display:flex;gap:6px;align-items:flex-end;height:60px;opacity:0}.wave i{width:10px;height:60px;background:#F4F2EE;display:block;transform-origin:50% 100%;transform:scaleY(.1)}
.face{backface-visibility:hidden;transform-style:preserve-3d}.back{opacity:0}
.ck{display:flex;align-items:center;gap:22px;padding:14px 0;font-size:64px;font-weight:800;letter-spacing:-.03em;opacity:0;position:relative}
.ck .bx{position:relative;width:64px;height:64px;box-shadow:inset 0 0 0 5px currentColor;display:block;flex:0 0 64px}
.ck .bxf{position:absolute;inset:8px;background:currentColor;transform:scaleY(0);transform-origin:50% 100%;display:block}
.ck svg{position:absolute;left:8px;top:8px;width:48px;height:48px}.tick{fill:none;stroke:#0E0E10;stroke-width:6;stroke-linecap:round;stroke-linejoin:round}
.plate.cream .tick,.strip .tick{stroke:#F4F2EE}
.ck .ring{position:absolute;left:50%;top:50%;width:64px;height:64px;border:3px solid currentColor;transform:translate(-50%,-50%) scale(0);opacity:0;display:block}
.ck .dots{position:absolute;left:32px;top:32px;display:block}.ck .dots i{position:absolute;left:0;top:0;width:8px;height:8px;background:currentColor;opacity:0;display:block}
.ck .lbl{white-space:nowrap}.ck.sm{font-size:40px;padding:0;gap:16px}.ck.sm .bx{width:52px;height:52px;flex:0 0 52px}.ck.sm svg{left:6px;top:6px;width:40px;height:40px}
.conic{position:absolute;right:30px;top:80px;opacity:0;transform:rotate(-90deg)}
.strip{position:absolute;left:0;top:875px;width:1080px;height:170px;background:#F4F2EE;color:#0E0E10;opacity:0;z-index:47;transform-origin:50% 50%;display:flex;align-items:center;gap:40px;padding:0 40px}
.strip .kick{position:absolute;left:40px;top:14px;font-size:20px;letter-spacing:.1em;opacity:.7}.strip .ck{margin-top:26px}
.slice{position:relative}
/* rail */
.rail{position:absolute;left:0;top:0;width:1080px;height:200px;background:#0E0E10;color:#F4F2EE;box-shadow:inset 0 0 0 2px rgba(244,242,238,.30);opacity:0;z-index:46;display:flex;align-items:center;gap:36px;padding:0 60px}
.rail .kick{font-size:24px;letter-spacing:.16em;opacity:.7}
.wheel{width:190px;height:130px;overflow:hidden;font-size:120px;font-weight:900;line-height:130px;font-variant-numeric:tabular-nums}.wheel-in b{display:block;height:130px}
.slot{position:relative;flex:1;height:90px;overflow:hidden;font-size:62px;font-weight:900;letter-spacing:-.03em;line-height:90px;text-transform:uppercase}.slot .sl{position:absolute;left:0;top:0;white-space:nowrap}
.slot .bar{display:block;width:120px;height:10px;background:#F4F2EE;margin-top:40px}
/* frame + montage + end */
.fbar{position:absolute;background:#F4F2EE;opacity:0;z-index:47;display:block}
#tk-hero{background:transparent}
.hero-v{position:absolute;inset:0;opacity:0}.hero-v video{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}
.stack{position:absolute;inset:0;z-index:47;pointer-events:none}.stack .sw b{-webkit-text-stroke:4px #0E0E10;paint-order:stroke fill}.stack .sw{top:880px;transform-origin:50% 50%}
.endbox{position:absolute;left:370px;top:770px;width:340px;height:340px;background:#F4F2EE;color:#0E0E10;opacity:0;z-index:47;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;transform-origin:50% 50%}
.endbox img{width:150px;height:150px;display:block}.endbox .absvg{width:340px;height:340px;opacity:1}.ecu{font-size:52px;font-weight:900;letter-spacing:-.04em;opacity:0}
.seamline.half{opacity:0;height:6px;top:957px;background:#0E0E10;box-shadow:0 0 0 2px #F4F2EE}
/* captions */
.cap{position:absolute;left:0;width:1080px;text-align:center;opacity:0;z-index:50;padding:0 60px;font-size:64px;font-weight:850;letter-spacing:-0.025em;text-transform:uppercase;color:#F4F2EE;line-height:1.06}
.cap b{opacity:.9;display:inline-block;font-weight:850;background:#0E0E10;padding:6px 14px;margin:0 -2px;box-shadow:0 0 0 4px #0E0E10;box-decoration-break:clone;-webkit-box-decoration-break:clone;transform-origin:50% 50%}
.cap.plain b{opacity:.95}
.cap.inv{color:#0E0E10}.cap.inv b{background:#F4F2EE;box-shadow:0 0 0 4px #F4F2EE}
.blind{position:absolute;left:0;width:1080px;height:240px;z-index:48;display:block}
`;

const JS = `
const tl = gsap.timeline({ paused: true });
const E = "power3.out";
const FT = (s,a,b,t) => tl.fromTo(s,a,{...b,immediateRender:false},t);
function SLAM(s,t){ FT(s,{scale:1.5,filter:"blur(16px)",opacity:0},{scale:1,filter:"blur(0px)",opacity:1,duration:.45,ease:"power4.out"},t); }
function SLAMW(s,t){ FT(s,{scale:1.5,filter:"blur(16px)",opacity:0},{scale:1,filter:"blur(0px)",opacity:1,duration:.4,ease:"power4.out"},t); EXTRUDE(s,t+.08); }
function QUOTES(a,b,t){ FT(a,{scale:0,opacity:0},{scale:1,opacity:1,duration:.25,ease:"back.out(1.6)"},t); FT(b,{scale:0,opacity:0},{scale:1,opacity:1,duration:.25,ease:"back.out(1.6)"},t+.06); }
function RISEW(s,t){ FT(s,{opacity:0,y:40},{opacity:1,y:0,duration:.2,ease:"power4.out"},t); }
function WATER(s,t){ tl.set(s,{opacity:1,y:80},t); tl.to(s,{y:0,duration:.18,ease:"power4.out"},t); }
function ROLL(a,b,t){ tl.to(a,{yPercent:-110,duration:.22,ease:"power3.inOut"},t); tl.set(a,{opacity:0},t+.23); FT(b,{opacity:1,yPercent:110},{opacity:1,yPercent:0,duration:.22,ease:"power3.inOut"},t); }
function HANG(s,t){ FT(s,{opacity:1,y:-60,clipPath:"inset(0 0 100% 0)"},{opacity:1,y:0,clipPath:"inset(0 0 0% 0)",duration:.3,ease:"back.out(1.4)"},t); }
function POPC(s,t){ FT(s,{opacity:0,scale:0},{opacity:1,scale:1,duration:.3,ease:"back.out(1.6)"},t); }
function OUTC(s,t){ tl.to(s,{opacity:0,duration:.16,ease:"power2.in"},t); tl.set(s,{opacity:0},t+.17); }
function UPOUT(s,t){ tl.to(s,{y:-260,duration:.25,ease:"power3.in"},t); tl.set(s,{opacity:0},t+.26); }
function GRAV(s,t){ tl.to(s,{y:2100,rotation:4,duration:.35,ease:"power3.in"},t); tl.set(s,{opacity:0},t+.36); }
function TICK(s,t){ FT(s,{x:0},{x:14,duration:.05,ease:"steps(2)"},t); tl.to(s,{x:-10,duration:.05,ease:"steps(2)"},t+.05); tl.to(s,{x:0,duration:.06,ease:"steps(2)"},t+.10); }
function EXTRUDE(s,t){ const copies=gsap.utils.toArray(s+" b").slice(1); copies.forEach((c,i)=>{ FT(c,{x:0,y:0,opacity:0},{x:(i+1)*3,y:(i+1)*3,opacity:.75-(i*.14),duration:.3,ease:"power3.out"},t+i*.03); }); }
function SHEEN(s,t){ FT(s,{backgroundPosition:"100% 50%"},{backgroundPosition:"0% 50%",duration:.6,ease:"none"},t); }
function SHEENRAIL(s,t){ FT(s,{filter:"brightness(1)"},{filter:"brightness(1.5)",duration:.12,yoyo:true,repeat:1},t); }
function DRAWP(sel,t,d){ const p=document.querySelector(sel); const L=p.getTotalLength()*1.02; p.style.strokeDasharray=L; p.style.strokeDashoffset=L; const par=p.closest("svg"); if(par) tl.set(par,{opacity:1},t-.001); tl.to(p,{strokeDashoffset:0,duration:d,ease:"power2.out"},t); }
function FLOW(sel,t0,t1){ const p=document.querySelector(sel); const st={o:0}; tl.to(st,{o:-22*Math.round((t1-t0)*8),duration:t1-t0,ease:"none",onUpdate:()=>{p.style.strokeDashoffset=st.o;}},t0); }
function PACKET(pathSel,dotSel,t,d,rev){ const p=document.querySelector(pathSel), dot=document.querySelector(dotSel), L=p.getTotalLength(); const s={t:0}; tl.fromTo(s,{t:0},{t:1,duration:d,ease:"power1.inOut",onUpdate:()=>{const u=rev?1-s.t:s.t; const pt=p.getPointAtLength(u*L); dot.setAttribute("cx",pt.x); dot.setAttribute("cy",pt.y); dot.setAttribute("opacity",(s.t>0&&s.t<1)?"1":"0");}},t); }
function RADAR(a,b,c,t){ [a,b,c].forEach((s,i)=>FT(s,{scale:0,opacity:.7},{scale:3.2,opacity:0,duration:.8,ease:"power2.out"},t+i*.1)); }
function HALO(s,t){ FT(s,{opacity:0},{opacity:.3,duration:.4,ease:"power2.out"},t); const ph={p:0}; tl.to(ph,{p:Math.PI*4,duration:3.4,ease:"none",onUpdate:()=>{document.querySelector(s).style.opacity=String(.3+Math.sin(ph.p)*.04);}},t+.4); }
function TOGGLE(id,t,n){ tl.to(id,{scale:.96,duration:.08,ease:"power1.in"},t); tl.to(id,{scale:1,duration:.32,ease:"back.out(1.6)"},t+.08);
  tl.to(id+" .tg-knob",{x:64,duration:.3,ease:"back.out(1.5)"},t+.06); tl.to(id+" .tg-track",{backgroundColor:"#F4F2EE",duration:.2,ease:"power2.out"},t+.06); tl.to(id+" .tg-knob",{backgroundColor:"#0E0E10",duration:.2},t+.06);
  FT(id+" .tg-ring",{scale:0,opacity:.8},{scale:2.6,opacity:0,duration:.55,ease:"power2.out"},t+.14); tl.set(id+" .off",{opacity:0},t+.18); tl.set(id+" .on",{opacity:1},t+.18);
  const st={v:n-1}; const el=document.getElementById("tkm-n"); tl.to(st,{v:n,duration:.15,ease:"none",onUpdate:()=>{el.textContent=String(Math.round(st.v));}},t+.1); }
const PARTS={};
function buildDots(hostSel){ const host=document.querySelector(hostSel+" .dots"); const arr=[]; for(let i=0;i<12;i++){ const d=document.createElement("i"); host.appendChild(d); const a=(i*2.399)%(Math.PI*2), sp=260+((i*37)%120); arr.push({el:d,vx:Math.cos(a)*sp,vy:Math.sin(a)*sp-260,spin:((i*53)%360)-180}); } PARTS[hostSel]=arr; }
function CHECK(id,t,n,counterSel){ if(!PARTS[id]) buildDots(id);
  tl.to(id+" .bx",{scale:.86,duration:.08,ease:"power1.in"},t); tl.to(id+" .bx",{scale:1,duration:.4,ease:"back.out(2)"},t+.08);
  FT(id+" .bxf",{scaleY:0},{scaleY:1,duration:.2,ease:"power3.out"},t+.06);
  const tk=document.querySelector(id+" .tick"); const L=tk.getTotalLength()*1.05; tk.style.strokeDasharray=L; tk.style.strokeDashoffset=L; tl.to(tk,{strokeDashoffset:0,duration:.28,ease:"power2.out"},t+.14);
  FT(id+" .ring",{scale:0,opacity:.9},{scale:3,opacity:0,duration:.6,ease:"power2.out"},t+.12);
  const parts=PARTS[id]; const d={T:0}; tl.fromTo(d,{T:0},{T:1,duration:.7,ease:"none",onUpdate:()=>{const s=d.T*.7; const fade=Math.min(1,(1-d.T)/.3); parts.forEach(p=>{p.el.style.transform="translate("+(p.vx*s)+"px,"+(p.vy*s+.5*1200*s*s)+"px) rotate("+(p.spin*s)+"deg)"; p.el.style.opacity=d.T===0||d.T>=1?"0":String(fade);});}},t+.12);
  tl.to(id+" .lbl",{opacity:.62,duration:.25},t+.4);
  if(counterSel){ const st={v:n-1}; const el=document.querySelector(counterSel); tl.to(st,{v:n,duration:.15,ease:"none",onUpdate:()=>{el.textContent=String(Math.round(st.v));}},t+.1); FT(counterSel,{scale:1},{scale:1.25,duration:.12,yoyo:true,repeat:1,ease:"power2.out"},t+.1); } }
function TYPE(sel,seq,t0,t1){ const el=document.querySelector(sel); const st={t:0}; const D=Math.max(.05,t1-t0); tl.to(st,{t:1,duration:D,ease:"none",onUpdate:()=>{const tt=st.t*D; let s=""; for(const [a,txt] of seq){ if(tt>=a) s=txt; } el.textContent=s;}},t0); }
function BLINK(sel,t0,t1){ const el=document.querySelector(sel); const ph={p:0}; const cyc=Math.max(1,Math.round((t1-t0)/.5)); tl.to(ph,{p:Math.PI*2*cyc,duration:t1-t0,ease:"none",onUpdate:()=>{el.style.opacity=Math.sin(ph.p)>0?"1":"0";}},t0); tl.set(el,{opacity:0},t1+.01); }
function STREAM(inner,bar,n,t0,t1){ const D=t1-t0; for(let i=0;i<n;i++){ const t=t0+D*(i/n); tl.set("#pl"+i,{opacity:1},t); } const el=document.querySelector(inner); const st={y:0}; tl.to(st,{y:1,duration:D,ease:"none",onUpdate:()=>{el.style.transform="translateY("+(-Math.max(0,(st.y*n-8))*36)+"px)";}},t0); FT(bar,{scaleY:1},{scaleY:.35},t0); tl.to(bar,{y:280,duration:D,ease:"none"},t0); }
function WAVE(t0,t1){ const els=[]; for(let i=0;i<8;i++) els.push(document.getElementById("wv"+i)); const ph={p:0}; tl.to(ph,{p:Math.PI*2*3,duration:t1-t0,ease:"none",onUpdate:()=>{els.forEach((e,i)=>{e.style.transform="scaleY("+(.15+Math.abs(Math.sin(ph.p+i*.9))*.85)+")";});}},t0); }
function TUMBLE(a,b,t){ tl.to(a,{rotationX:-90,y:-40,x:360,duration:.38,ease:"power2.inOut"},t); tl.set(a,{opacity:0},t+.39); tl.to(b,{x:-360,y:0,duration:.38,ease:"power2.inOut"},t); FT(b,{rotationX:0},{rotationX:0,duration:.01},t); }
function JITTER(sel,t0,t1){ const el=document.querySelector(sel); const st={a:1}; tl.fromTo(st,{a:1},{a:0,duration:t1-t0,ease:"none",onUpdate:()=>{const k=Math.floor(((st.a*1000)|0)/70)%3; el.style.transform="translateX("+((k-1)*12*st.a)+"px)";}},t0); tl.set(el,{x:0},t1+.01); }
function WEIGHTS(sel,t0,t1){ const el=document.querySelector(sel); const st={a:0}; tl.to(st,{a:1,duration:t1-t0,ease:"none",onUpdate:()=>{const k=Math.floor(st.a*12)%2; el.style.fontVariationSettings='"wght" '+(k?300:900);}},t0); tl.set(el,{fontVariationSettings:'"wght" 800'},t1+.01); }
function SLOTSWAP(host,i,t){ if(i>0){ tl.to("#sl"+(i-1),{yPercent:-120,duration:.22,ease:"power3.inOut"},t); tl.set("#sl"+(i-1),{opacity:0},t+.23);} FT("#sl"+i,{opacity:1,yPercent:120},{opacity:1,yPercent:0,duration:.22,ease:"power3.inOut"},t); }
function BLINDS(t0,t1,d=.22,st=.025){ const strips=gsap.utils.toArray(".blind"); strips.forEach((s,i)=>{ tl.to(s,{x:0,duration:d,ease:"power3.inOut"},t0+i*st); }); const mid=t0+d+7*st; strips.forEach((s,i)=>{ tl.to(s,{x:1080,duration:d,ease:"power3.inOut"},Math.max(mid+.02, t1-d-7*st)+i*st); }); strips.forEach((s)=>tl.set(s,{x:-1080},t1+.3)); }
function SLICEIN(sel,t){ const el=document.querySelector(sel); tl.set(el,{opacity:1,clipPath:"inset(0 0 0 0)"},t); const bands=5; for(let i=0;i<bands;i++){ const c=el.cloneNode(true); c.id=el.id+"-b"+i; c.querySelectorAll("[id]").forEach(n=>n.id=n.id+"-b"+i); c.style.clipPath="inset("+(i*20)+"% 0 "+((4-i)*20)+"% 0)"; c.style.zIndex=47; el.parentNode.appendChild(c); const dir=i%2?1:-1; FT(c,{x:dir*420,opacity:1},{x:0,opacity:1,duration:.3,ease:"steps(4)"},t); tl.set(c,{opacity:0},t+.32); } tl.set(el,{opacity:0},t-.001); tl.set(el,{opacity:1},t+.30); }
function WHIP(a,b,t){ tl.to(a,{filter:"blur(12px)",skewX:-8,x:-200,duration:.25,ease:"power3.in"},t); tl.set(a,{opacity:0,filter:"none",skewX:0,x:0},t+.26); FT(b,{filter:"blur(12px)",skewX:8,x:200,opacity:0},{filter:"blur(0px)",skewX:0,x:0,opacity:1,duration:.25,ease:"power3.out"},t+.1); }
function STACKTO(sel,i,t){ tl.to(sel,{scale:.28,x:-300,y:-834+i*54,duration:.3,ease:"power3.inOut"},t); }
function CAP(s,a){ FT(s,{opacity:0,y:14},{opacity:1,y:0,duration:.12,ease:E},a); }
function HIT(s,t,d){ tl.to(s,{opacity:1,duration:.06},t); FT(s,{scale:.92},{scale:1,duration:.18,ease:"back.out(2)"},t); tl.to(s,{opacity:0.9,duration:.1},t+Math.max(.12,d)); }
gsap.set(".blind",{x:-1080});
FT("#prog",{scaleX:0},{scaleX:1,duration:${DUR},ease:"none"},0);
tl.set("#base",{transformOrigin:"550px 700px"},0);
FT("#base",{scale:1.12},{scale:1,duration:.7,ease:"power3.out"},0);
`;

const blinds = Array.from({ length: 8 }, (_, i) => `<i class="blind" style="top:${i * 240}px;background:${i % 2 ? "#F4F2EE" : "#0E0E10"}"></i>`).join("");

const out = `<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<title>Arcads ad — V7</title>
<script src="assets/gsap.min.js"></script>
<style>${CSS}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="1920" data-duration="${DUR}">
  <div id="vclip"><div id="vwrap"><video id="base" src="assets/base.mp4" data-start="0" data-duration="${DUR}" muted playsinline></video></div></div>
  <audio id="base-a" src="assets/base.mp4" data-start="0" data-duration="${DUR}" data-volume="1"></audio>
  <i id="prog"></i>
${html.map((h) => "  " + h).join("\n")}
  ${blinds}
${audio.map((h) => "  " + h).join("\n")}
</div>
<script>
${JS}
${tw.join("\n")}
tl.set("#base",{scale:1},${DUR - 0.01});
window.__timelines["main"] = tl;
</script>
</body>
</html>
`;
fs.writeFileSync(R("mg/comp/index.html"), out);
console.log(`v7: html ${html.length} nodes, tweens ${tw.length}, captions ${chunks.filter((c) => !c.mute).length}/${chunks.length}, sfx ${hits.length}`);

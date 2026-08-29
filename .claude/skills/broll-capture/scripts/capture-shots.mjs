import puppeteer from "puppeteer";
import fs from "fs";

const OUT = process.env.SHOTS_DIR || "assets/shots";
fs.mkdirSync(OUT, { recursive: true });

const TARGETS = [
  { name: "example-home", url: "https://example.com", h: 2400 },  // EDIT: your targets
];

const KILL = `
  {
  const sels_kill = ['[id*="cookie" i]','[class*="cookie" i]','[id*="consent" i]','[class*="consent" i]',
    '[class*="chat" i]','[class*="intercom" i]','[id*="banner" i]','[role="dialog"]','[class*="_9dgv"]'];
  for (const s of sels_kill) document.querySelectorAll(s).forEach(n => { try { n.style.setProperty('display','none','important'); } catch(e){} });
  }
`;

const browser = await puppeteer.launch({
  headless: "new",
  args: ["--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-features=IsolateOrigins,site-per-process"],
});

for (const t of TARGETS) {
  const page = await browser.newPage();
  await page.setUserAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36");
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  try {
    await page.goto(t.url, { waitUntil: "networkidle2", timeout: 60000 });
  } catch (e) {
    console.log(t.name, "NAV WARN", e.message);
  }
  await new Promise(r => setTimeout(r, 2500));
  await page.evaluate(KILL);
  // scroll to bottom to force lazy loads then back to top
  await page.evaluate(async () => {
    const step = 600;
    for (let y = 0; y < document.body.scrollHeight; y += step) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 90)); }
    window.scrollTo(0, 0);
  });
  await new Promise(r => setTimeout(r, 1200));
  await page.evaluate(KILL);
  const bodyH = await page.evaluate(() => document.body.scrollHeight);
  const clipH = Math.min(t.h, bodyH);
  await page.screenshot({ path: `${OUT}/${t.name}.png`, clip: { x: 0, y: 0, width: 1440, height: clipH } });
  const title = await page.title();
  console.log(t.name, "OK  bodyH=", bodyH, "clip=", clipH, "|", title);
  await page.close();
}
await browser.close();

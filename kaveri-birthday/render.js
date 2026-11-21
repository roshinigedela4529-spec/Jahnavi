// Deterministic frame renderer: steps scene.html through time and pipes frames to ffmpeg.
// usage: node render.js <outSegment.mp4> <startFrame> <endFrame> [port]
//        node render.js --stills <outDir> <t1,t2,...> [port]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');

(async () => {
  const args = process.argv.slice(2);
  const stills = args[0] === '--stills';
  const port = (stills ? args[3] : args[3]) || 8765;
  const browser = await chromium.launch({ args: ['--disable-web-security', '--force-color-profile=srgb'] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => { console.error('PAGE ERROR', e); process.exit(1); });
  await page.goto(`http://127.0.0.1:${port}/scene.html`);
  await page.evaluate(() => window.__ready);
  const grab = async t => {
    const b64 = await page.evaluate(t => { renderAt(t); return document.getElementById('c').toDataURL('image/png').split(',')[1]; }, t);
    return Buffer.from(b64, 'base64');
  };

  if (stills) {
    const dir = args[1]; fs.mkdirSync(dir, { recursive: true });
    for (const t of args[2].split(',').map(Number)) fs.writeFileSync(`${dir}/t${t.toFixed(2)}.png`, await grab(t));
    await browser.close(); return;
  }

  const [out, s, e] = [args[0], +args[1], +args[2]];
  const fps = await page.evaluate(() => window.FPS);
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '12', '-pix_fmt', 'yuv420p', '-profile:v', 'high', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let f = s; f < e; f++) {
    const buf = await grab(f / fps);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if ((f - s) % 60 === 0) console.log(`[${out}] frame ${f}/${e}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
})();

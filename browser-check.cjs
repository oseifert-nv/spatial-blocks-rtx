// Optional browser integration check. Pass installed Playwright and Chrome paths.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const {url} = JSON.parse(fs.readFileSync(path.join(__dirname, 'runtime.json'), 'utf8'));
  const out = path.join(__dirname, 'qa-output');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH});
  const page = await browser.newPage({viewport:{width:1280,height:940}, deviceScaleFactor:1});
  const errors = [];
  const external = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {if(m.type()==='error') errors.push(m.text());});
  page.on('request', req => {if(!req.url().startsWith(url) && !req.url().startsWith('data:')) external.push(req.url());});
  const state = async () => (await page.request.get(url+'/api/state')).json();
  const waitPieces = async count => page.waitForFunction(n=>Number(document.getElementById('pieces').textContent)===n,count);
  const layout = async () => {
    const metrics = await page.evaluate(()=>{
      const b=document.getElementById('board').getBoundingClientRect();
      return {width:innerWidth,scroll:document.documentElement.scrollWidth,boardWidth:b.width,boardHeight:b.height};
    });
    assert(metrics.scroll <= metrics.width+1,JSON.stringify(metrics));
    assert(Math.abs(metrics.boardHeight/metrics.boardWidth-2)<0.015,JSON.stringify(metrics));
    return metrics;
  };
  try {
    await page.goto(url);
    await page.getByText('CPU LIBRARY CONNECTED').waitFor();
    assert.equal((await state()).phase,'ready');
    console.log('Desktop layout:',await layout());
    await page.screenshot({path:path.join(out,'desktop-ready.png'),fullPage:true});
    await page.locator('#play').click();
    await page.waitForFunction(()=>document.getElementById('overlay').hidden);
    const before = await state();
    await page.keyboard.press('ArrowLeft');
    await page.waitForFunction(()=>document.getElementById('board')===document.activeElement);
    await page.waitForTimeout(100);
    assert.equal((await state()).active.cells[0][0],before.active.cells[0][0]-1);
    await page.keyboard.press('ArrowUp');
    await page.waitForTimeout(100);
    assert.equal((await state()).active.rotation,1);
    await page.keyboard.press('Space');
    await waitPieces(1);
    assert.equal((await state()).board.length,4);
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Space');
    await waitPieces(2);
    for(let i=0;i<4;i++) await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('Space');
    await waitPieces(3);
    assert.equal((await state()).board.length,12);
    assert((await state()).engine.queries>before.engine.queries);
    await page.screenshot({path:path.join(out,'desktop-playing.png'),fullPage:true});
    await page.locator('#pause').click();
    await page.waitForFunction(()=>document.getElementById('phase-label').textContent==='PAUSED');
    const paused = await state();
    await page.waitForTimeout(1100);
    assert.deepEqual((await state()).active,paused.active);
    await page.keyboard.press('KeyP');
    await page.waitForFunction(()=>document.getElementById('phase-label').textContent==='LIVE');
    await page.locator('#restart').click();
    await waitPieces(0);
    assert.equal((await state()).board.length,0);
    await page.setViewportSize({width:390,height:844});
    console.log('Mobile layout:',await layout());
    await page.locator('[data-action="left"]').click();
    await page.locator('[data-action="drop"]').click();
    await waitPieces(1);
    await page.locator('#pause').click();
    await page.waitForFunction(()=>document.getElementById('phase-label').textContent==='PAUSED');
    await page.screenshot({path:path.join(out,'mobile-paused.png'),fullPage:true});
    await page.setViewportSize({width:320,height:720});
    console.log('Small mobile layout:',await layout());
    const rejected=await page.request.post(url+'/api/action',{headers:{Origin:'https://example.com'},data:{action:'restart'}});
    assert.equal(rejected.status(),403);
    assert.equal((await state()).pieces,1);
    assert.deepEqual(errors,[]);
    assert.deepEqual(external,[]);
    console.log('PASS: native-connected UI, move, rotation, keyboard hard drop, stacking, pause/resume, restart, touch, responsive board, origin restriction; no browser errors or external requests.');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});

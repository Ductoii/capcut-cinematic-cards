import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync,unlinkSync,appendFileSync} from 'node:fs';
import {once} from 'node:events';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const child=spawn(process.env.HARNESS_PYTHON||'.work/venv/bin/python',['-u','tests/browser_fixture.py'],{stdio:['ignore','pipe','pipe']});
let stderr='';child.stderr.on('data',d=>stderr+=d);
const fixture=await new Promise((resolve,reject)=>{
 let buffer='';const timer=setTimeout(()=>reject(new Error('Fixture timeout '+stderr)),20000);
 child.stdout.on('data',d=>{buffer+=d;const line=buffer.split('\n')[0];try{const item=JSON.parse(line);clearTimeout(timer);resolve(item);}catch{}});
 child.on('exit',()=>reject(new Error('Fixture exited '+stderr)));
});
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
try{
 await page.goto(fixture.url);await page.getByRole('heading',{name:'Cân âm thoại',exact:true}).waitFor({timeout:5000});
 await page.locator('#project-select').selectOption({label:'Test film'});
 await page.getByRole('button',{name:'Cân âm thoại',exact:true}).click();
 await page.locator('#apply').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#apply').disabled,{timeout:60000});
 assert.ok(await page.locator('#interval-rows tr').count()>0);
 await page.locator('#quality-summary').filter({hasText:'VAD'}).waitFor({timeout:3000});
 assert.match(await page.locator('#job-state').innerText(),/Sẵn sàng/);
 await page.locator('#interval-rows button').first().click();
 await page.getByRole('button',{name:'Sau xử lý',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#audio-player').readyState>0);await page.locator('#audio-player').evaluate(el=>{el.pause();el.currentTime=2;});const afterTime=2;
 await page.getByRole('button',{name:'Bản gốc',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#audio-player').readyState>0&&Math.abs(document.querySelector('#audio-player').currentTime-2)<.2);assert.ok(Math.abs(await page.locator('#audio-player').evaluate(el=>el.currentTime)-afterTime)<.2);
 writeFileSync(fixture.root+'/busy','1');await page.locator('#apply').click();
 await page.getByText(/CapCut is running/).first().waitFor({timeout:10000});
 unlinkSync(fixture.root+'/busy');await page.waitForFunction(()=>!document.querySelector('#apply').disabled);await page.locator('#apply').click();
 await page.waitForFunction(()=>document.querySelector('#job-state').textContent.includes('Đã áp dụng'),{timeout:15000});
 await page.locator('#undo').click();await page.waitForFunction(()=>document.querySelector('#job-state').textContent.includes('Đã hoàn tác'),{timeout:15000});
 await page.locator('#analyze').click();await page.waitForFunction(()=>!document.querySelector('#apply').disabled,{timeout:60000});
 appendFileSync(fixture.project+'/draft_info.json',' ');await page.locator('#apply').click();await page.locator('#job-error').filter({hasText:/changed/}).waitFor({timeout:15000});
 await page.locator('#command-input').fill('rm -rf /');await page.locator('#command-form button').click();
 await page.getByText(/Lệnh chưa hỗ trợ/).first().waitFor();
 mkdirSync('.work/browser-artifacts',{recursive:true});
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:900});assert.ok(await page.locator('#target').isVisible());await page.screenshot({path:`.work/browser-artifacts/${width}.png`,fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
 assert.deepEqual(errors,[]);console.log('PASS: real UI job -> A/B -> busy guard -> apply -> undo; unknown command; 1440/768/390');
}finally{await browser.close();child.kill('SIGINT');await Promise.race([once(child,'exit'),new Promise(r=>setTimeout(r,5000))]);}

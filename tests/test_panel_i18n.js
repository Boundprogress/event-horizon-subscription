'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const panel=fs.readFileSync(path.join(root,'panel.js'),'utf8');
const resource=fs.readFileSync(path.join(root,'panel_i18n.js'),'utf8');
const html=fs.readFileSync(path.join(root,'panel.html'),'utf8');
const catalog=JSON.parse(resource.match(/const english=Object\.freeze\(([\s\S]+?)\);\nconst storageKey/)[1]);
const unescape=text=>text.replace(/&quot;/g,'"').replace(/&#x27;/g,"'").replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
function page(options={}){
 const nodes=new Map(),calls=[],clipboard=[],confirmations=[],storage=new Map(),cookieWrites=[],historyCalls=[];
 const origin=options.origin||'http://127.0.0.1:8011',hostname=new URL(origin).hostname,cookieJar=options.cookieJar||new Map();
 if(options.cookie!==undefined)cookieJar.set(hostname,options.cookie);
 if(options.saved)storage.set('eh-panel-language',options.saved);
 const element=id=>{
  if(!nodes.has(id)){
   const node={id,hidden:false,disabled:false,textContent:'',value:'',children:[],attributes:{},dataset:{},
    isRoot:true,parent:null,get isConnected(){return this.parent?this.parent.isConnected:this.isRoot;},
    classList:{toggle(){}},reset(){},focus(){},select(){},scrollIntoView(){},removeAttribute(name){delete this.attributes[name];},
    getAttribute(name){return this.attributes[name]??null;},setAttribute(name,value){this.attributes[name]=String(value);},
    append(...items){for(const child of items){child.parent=this;}this.children.push(...items);},replaceChildren(...items){for(const child of this.children)child.parent=null;this.children=[];this.append(...items);},querySelector(selector){return element(id+selector);}};
   node.elements=new Proxy({}, {get:(_,name)=>element(id+':'+name)});nodes.set(id,node);
  }return nodes.get(id);
 };
 const staticNodes=[];
 for(const match of html.matchAll(/<[^>]+\sdata-i18n(?:-[\w-]+)?="[^>]*>/g)){
  const node=element('static:'+staticNodes.length);
  for(const attr of match[0].matchAll(/([\w-]+)="([^"]*)"/g))node.setAttribute(attr[1],unescape(attr[2]));
  staticNodes.push(node);
 }
 const document={documentElement:{lang:'zh-CN'},getElementById:element,
  querySelectorAll(selector){const attr=selector.match(/^\[([^\]]+)\]$/)?.[1];return attr?staticNodes.filter(node=>node.getAttribute(attr)!==null):[];},
  createElement:tag=>{const node=element(tag+':'+nodes.size);node.isRoot=false;return node;}};
 Object.defineProperty(document,'cookie',{
  get(){if(options.cookieBlocked)throw Error('cookies blocked');return cookieJar.get(hostname)||'';},
  set(header){if(options.cookieBlocked)throw Error('cookies blocked');cookieWrites.push(header);
   const pair=header.split(';')[0],name=pair.split('=')[0];
   const others=(cookieJar.get(hostname)||'').split(';').map(x=>x.trim()).filter(x=>x&&x.split('=')[0]!==name);
   cookieJar.set(hostname,[...others,pair].join('; '));}
 });
 const fixture={signed_in:true,account:'account-a',username:'原文 User 中文',version:'fixture',endpoint:'https://example.invalid',pending:null,notice:null,
  credentials:{api_ready:true,device_ready:true,key_id:'key-a'},connection:{clean:true,running:false,status:'offline'},
  onboarding:{stage:'connect'},updates:{status:'source_manual'},terms_document:{available:true,version:'v1',sha256:'hash'},cloud_checked_at:1000,
  cloud:{subscription:{billing:'lifetime_frames',metering:'frames',enabled:true,expires_at:null,period_ends_at:null,frame_limit:5000,charged_frames:10,remaining:4990},
   keys:[],device:{registered:true,enabled:true},terms:{current:true,version:'v1',sha256:'hash'},appeals:{available:true,eligible:true},recovery:{verified:true,available:true,email_masked:'原文@example.invalid'}}};
 const context=vm.createContext({fixture,document,location:{hash:options.hash||'',pathname:'/',origin},sessionStorage:{getItem:()=>{if(options.sessionBlocked)throw Error('session blocked');return '';},setItem:()=>{if(options.sessionBlocked)throw Error('session blocked');}},
  localStorage:{getItem:key=>{if(options.storageBlocked)throw Error('blocked');return storage.get(key)||null;},setItem:(key,value)=>{if(options.storageBlocked)throw Error('blocked');storage.set(key,value);}},
  history:{replaceState(...args){historyCalls.push(args);}},navigator:{language:options.browser||'zh-CN',onLine:true,clipboard:{writeText:async text=>clipboard.push(text)}},
  window:{scrollTo(){}},confirm:text=>{confirmations.push(text);return false;},
  fetch:async(url,request)=>{calls.push({url,request});const values={
   '/api/state':fixture,'/api/refresh':{status:'refreshed'},
   '/api/agent_connect':{host:'generic',host_connection:'not_verified',contains_credentials:false,path:'/tmp/原文 "目录"/CONNECT.md',instruction:'读取本机原文指令。'},
   '/api/diagnose':{status:'checked',mode:'online',api_health_ok:true,device_authentication:'not_tested',error:'远端原文_CODE'},
   '/api/activation_receipts':{pending_confirmed:false,receipts:[{redeemed_at:1000,plan_id:'原文_plan',billing:'lifetime_frames',frames:5000,request_id:'原文_request'}]}};
   if(!Object.hasOwn(values,url))throw Error('Unexpected endpoint '+url);
   return {ok:true,json:async()=>values[url]};},setTimeout,clearTimeout,setInterval(){},AbortController});
 vm.runInContext(resource,context,{filename:'panel_i18n.js'});vm.runInContext(panel,context,{filename:'panel.js'});
 const run=code=>vm.runInContext(code,context);run('state=fixture;render()');
 return{context,fixture,element,staticNodes,document,calls,storage,cookieJar,cookieWrites,historyCalls,clipboard,confirmations,run,switch:language=>run(`setPanelLanguage(${JSON.stringify(language)})`)};
}
const treeText=node=>[node.textContent,...node.children.map(treeText)].join(' ');
async function main(){
 let passed=0;
 async function test(name,body){await body();passed++;console.log('ok - '+name);}
 await test('catalog covers all marked UI text and format parameters',()=>{
  assert.ok(Object.keys(catalog).length>450);
  for(const match of html.matchAll(/data-i18n(?:-[\w-]+)?="([^"]*)"/g))assert.ok(Object.hasOwn(catalog,unescape(match[1])),match[1]);
  for(const match of panel.matchAll(/\bt\(("(?:[^"\\]|\\.)*")/g))assert.ok(Object.hasOwn(catalog,JSON.parse(match[1])),match[1]);
  for(const [key,value]of Object.entries(catalog)){
   assert.ok(value.trim(),key);
   assert.deepEqual([...key.matchAll(/\{(\w+)\}/g)].map(x=>x[1]).sort(),[...value.matchAll(/\{(\w+)\}/g)].map(x=>x[1]).sort(),key);
   assert.doesNotMatch(value.replaceAll('《EH 订阅服务使用协议》',''),/\p{Script=Han}/u,key);
  }
  assert.ok(html.indexOf('/panel_i18n.js')<html.indexOf('/panel.js'));
 });
 await test('explicit language, browser default, persistence, and blocked storage',()=>{
  const english=page({browser:'en-GB'});assert.equal(english.document.documentElement.lang,'en');assert.equal(english.element('language').value,'en');
  english.switch('zh-CN');assert.equal(english.storage.get('eh-panel-language'),'zh-CN');assert.equal(english.document.documentElement.lang,'zh-CN');
  assert.equal(page({saved:'en',browser:'zh-CN'}).element('connection-badge').textContent,'Not connected');
  assert.equal(page({saved:'zh-CN',browser:'en-US'}).element('connection-badge').textContent,'未连接');
  const blocked=page({storageBlocked:true,browser:'en-US'});blocked.switch('zh-CN');assert.equal(blocked.document.documentElement.lang,'zh-CN');
  assert.throws(()=>english.run("EHPanelI18n.setLanguage('xx')"),/Unsupported/);
 });
 await test('language preference survives a new loopback origin through a host-only cookie',()=>{
  const shared=new Map(),first=page({origin:'http://127.0.0.1:8111',cookieJar:shared});
  first.switch('en');
  const second=page({origin:'http://127.0.0.1:9222',cookieJar:shared,browser:'zh-CN',saved:'zh-CN'});
  assert.equal(second.document.documentElement.lang,'en');
  assert.notEqual(first.storage,second.storage);
  assert.equal(first.cookieWrites.at(-1),'eh-panel-language=en; Path=/; SameSite=Strict; Max-Age=31536000');
  assert.doesNotMatch(first.cookieWrites.at(-1),/Secure|Domain=|account|Key|capability/);
  second.switch('zh-CN');
  assert.equal(page({origin:'http://127.0.0.1:9333',cookieJar:shared,browser:'en-US'}).document.documentElement.lang,'zh-CN');
 });
 await test('blocked and invalid cookies fall back safely to legacy storage or browser language',()=>{
  assert.equal(page({cookie:'eh-panel-language=en; unrelated=value',saved:'zh-CN'}).document.documentElement.lang,'en');
  for(const invalid of ['xx','<script>','en%0A','en=extra','EN','']){
   const app=page({cookie:'eh-panel-language='+invalid,saved:'zh-CN',browser:'en-US'});
   assert.equal(app.document.documentElement.lang,'zh-CN');
  }
  const local=page({cookieBlocked:true,saved:'en',browser:'zh-CN'});assert.equal(local.document.documentElement.lang,'en');local.switch('zh-CN');
  const blocked=page({cookieBlocked:true,storageBlocked:true,browser:'en-US'});assert.equal(blocked.document.documentElement.lang,'en');
  const before=blocked.calls.length;blocked.switch('zh-CN');assert.equal(blocked.document.documentElement.lang,'zh-CN');assert.equal(blocked.calls.length,before);
 });
 await test('blocked session storage keeps fragment access only in memory and clears the URL hash',async()=>{
  const app=page({sessionBlocked:true,cookieBlocked:true,storageBlocked:true,hash:'#synthetic-access',saved:'en',browser:'en-US'});
  await app.run('Promise.resolve()');
  assert.equal(app.run('capability'),'synthetic-access');
  assert.equal(app.historyCalls.length,1);assert.equal(app.historyCalls[0][2],'/');
  assert.equal(app.calls[0].request.headers.Authorization,'Bearer synthetic-access');
  assert.ok(app.calls.every(call=>call.request.credentials==='omit'));
  assert.equal(app.storage.size,1);assert.equal(app.cookieWrites.length,0);
  const refreshed=page({sessionBlocked:true,cookieBlocked:true,storageBlocked:true,browser:'en-US'});
  assert.equal(refreshed.run('capability'),'');assert.match(refreshed.element('feedback').textContent,/Run the client launcher/);assert.equal(refreshed.calls.length,0);
 });
 await test('English text fragments stay separated when line breaks are hidden',()=>{
  const app=page({saved:'en'});
  assert.equal(app.run("t('把网页能力')+t('接入你的 agent。')"),'Bring web capabilities to your agent.');
  assert.equal(app.run("t('注册账号，申请赠送激活码，')+t('连接浏览器后按额度使用。')"),'Register, request a complimentary code, then connect your browser and use your quota.');
  assert.match('test@example.invalid'+app.run("t('也可在站内提交并查询处理结果。')"),/invalid You can also/);
  app.switch('zh-CN');assert.equal(app.run("t('把网页能力')+t('接入你的 agent。')"),'把网页能力接入你的 agent。');
 });
 await test('static labels and attributes translate, original Chinese legal title remains identified',()=>{
  const app=page({saved:'en'});
  for(const node of app.staticNodes){
   if(node.getAttribute('data-i18n'))assert.equal(node.textContent,catalog[node.getAttribute('data-i18n')]);
   for(const attr of ['title','aria-label','placeholder'])if(node.getAttribute('data-i18n-'+attr))assert.equal(node.getAttribute(attr),catalog[node.getAttribute('data-i18n-'+attr)]);
  }
  assert.match(app.staticNodes.find(n=>n.getAttribute('data-i18n')==='《EH 订阅服务使用协议》').textContent,/Chinese terms/);
 });
 await test('dynamic errors, guides, auth tabs, billing, status, and feedback switch live',()=>{
  const app=page({saved:'en'});
  assert.equal(app.element('expiry').textContent,'No expiry');assert.equal(app.element('subscription-status').textContent,'Active');
  assert.match(app.element('billing-period').textContent,/Lifetime quota: 5,000 frames/);
  assert.match(app.element('guide-title').textContent,/Connect your dedicated browser/);
  app.run("authMode('register');say(()=>errorMessage({code:'invalid_credentials'}),true)");
  assert.equal(app.element('auth-submit').textContent,'Create account');assert.equal(app.element('feedback').textContent,'Incorrect username or password.');
  const before=app.calls.length;app.switch('zh-CN');assert.equal(app.calls.length,before);
  assert.equal(app.element('auth-submit').textContent,'创建账号');assert.equal(app.element('feedback').textContent,'用户名或密码不正确。');
  app.switch('en');assert.equal(app.element('feedback').textContent,'Incorrect username or password.');
  app.run("fixture.cloud.subscription={billing:'calendar_month',metering:'frames',enabled:true,expires_at:Date.now()/1000+3600,period_starts_at:1000,period_ends_at:2000,frame_limit:3000};render()");
  assert.match(app.element('billing-period').textContent,/Current period \(Beijing time\)/);
 });
 await test('user inputs, masked email, raw diagnostics, appeal content, and credentials are not translated',async()=>{
  const app=page({saved:'en'});app.element('auth-form:password').value='原文 password Key';app.element('support-preview').value='原文 report';
  app.run("appealHistory={appeals:[{status:'pending',request_id:'原文_request',reason:'用户名 登录 原文',public_result:'已完成 原文处理',created_at:1000}]};renderAppeals()");
  assert.match(treeText(app.element('appeal-history')),/用户名 登录 原文/);assert.match(treeText(app.element('appeal-history')),/已完成 原文处理/);
  assert.equal(app.element('username').textContent,'原文 User 中文');assert.match(app.element('email-status').textContent,/原文@example.invalid/);
  await app.run("act('diagnose')");assert.match(treeText(app.element('diagnostic-result')),/远端原文_CODE/);
  app.switch('zh-CN');app.switch('en');
  assert.equal(app.element('auth-form:password').value,'原文 password Key');assert.equal(app.element('support-preview').value,'原文 report');
  assert.match(treeText(app.element('appeal-history')),/已完成 原文处理/);assert.match(treeText(app.element('diagnostic-result')),/Network check/);
  assert.match(treeText(app.element('diagnostic-result')),/远端原文_CODE/);
  assert.equal(app.run("t('提交于 {p0} · 请求号 {p1}',{p0:'登录 原文',p1:'{p0}'})"),'Submitted 登录 原文 · Request ID {p0}');
 });
 await test('activation records and unknown request notices remain localized without new submissions',async()=>{
  const app=page({saved:'en'});await app.run("act('activation_receipts')");
  assert.match(treeText(app.element('activation-receipts-list')),/One-time quota: 5,000 frames/);
  app.run("fixture.pending={id:'id',operation:'redeem',request_id:'原文_request',started_at:1000};render()");
  assert.match(app.element('pending-text').textContent,/Do not submit the code again/);
  const before=app.calls.length;app.switch('zh-CN');assert.match(treeText(app.element('activation-receipts-list')),/一次性总额/);app.switch('en');
  assert.equal(app.calls.length,before);assert.match(app.element('pending-text').textContent,/原文_request/);
 });
 await test('clearing a pending operation removes stale readers before switching language',()=>{
  for(const operation of ['appeal_create','redeem','key_rotate']){
   const app=page({saved:'en'});
   app.fixture.pending={operation,request_id:'same-request',state:'unknown',id:'x',started_at:1000};app.run('render()');
   assert.match(app.element('pending-text').textContent,/same-request|key_rotate/);
   app.fixture.pending=null;app.run('render()');app.switch('zh-CN');app.switch('en');
   assert.equal(app.element('pending').hidden,true);assert.equal(app.element('pending-text').textContent,'');
   assert.doesNotMatch(app.element('appeal-query-state').textContent,/same-request/);
  }
 });
 await test('confirmation dialogs use selected language and do not bypass cancellation',async()=>{
  const app=page({saved:'en'});const before=app.calls.length;await app.run('quitClient()');
  assert.match(app.confirmations.at(-1),/^Exit and disconnect/);assert.equal(app.calls.length,before);
  app.switch('zh-CN');await app.run('quitClient()');assert.match(app.confirmations.at(-1),/^退出会断开/);
  app.switch('en');app.run("fixture.pending={id:'pending',operation:'redeem',request_id:'r'};document.getElementById('acknowledge').onclick()");
  assert.match(app.confirmations.at(-1),/^Have you reviewed the activation receipt/);assert.equal(app.calls.length,before);
 });
 await test('one-line setup uses exact JSON-quoted local path and language switch never recopies or requests',async()=>{
  const app=page({saved:'en'});await app.run('connectAgent()');
  assert.equal(app.clipboard.length,1);const line=app.element('agent-one-line').value;
  assert.match(line,/^Read the local file /);assert.ok(line.includes(JSON.stringify('/tmp/原文 "目录"/CONNECT.md')));assert.match(line,/Do not run a web task yet\.$/);
  assert.equal(app.clipboard[0],line);const before=app.calls.length;
  app.switch('zh-CN');assert.equal(app.element('agent-one-line').value,'读取本机原文指令。');app.switch('en');
  assert.equal(app.element('agent-one-line').value,line);assert.equal(app.clipboard.length,1);assert.equal(app.calls.length,before);
  app.run("fixture.account='account-b';fixture.username='Other 原文';render()");app.switch('zh-CN');app.switch('en');
  assert.equal(app.element('agent-one-line').value,'');assert.equal(app.run('agentLink'),null);assert.equal(app.element('agent-line-preview').hidden,true);
 });
 await test('polling and repeated appeal rendering keep text bindings bounded',()=>{
  const app=page({saved:'en'});
  app.run("appealHistory={appeals:[{status:'pending',request_id:'retained',reason:'原文 private',public_result:'原文 response',created_at:1000}]};render()");
  const size=app.run('textBindings.size');
  for(let i=0;i<150;i++)app.run('render()');
  assert.equal(app.run('textBindings.size'),size);
  app.run("fixture.account='account-b';render()");
  app.switch('zh-CN');app.switch('en');
  assert.doesNotMatch(treeText(app.element('appeal-history')),/原文 private|原文 response/);
  assert.ok(app.run('textBindings.size')<=size);
 });
 await test('every authored message and onboarding stage has an English rendering',()=>{
  const app=page({saved:'en'});
  const messages=app.run('Object.values(messages)');for(const message of messages)assert.doesNotMatch(message.replaceAll('《EH 订阅服务使用协议》',''),/\p{Script=Han}/u);
  const guides=app.run('Object.values(guideStages)');for(const row of guides)for(const text of row.slice(0,3))assert.doesNotMatch(text,/\p{Script=Han}/u);
 });
 console.log(passed+' bilingual panel UI checks passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});

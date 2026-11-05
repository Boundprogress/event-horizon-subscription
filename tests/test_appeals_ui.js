'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const sourcePath = process.argv[2] || path.join(__dirname, '..', 'panel.js');
const source = fs.readFileSync(sourcePath, 'utf8');

function gate() {
  let enter, release;
  return {entered: new Promise(resolve => { enter = resolve; }),
    released: new Promise(resolve => { release = resolve; }),
    enter: () => enter(), release: () => release()};
}

function page(options = {}) {
  const nodes = new Map(), calls = [];
  const element = id => {
    if (!nodes.has(id)) {
      const node = {id, hidden: false, disabled: false, textContent: '', children: [],
        classList: {toggle() {}}, reset() {}, removeAttribute(name) { delete this[name]; },
        append(...items) { this.children.push(...items); },
        replaceChildren(...items) { this.children = items; },
        querySelector(selector) { return element(id + selector); }};
      node.elements = new Proxy({}, {get: (_target, name) => element(id + ':' + name)});
      nodes.set(id, node);
    }
    return nodes.get(id);
  };
  const fixture = {signed_in: true, account: 'account-a', username: 'Account A',
    version: 'fixture', endpoint: 'https://example.invalid', pending: options.pending || null,
    notice: null, credentials: {api_ready: true, device_ready: true, key_id: 'key-a'},
    connection: {clean: true, running: false, status: 'offline'},
    onboarding: {stage: 'activation_review'}, updates: {status: 'source_manual'},
    terms_document: {available: true, version: '1', sha256: 'a'}, cloud_checked_at: Date.now() / 1000,
    cloud: {subscription: {enabled: false, expires_at: 1, remaining: 5},
      keys: [], device: {registered: true, enabled: true},
      terms: {current: true, version: '1', sha256: 'a'},
      appeals: {available: true, eligible: true}, activation_review_required: true}};
  const row = {id: 'appeal-a', request_id: 'request-a', status: 'pending',
    reason: 'ACCOUNT_A_PRIVATE_REASON', public_result: '', created_at: 1000};
  const rows = options.empty ? [] : [row];
  const clone = value => JSON.parse(JSON.stringify(value));
  const context = vm.createContext({fixture,
    document: {getElementById: element, querySelectorAll: () => [],
      createElement: tag => element(tag + ':' + nodes.size)},
    location: {hash: '', pathname: '/'}, sessionStorage: {getItem: () => ''},
    history: {replaceState() {}}, navigator: {onLine: true}, window: {scrollTo() {}},
    fetch: async (url, request) => {
      const endpoint = url.replace('/api/', '');
      calls.push({endpoint, method: request.method, account: fixture.account});
      let value;
      if (endpoint === 'state') value = fixture;
      else if (endpoint === 'refresh') value = {status: 'refreshed'};
      else if (endpoint === 'appeals') {
        value = {appeals: fixture.account === 'account-a' ? rows : [],
          pending_confirmed: fixture.account === 'account-a' && !!fixture.pending && rows.length > 0};
        value = clone(value);
        if (options.queryGate) { options.queryGate.enter(); await options.queryGate.released; }
      } else if (endpoint === 'appeal_create') {
        rows.push(row); value = {appeal: row, replayed: false};
        if (options.createGate) { options.createGate.enter(); await options.createGate.released; }
        if (options.loseCreateResponse) {
          fixture.pending = {id: 'operation-a', operation: 'appeal_create',
            request_id: 'request-a', state: 'unknown', started_at: 1000};
          throw new TypeError('Synthetic response lost after server commit');
        }
      } else throw Error('Unexpected endpoint: ' + endpoint);
      return {ok: true, status: 200, json: async () => clone(value)};
    },
    setTimeout, clearTimeout, setInterval() {}, AbortController,
  });
  vm.runInContext(source, context, {filename: sourcePath});
  vm.runInContext('state=fixture;render()', context);
  return {element, calls, rows, fixture, context,
    run: code => vm.runInContext(code, context),
    act: op => vm.runInContext(`act(${JSON.stringify(op)}, {reason:'SYNTHETIC REASON'})`, context),
    switchAccount: async (account, signedIn = true) => {
      fixture.account = account; fixture.signed_in = signedIn;
      await vm.runInContext('readState()', context);
    }};
}

function text(node) { return [node.textContent, ...node.children.map(text)].join(' '); }
function assertPrivateHistoryAbsent(app) {
  assert.equal(app.run('appealHistory'), null);
  assert.doesNotMatch(text(app.element('appeal-history')), /ACCOUNT_A_PRIVATE_REASON/);
  assert.match(app.element('feedback').textContent, /账号已变化/);
  assert.equal(app.element('feedback').className, 'error');
}

async function run() {
  let passed = 0, failed = 0;
  async function test(name, body) {
    let timer;
    try {
      await Promise.race([body(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error('Behavior check did not reach its expected response')), 1500);
      })]);
      passed++; console.log('ok - ' + name);
    }
    catch (error) { failed++; console.error('not ok - ' + name + '\n' + error.stack); }
    finally { clearTimeout(timer); }
  }
  await test('successful query renders owned history without a create request', async () => {
    const app = page(); await app.act('appeals');
    assert.match(app.element('feedback').textContent, /已查询本人申诉/);
    assert.equal(app.element('feedback').className, '');
    assert.match(text(app.element('appeal-history')), /ACCOUNT_A_PRIVATE_REASON/);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeals').length, 1);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 0);
  });
  await test('successful submission commits once and queries for its history', async () => {
    const app = page({empty: true}); await app.act('appeal_create');
    assert.equal(app.rows.length, 1);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 1);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeals').length, 1);
    assert.match(app.element('feedback').textContent, /申诉已提交/);
    assert.match(text(app.element('appeal-history')), /ACCOUNT_A_PRIVATE_REASON/);
  });
  await test('querying the original pending request enables acknowledgement without resubmitting', async () => {
    const pending = {id: 'operation-a', operation: 'appeal_create', request_id: 'request-a', state: 'unknown'};
    const app = page({pending});
    assert.equal(app.element('acknowledge').disabled, true);
    await app.act('appeals');
    assert.equal(app.run('appealHistory.pending_confirmed'), true);
    assert.equal(app.element('acknowledge').disabled, false);
    assert.match(app.element('appeal-query-state').textContent, /已查到原请求/);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 0);
  });
  for (const operation of ['appeals', 'appeal_create']) {
    await test('account switch during initial ' + operation + ' discards old results', async () => {
      const pending = gate(), app = page(operation === 'appeals' ? {queryGate: pending} : {empty: true, createGate: pending});
      const action = app.act(operation); await pending.entered;
      await app.switchAccount('account-b'); pending.release(); await action;
      assertPrivateHistoryAbsent(app);
      if (operation === 'appeal_create') assert.equal(app.calls.filter(c => c.endpoint === 'appeals').length, 0);
    });
  }
  for (const signedIn of [true, false]) {
    await test('identity change during post-submit query is rejected (signedIn=' + signedIn + ')', async () => {
      const pending = gate(), app = page({empty: true, queryGate: pending});
      const action = app.act('appeal_create'); await pending.entered;
      await app.switchAccount(signedIn ? 'account-b' : null, signedIn);
      pending.release(); await action;
      assertPrivateHistoryAbsent(app);
      assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 1);
    });
  }
  await test('post-submit query refreshes identity before publishing its response', async () => {
    const pending = gate(), app = page({empty: true, queryGate: pending});
    const action = app.act('appeal_create'); await pending.entered;
    // Another tab changed the local account; this page has not polled it yet.
    app.fixture.account = 'account-b';
    pending.release(); await action;
    assertPrivateHistoryAbsent(app);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 1);
  });
  await test('lost create response never retries and explicit query recovers the committed receipt', async () => {
    const app = page({empty: true, loseCreateResponse: true}); await app.act('appeal_create');
    assert.equal(app.rows.length, 1);
    assert.match(app.element('feedback').textContent, /响应未确认/);
    assert.equal(app.run('appealHistory'), null);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 1);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeals').length, 0);
    await app.act('appeals');
    assert.equal(app.run('appealHistory.pending_confirmed'), true);
    assert.equal(app.element('acknowledge').disabled, false);
    assert.equal(app.calls.filter(c => c.endpoint === 'appeal_create').length, 1);
  });
  console.log(`${passed} appeals UI behavior checks passed; ${failed} failed`);
  if (failed) process.exitCode = 1;
}

run().catch(error => { console.error(error); process.exitCode = 1; });

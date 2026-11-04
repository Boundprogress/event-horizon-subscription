'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'panel.js'), 'utf8');

function page(subscription, receipts = []) {
  const nodes = new Map();
  const element = id => {
    if (!nodes.has(id)) {
      const node = {id, hidden: false, disabled: false, textContent: '', children: [],
        classList: {toggle() {}}, reset() {}, removeAttribute() {},
        append(...items) { this.children.push(...items); },
        replaceChildren(...items) { this.children = items; },
        querySelector(selector) { return element(id + selector); }};
      node.elements = new Proxy({}, {get: (_target, name) => element(id + ':' + name)});
      nodes.set(id, node);
    }
    return nodes.get(id);
  };
  const fixture = {signed_in: true, account: 'fixture', username: 'Fixture', version: '0.26.0',
    endpoint: 'https://example.invalid', pending: null, notice: null,
    credentials: {api_ready: true, device_ready: true, key_id: 'fixture-key'},
    connection: {clean: true, running: false, status: 'offline'},
    onboarding: {stage: 'connect'}, updates: {status: 'source_manual'},
    terms_document: {available: true, version: '1', sha256: 'a'},
    cloud_checked_at: Date.now() / 1000,
    cloud: {subscription, keys: [], device: {registered: true, enabled: true},
      terms: {current: true, version: '1', sha256: 'a'}}};
  const context = vm.createContext({
    fixture, document: {getElementById: element, querySelectorAll: () => [],
      createElement: tag => element(tag + ':' + nodes.size)},
    location: {hash: '', pathname: '/'}, sessionStorage: {getItem: () => ''},
    navigator: {onLine: true}, history: {replaceState() {}}, window: {scrollTo() {}},
    fetch: async url => ({ok: true, json: async () => url === '/api/state' ? fixture :
      url === '/api/activation_receipts' ? {receipts, pending_confirmed: false} : {status: 'refreshed'}}),
    setTimeout, clearTimeout, setInterval() {}, AbortController,
  });
  vm.runInContext(source, context, {filename: 'panel.js'});
  vm.runInContext('state=fixture;render()', context);
  return {element, context};
}

async function run() {
  const lifetime = {billing: 'lifetime_frames', metering: 'frames', enabled: true,
    expires_at: null, period_ends_at: null, frame_limit: 5000, remaining: 4988, charged_frames: 10};
  const permanent = page(lifetime);
  assert.equal(permanent.element('expiry').textContent, '永久有效');
  assert.equal(permanent.element('remaining-label').textContent, '剩余总额度');
  assert.equal(permanent.element('subscription-status').textContent, '已开通');
  assert.match(permanent.element('billing-period').textContent, /一次性总额度 5,000 帧/);
  assert.match(permanent.element('billing-period').textContent, /不按月重置/);

  const monthly = page({...lifetime, billing: 'calendar_month', period_starts_at: Date.now() / 1000,
    expires_at: Date.now() / 1000 + 3600, period_ends_at: Date.now() / 1000 + 3600});
  assert.equal(monthly.element('remaining-label').textContent, '本期剩余额度');
  assert.notEqual(monthly.element('expiry').textContent, '永久有效');
  assert.equal(monthly.element('subscription-status').textContent, '已开通');
  assert.match(monthly.element('billing-period').textContent, /本期（北京时间）/);

  const missing = page({...lifetime, billing: undefined});
  assert.notEqual(missing.element('expiry').textContent, '永久有效');
  assert.notEqual(missing.element('subscription-status').textContent, '已开通');
  const disabled = page({...lifetime, enabled: false});
  assert.notEqual(disabled.element('subscription-status').textContent, '已开通');

  const receipts = page(lifetime, [
    {redeemed_at: 1000, request_id: 'permanent', plan_id: 'eh_lifetime',
      billing: 'lifetime_frames', months: 0, frames: 5000},
    {redeemed_at: 1000, request_id: 'monthly', plan_id: 'eh_1m', months: 1, frames: 3000},
  ]);
  await vm.runInContext("act('activation_receipts')", receipts.context);
  const rows = receipts.element('activation-receipts-list').children.map(row => row.textContent);
  assert.equal(rows.length, 2);
  assert.match(rows[0], /永久有效 · 一次性总额 5,000 帧/);
  assert.doesNotMatch(rows[0], /0 个月|每月/);
  assert.match(rows[1], /1 个月 · 每月 3,000 帧/);
  process.stdout.write('5 permanent/monthly UI behavior checks passed\n');
}

run().catch(error => { console.error(error); process.exitCode = 1; });

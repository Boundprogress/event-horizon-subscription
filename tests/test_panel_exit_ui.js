'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'panel.js'), 'utf8');

function page(fetch) {
  const elements = new Map(), scheduled = new Map();
  let now = 0, nextTimer = 0;
  const element = id => {
    if (!elements.has(id)) elements.set(id, {disabled: false, hidden: false, textContent: '', className: ''});
    return elements.get(id);
  };
  const context = vm.createContext({
    document: {getElementById: element,
      querySelectorAll: selector => selector === 'button' ? [...elements.values()] : []},
    location: {hash: '', pathname: '/'},
    sessionStorage: {getItem: () => '', setItem: () => {}},
    history: {replaceState: () => {}},
    navigator: {onLine: true},
    confirm: () => true,
    fetch: (...args) => fetch(...args),
    AbortController,
    Date: class Clock extends Date { static now() { return now; } },
    setTimeout: (callback, delay) => {
      const id = ++nextTimer;
      scheduled.set(id, delay);
      setImmediate(() => {
        if (!scheduled.has(id)) return;
        now += scheduled.get(id);
        scheduled.delete(id);
        callback();
      });
      return id;
    },
    clearTimeout: id => scheduled.delete(id),
    setInterval: () => { throw new Error('Unneeded polling in this test'); },
  });
  vm.runInContext(source, context, {filename: 'panel.js'});
  vm.runInContext("capability='test-capability'", context);
  return {
    context, element,
    quit: () => element('quit').onclick(),
    feedback: () => element('feedback'),
    now: () => now,
    timers: scheduled,
  };
}

const receipt = clean => ({ok: true, json: async () => ({status: 'shutdown_ready', connection_clean: clean})});
const gone = () => Promise.reject(new TypeError('Failed to fetch'));
const waitForAbort = (_url, options) => new Promise((resolve, reject) => {
  options.signal.addEventListener('abort', () => {
    const error = new Error('aborted'); error.name = 'AbortError'; reject(error);
  }, {once: true});
});

async function run() {
  let count = 0;
  async function test(name, body) {
    await body(); count++; process.stdout.write('ok ' + count + ' - ' + name + '\n');
  }

  await test('clean receipt and closed server produce completion after immediate progress', async () => {
    const calls = [];
    const app = page((url, options) => {
      calls.push([url, options]);
      assert.equal(app.element('quit').disabled, true);
      if (calls.length === 1) {
        assert.match(app.feedback().textContent, /正在退出并清理连接/);
        return Promise.resolve(receipt(true));
      }
      return gone();
    });
    await app.quit();
    assert.match(app.feedback().textContent, /^客户端已退出/);
    assert.equal(app.feedback().className, '');
    assert.equal(calls.length, 2);
    assert.equal(calls[0][0], '/api/quit');
    assert.equal(calls[0][1].method, 'POST');
    assert.equal(calls[1][0], '/api/state');
    assert.equal(calls[1][1].method, 'GET');
    assert.equal(calls[1][1].cache, 'no-store');
    assert.equal(calls[1][1].headers.Authorization, 'Bearer test-capability');
    assert.ok(calls[0][1].signal);
    assert.ok(calls[1][1].signal);
    assert.equal(vm.runInContext('closing', app.context), true);
    assert.equal(app.timers.size, 0);
  });

  await test('unclean receipt never becomes browser-clean success', async () => {
    let calls = 0;
    const app = page(() => ++calls === 1 ? Promise.resolve(receipt(false)) : gone());
    await app.quit();
    assert.match(app.feedback().textContent, /^控制台已关闭，但浏览器退出尚未确认/);
    assert.equal(app.feedback().className, 'error');
  });

  await test('lost initial receipt is unknown, with no shutdown probe', async () => {
    let calls = 0;
    const app = page(() => { calls++; return gone(); });
    await app.quit();
    assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    assert.equal(app.feedback().className, 'error');
    assert.equal(calls, 1);
  });

  await test('probe timeout is not evidence of shutdown', async () => {
    let calls = 0;
    const app = page((...args) => ++calls === 1 ? Promise.resolve(receipt(true)) : waitForAbort(...args));
    await app.quit();
    assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    assert.equal(app.now(), 1000);
    assert.equal(calls, 2);
  });

  await test('still responding server ends with bounded unknown outcome', async () => {
    let calls = 0;
    const app = page(() => Promise.resolve(++calls === 1 ? receipt(true) : {ok: false, status: 409}));
    await app.quit();
    assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    assert.equal(app.now(), 10000);
    assert.ok(calls > 2 && calls <= 41);
  });

  await test('browser offline after receipt cannot count as closed server', async () => {
    let calls = 0;
    const app = page(() => { calls++; app.context.navigator.onLine = false; return Promise.resolve(receipt(true)); });
    await app.quit();
    assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    assert.equal(calls, 1);
  });

  await test('explicit abort and non-network errors cannot count as closed server', async () => {
    for (const name of ['AbortError', 'SecurityError', 'Error']) {
      let calls = 0;
      const app = page(() => {
        if (++calls === 1) return Promise.resolve(receipt(true));
        const error = new Error('probe unavailable'); error.name = name;
        return Promise.reject(error);
      });
      await app.quit();
      assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    }
  });

  await test('invalid cleanup receipt cannot permit shutdown success', async () => {
    for (const value of [{status: 'closing'}, {status: 'shutdown_ready', connection_clean: 'true'}, null]) {
      let calls = 0;
      const app = page(() => { calls++; return Promise.resolve({ok: true, json: async () => value}); });
      await app.quit();
      assert.match(app.feedback().textContent, /^退出结果尚未确认/);
      assert.equal(calls, 1);
    }
  });

  await test('quit request itself has a 65 second deadline', async () => {
    const app = page(waitForAbort);
    await app.quit();
    assert.match(app.feedback().textContent, /^退出结果尚未确认/);
    assert.equal(app.now(), 65000);
    assert.equal(app.timers.size, 0);
  });

  await test('a late state response cannot overwrite completed exit or enable buttons', async () => {
    let releaseState, calls = 0;
    const app = page((url) => {
      calls++;
      if (calls === 1) return new Promise(resolve => { releaseState = resolve; });
      if (url === '/api/quit') return Promise.resolve(receipt(true));
      return gone();
    });
    const oldRead = vm.runInContext('readState()', app.context);
    await app.quit();
    releaseState({ok: true, json: async () => ({unusable_stale_snapshot: true})});
    await oldRead;
    assert.match(app.feedback().textContent, /^客户端已退出/);
    assert.equal(app.element('quit').disabled, true);
    assert.equal(vm.runInContext('state', app.context), null);
  });

  process.stdout.write(count + ' exit UI tests passed\n');
}

run().catch(error => { console.error(error); process.exitCode = 1; });

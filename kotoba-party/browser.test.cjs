'use strict';
/**
 * Reproducible mobile browser checks. All Wikipedia responses are LOCAL MOCKS.
 * These checks do not establish that live Wikipedia is accessible from a phone.
 *
 * npm run build && npm run test:browser
 * Optional: BASE_URL=http://127.0.0.1:4173 npm run test:browser
 * Optional: CHROMIUM_PATH=/path/to/chromium npm run test:browser
 * Without BASE_URL, current source files + built dictionary are served in memory.
 * No server, credentials, screenshots or other test artifacts are required.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173/';
const baseOrigin = new URL(baseURL).origin;
const fixture = read('template.html')
  .split('__STYLE__').join(read('style.css'))
  .split('__DATA__').join(read('public/data.json').replace(/<\//g, '<\\/'))
  .split('__ENGINE__').join(read('engine.js'))
  .split('__APP__').join(read('app.js'));
const completed = [];
const counts = [];
const pass = name => { completed.push(name); console.log(`PASS ${name}`); };
const state = page => page.evaluate(() => JSON.parse(localStorage.getItem('kotoba-party.v1')));
const waitStatus = (page, text) => page.waitForFunction(value => {
  return document.getElementById('refillStatus')?.textContent.includes(value);
}, text, { timeout: 30000 });
const endRound = async page => { await page.click('#endRound'); await page.click('#dialogOk'); };
const openRefill = async page => {
  if (!await page.locator('#numberSettings').evaluate(e => e.open)) {
    await page.locator('#numberSettings > summary').click();
  }
};

async function createContext(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const mock = { mode: 'batch', delay: 450, requests: 0, inFlight: 0, maxInFlight: 0, offsets: [] };
  // Prevent accidental third-party traffic. Only the chosen app origin may load.
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== baseOrigin) return route.abort('blockedbyclient');
    if (process.env.BASE_URL) return route.continue();
    return route.fulfill({ contentType: 'text/html; charset=utf-8', body: fixture });
  });
  // Registered last so this route takes precedence over the network guard above.
  await context.route('https://ja.wikipedia.org/w/api.php*', async route => {
    mock.requests++;
    mock.inFlight++;
    mock.maxInFlight = Math.max(mock.maxInFlight, mock.inFlight);
    const mode = mock.mode;
    const offset = Number(new URL(route.request().url()).searchParams.get('sroffset'));
    mock.offsets.push(offset);
    let rows = Array.from({ length: 100 }, (_, i) => ({ title: `検証用候補${offset + i}`, ns: 0 }));
    // Deliberately duplicate a title using full-width digits to test canonical dedup.
    rows[99] = { title: rows[0].title.replace(/[0-9]/g, c => String.fromCharCode(c.charCodeAt(0) + 0xfee0)), ns: 0 };
    if (mode === 'delayed') await new Promise(resolve => setTimeout(resolve, mock.delay));
    if (mode === 'empty') rows = [];
    mock.inFlight--;
    const body = { query: { search: rows } };
    if (mode !== 'empty') body.continue = { sroffset: offset + 100 };
    try {
      await route.fulfill({ contentType: 'application/json', status: mode === 'failure' ? 503 : 200, body: JSON.stringify(body) });
    } catch (error) {
      // Navigation/AbortController can close an intentionally delayed request.
      if (mode !== 'delayed') throw error;
    }
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(baseURL);
  await page.waitForFunction(() => window.KOTOBA_READY === true);
  return { context, page, mock, errors };
}

async function bulkAndPrivacy(browser) {
  const { context, page, mock, errors } = await createContext(browser);
  try {
    await page.click('#autoMode');
    assert.equal(await page.getAttribute('#searchToggle', 'type'), 'checkbox');
    assert.equal(await page.isChecked('#searchToggle'), false);
    const offlineCount = Number((await page.locator('[data-genre=food] span').textContent()).replace(/[^0-9]/g, ''));
    await page.click('[data-genre=food]');
    assert.equal(await page.locator('[data-player]').count(), 3);
    assert.equal(mock.requests, 0);
    const initial = await state(page);
    assert.equal(new Set(initial.current.entries.map(e => e.w)).size, 3);
    pass('checkbox defaults OFF; automatic draw makes no search request');
    await endRound(page);
    assert.equal((await state(page)).used.length, 3);
    pass('ending a round retains duplicate-prevention history');

    await page.click('#autoMode');
    await page.check('#searchToggle');
    await openRefill(page);
    await page.click('#refill');
    await waitStatus(page, '3,000語保存しました。');
    const full = await state(page);
    assert.equal(full.cache.food.words.length, 3000);
    assert.equal(await page.evaluate(() => {
      const saved = JSON.parse(localStorage.getItem('kotoba-party.v1'));
      return new Set(saved.cache.food.words.map(e => KotobaEngine.key(e.w))).size;
    }), 3000);
    assert.equal(mock.maxInFlight, 1);
    assert.equal(mock.requests, 31);
    pass('serial bulk search stores exactly 3,000 canonical unique candidates with real progress');
    await page.uncheck('#searchToggle');
    assert.equal(await page.locator('[data-genre=food] span').textContent(), `未出題 ${offlineCount - 3}語`);
    const beforeOfflineDraw = mock.requests;
    await page.click('[data-genre=food]');
    assert.equal(mock.requests, beforeOfflineDraw);
    assert((await state(page)).current.entries.every(e => e.source !== 'Wikipedia'));
    pass('OFF excludes saved online candidates and starts without any network request');
    await endRound(page);

    await page.click('#manualMode');
    await page.click('#beginManual');
    await page.click('#readyManual');
    assert.equal(await page.isChecked('#searchToggle'), false);
    await page.fill('#manualWord', 'わたあめ試験');
    await page.check('#searchToggle');
    assert.equal(await page.inputValue('#manualWord'), 'わたあめ試験');
    pass('manual search checkbox preserves the current author’s draft');
    await page.locator('#main details > summary').click();
    await page.fill('#query', '場所');
    mock.mode = 'delayed';
    const pending = page.waitForRequest('https://ja.wikipedia.org/w/api.php*');
    await page.click('#searchWords');
    await pending;
    await page.click('#saveManual');
    await page.waitForTimeout(mock.delay + 150);
    assert.equal(await page.locator('#candidateList').count(), 0);
    assert.match(await page.locator('h1').textContent(), /プレイヤー2/);
    await page.click('#readyManual');
    assert.equal(await page.inputValue('#manualWord'), '');
    pass('late manual search cannot populate the next author’s screen');
    await page.fill('#manualWord', '隠すべき入力テスト');
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    assert.equal(await page.locator('#manualWord').count(), 0);
    assert(!(await page.locator('#main').textContent()).includes('隠すべき入力テスト'));
    await page.click('#readyManual');
    assert.equal(await page.inputValue('#manualWord'), '');
    pass('switching away hides and clears the manual secret draft');
    assert.deepEqual(errors, []);
    counts.push({ scenario: 'bulk/privacy', mockedSearchRequests: mock.requests, maxConcurrentSearches: mock.maxInFlight, uniqueCachedWords: full.cache.food.words.length });
  } finally { await context.close(); }
}

async function cancellationAndManual(browser) {
  const { context, page, mock, errors } = await createContext(browser);
  try {
    await page.click('#autoMode');
    await page.check('#searchToggle');
    await openRefill(page);
    mock.mode = 'delayed';
    let pending = page.waitForRequest('https://ja.wikipedia.org/w/api.php*');
    await page.click('#refill');
    await pending;
    await page.uncheck('#searchToggle');
    await page.waitForTimeout(mock.delay + 150);
    assert.equal(await page.isChecked('#searchToggle'), false);
    assert.equal(Object.keys((await state(page)).cache).length, 0);
    pass('turning OFF aborts bulk search and discards its late response');

    await page.check('#searchToggle');
    await openRefill(page);
    pending = page.waitForRequest('https://ja.wikipedia.org/w/api.php*');
    await page.click('#refill');
    await pending;
    await page.click('#back');
    await page.waitForTimeout(mock.delay + 150);
    assert.equal(await page.locator('#playerCount').count(), 1);
    assert.equal(Object.keys((await state(page)).cache).length, 0);
    pass('navigation cancels bulk search without mutating the new screen or cache');

    await page.click('#autoMode');
    await openRefill(page);
    mock.mode = 'batch';
    await page.click('#refill');
    await page.waitForFunction(() => JSON.parse(localStorage.getItem('kotoba-party.v1')).cache.food?.words.length > 0);
    await page.click('#cancelRefill');
    await waitStatus(page, '補充を止めました。');
    const partial = (await state(page)).cache.food.words.length;
    assert(partial > 0 && partial < 3000);
    assert.equal(await page.isDisabled('#refill'), false);
    pass('Stop retains partial candidates and enables continued refill');

    mock.mode = 'empty';
    await page.click('#refill');
    await waitStatus(page, '最後まで取得しました。');
    assert.equal((await state(page)).cache.food.words.length, partial);
    const requestsAtExhaustion = mock.requests;
    await page.click('#refill');
    await waitStatus(page, '最後まで取得しました。');
    assert.equal(mock.requests, requestsAtExhaustion);
    pass('empty/exhausted results stop gracefully and do not fabricate or reuse candidates');

    await page.selectOption('#refillGenre', 'animals');
    mock.mode = 'failure';
    await page.click('#refill');
    await waitStatus(page, '通信または');
    assert.equal(await page.isDisabled('#refill'), false);
    assert.equal((await state(page)).cache.food.words.length, partial);
    pass('API failure restores controls and retains already downloaded candidates');

    await page.click('#back');
    await page.click('#manualMode');
    await page.click('#beginManual');
    const words = ['秘密テスト一', '秘密テスト二', '秘密テスト三'];
    for (const [i, word] of words.entries()) {
      await page.click('#readyManual');
      if (i === 1) {
        await page.fill('#manualWord', ` ${words[0]} `);
        await page.click('#saveManual');
        assert.equal(await page.isVisible('#error'), true);
        assert.match(await page.locator('#error').textContent(), /重複|出題済み/);
        assert.equal((await state(page)).current.step, 1);
        pass('manual assignment rejects a previously assigned canonical word');
      }
      await page.fill('#manualWord', word);
      await page.click('#saveManual');
    }
    await page.click('#goPlay');
    const assigned = await state(page);
    assert.deepEqual(assigned.current.entries.map(e => e.w), [words[2], words[0], words[1]]);
    for (const word of words) assert(!(await page.locator('#main').textContent()).includes(word));
    pass('manual assignments follow 1→2→3→1; numbered player list hides every answer');
    await page.click('[data-player="0"]');
    assert.equal(await page.locator('#word').textContent(), words[2]);
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    assert.equal(await page.isHidden('#overlay'), true);
    assert.equal(await page.locator('#word').textContent(), '');
    pass('revealed answer is cleared when the browser loses focus');
    await endRound(page);
    assert.equal((await state(page)).used.length, 3);
    assert.deepEqual(errors, []);
    counts.push({ scenario: 'cancellation/manual', mockedSearchRequests: mock.requests, retainedPartialWords: partial });
  } finally { await context.close(); }
}

async function replacementFlows(browser) {
  const { context, page, mock, errors } = await createContext(browser);
  try {
    await page.click('#autoMode');
    await page.click('[data-genre=food]');
    const before = await state(page);
    await page.click('[data-player="1"]');
    assert.equal(await page.isVisible('#replaceWord'), true);
    await page.click('#replaceWord');
    await page.click('#dialogCancel');
    assert.deepEqual((await state(page)).current.entries, before.current.entries);
    pass('automatic change confirmation can be cancelled without changing any answer');
    await page.click('[data-player="1"]');
    await page.click('#replaceWord');
    await page.click('#dialogOk');
    const changed = await state(page);
    assert.notEqual(changed.current.entries[1].w, before.current.entries[1].w);
    assert.equal(changed.current.entries[1].c, before.current.entries[1].c);
    assert.deepEqual(changed.current.entries[0], before.current.entries[0]);
    assert.deepEqual(changed.current.entries[2], before.current.entries[2]);
    assert.equal(changed.used.length, 4);
    assert.equal(await page.evaluate(old => JSON.parse(localStorage.getItem('kotoba-party.v1')).used.includes(KotobaEngine.key(old)), before.current.entries[1].w), true);
    assert.equal(await page.locator('#word').textContent(), changed.current.entries[1].w);
    assert.equal(mock.requests, 0);
    pass('automatic change replaces only one player within the genre and keeps the old answer used');
    await page.click('#hideWord');
    await endRound(page);

    await page.click('#manualMode');
    await page.click('#beginManual');
    for (const word of ['手動チェンジ一', '手動チェンジ二', '手動チェンジ三']) {
      await page.click('#readyManual');
      await page.fill('#manualWord', word);
      await page.click('#saveManual');
    }
    await page.click('#goPlay');
    const original = await state(page);
    const beginChange = async () => {
      await page.click('[data-player="1"]');
      assert.equal(await page.isVisible('#replaceWord'), true);
      await page.click('#replaceWord');
      await page.click('#dialogOk');
      assert.match(await page.locator('h1').textContent(), /プレイヤー1/);
    };
    await beginChange();
    await page.click('#cancelReplacement');
    assert.deepEqual((await state(page)).current.entries, original.current.entries);
    assert.deepEqual((await state(page)).used, original.used);
    pass('manual change hands the phone to the original author; gate cancellation preserves the round');

    await beginChange();
    await page.click('#readyReplacement');
    for (const duplicate of [original.current.entries[1].w, original.current.entries[0].w]) {
      await page.fill('#replacementWord', ` ${duplicate} `);
      await page.click('#saveReplacement');
      assert.equal(await page.isVisible('#error'), true);
      assert.match(await page.locator('#error').textContent(), /重複|出題済み/);
      assert.deepEqual((await state(page)).current.entries, original.current.entries);
    }
    pass('manual change rejects the old answer and another player’s answer');
    await page.fill('#replacementWord', 'キャンセルする仮入力');
    await page.click('#cancelReplacement');
    assert.deepEqual((await state(page)).current.entries, original.current.entries);
    assert.deepEqual((await state(page)).used, original.used);
    pass('cancelling a manual change draft leaves all words and history untouched');

    await beginChange();
    await page.click('#readyReplacement');
    await page.fill('#replacementWord', 'アプリ切替で隠す仮入力');
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    assert.equal(await page.locator('#replacementWord').count(), 0);
    assert.equal(await page.isVisible('#readyReplacement'), true);
    assert(!(await page.locator('#main').textContent()).includes('アプリ切替で隠す仮入力'));
    assert.deepEqual((await state(page)).current.entries, original.current.entries);
    await page.click('#readyReplacement');
    assert.equal(await page.inputValue('#replacementWord'), '');
    pass('manual change draft is hidden and discarded when switching away');
    await page.fill('#replacementWord', '新しく決めたチェンジお題');
    await page.click('#saveReplacement');
    const replacement = await state(page);
    assert.equal(replacement.current.entries[1].w, '新しく決めたチェンジお題');
    assert.deepEqual(replacement.current.entries[0], original.current.entries[0]);
    assert.deepEqual(replacement.current.entries[2], original.current.entries[2]);
    assert.equal(replacement.used.length, original.used.length + 1);
    for (const key of original.used) assert(replacement.used.includes(key));
    assert.equal(await page.locator('[data-player]').count(), 3);
    assert(!(await page.locator('#main').textContent()).includes('新しく決めたチェンジお題'));
    pass('manual change commits only the selected answer, hides it, and retains every old history entry');
    assert.deepEqual(errors, []);
    counts.push({ scenario: 'auto/manual replacement', mockedSearchRequests: mock.requests, usedWordsAfterChange: replacement.used.length });
  } finally { await context.close(); }
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', args: ['--no-sandbox'] });
  try {
    await bulkAndPrivacy(browser);
    await cancellationAndManual(browser);
    await replacementFlows(browser);
    console.log(JSON.stringify({ ok: true, passed: completed.length, mode: process.env.BASE_URL ? 'BASE_URL app' : 'in-memory source fixture', wikipedia: 'All search responses mocked locally; live Wikipedia access not verified.', counts }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

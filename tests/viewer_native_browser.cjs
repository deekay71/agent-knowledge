#!/usr/bin/env node
'use strict';

// Additional native-browser proof, separate from the adapter cases in the main
// suite. Always headless: Chromium installs its platform-independent clipboard
// before a platform clipboard is created. Never use pbpaste/pbcopy or read the
// user's OS clipboard. No clipboard or document visibility method is replaced.
// Chromium source: https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/headless/chrome_browser_main_extra_parts_headless.cc
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn, execFileSync} = require('node:child_process');
const {performance} = require('node:perf_hooks');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');

const repo = path.resolve(__dirname, '..');
const output = path.resolve(process.env.VIEWER_BROWSER_OUTPUT || path.join(repo, '.cache/viewer-release-browser'));
const python = process.env.PYTHON || 'python3';
const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
fs.mkdirSync(output, {recursive: true});
const temporary = fs.mkdtempSync(path.join(repo, '.cache/viewer-native-fixtures-'));
const root = path.join(temporary, 'synthetic');
const report = {suite: 'Native headless Chromium clipboard and bounded real-tab visibility proof',
  started_at: new Date().toISOString(), results: [], page_errors: [], external_requests: [], visibility_attempts: [],
  clipboard_scope: 'Unmodified browser Clipboard API in an explicitly headless disposable Chrome process; platform-independent clipboard, not OS clipboard integration.',
  clipboard_source: 'https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/headless/chrome_browser_main_extra_parts_headless.cc'};
let browser, server;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function save() {
  report.passed = report.results.filter(r => r.status === 'passed').length;
  report.failed = report.results.filter(r => r.status === 'failed').length;
  report.unsupported = report.results.filter(r => r.status === 'unsupported').length;
  fs.writeFileSync(path.join(output, 'native-report.json'), JSON.stringify(report, null, 2) + '\n');
}
async function group(name, fn) {
  try { const evidence = await fn(); report.results.push({name, status: 'passed', evidence}); console.log('PASS ' + name); }
  catch (error) { report.results.push({name, status: 'failed', error: error.message}); console.log('FAIL ' + name + ': ' + error.message); }
  save();
}
async function startServer() {
  server = spawn(python, ['-u', path.join(repo, 'scripts/viewer.py'), '--root', root, '--port', '0'], {cwd: repo, stdio: ['ignore', 'pipe', 'pipe']});
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '';
    const timer = setTimeout(() => reject(new Error('Loopback server startup timed out')), 10000);
    server.stdout.on('data', chunk => { stdout += chunk; const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+\//); if (match) { clearTimeout(timer); resolve(match[0]); } });
    server.stderr.on('data', chunk => { stderr += chunk; });
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); if (!stdout.includes('http://')) reject(new Error('Fixture server exited ' + code + ': ' + stderr.slice(0, 500))); });
  });
}
async function main() {
  execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', root, '--topics', '1'], {cwd: repo});
  const url = await startServer();
  browser = await chromium.launch({executablePath: chrome, headless: true,
    args: ['--enable-automation', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps']});
  report.browser = browser.version();
  const browserSession = await browser.newBrowserCDPSession();
  const command = await browserSession.send('Browser.getBrowserCommandLine');
  assert(command.arguments.some(arg => arg === '--headless' || arg.startsWith('--headless=')), 'Clipboard proof must remain headless');
  report.headless_command_verified = true;
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce', locale: 'vi-VN', timezoneId: 'UTC'});
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], {origin: url});
  let graphRequests = 0;
  await context.route('**/*', route => {
    const address = route.request().url();
    if (!address.startsWith(url)) { report.external_requests.push(address); return route.abort('blockedbyclient'); }
    if (new URL(address).pathname === '/api/graph') graphRequests++;
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  await page.goto(url, {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => window.wikiViewer?.getSnapshot() && !document.getElementById('refresh').disabled && document.getElementById('graph-state').hidden);
  await group('native headless clipboard round-trip through the actual copy-context UI', async () => {
    const native = await page.evaluate(() => ({
      noNavigatorOverride: !Object.hasOwn(navigator, 'clipboard'),
      noMethodOverrides: !Object.hasOwn(navigator.clipboard, 'writeText') && !Object.hasOwn(navigator.clipboard, 'readText'),
      writeNative: Function.prototype.toString.call(navigator.clipboard.writeText).includes('[native code]'),
      readNative: Function.prototype.toString.call(navigator.clipboard.readText).includes('[native code]'),
    }));
    assert(Object.values(native).every(Boolean));
    const id = 'wiki/concepts/topic-001/comparison.md';
    await page.locator('#search').fill(id); await page.locator('#search').press('Enter');
    assert.equal(await page.locator('#detail-header .note-path').innerText(), id);
    await page.locator('#copy-context').click();
    await page.waitForFunction(() => document.getElementById('copy-status').textContent.startsWith('Đã sao chép'));
    // Only compare after this UI has written our known synthetic fixture. No
    // pre-existing clipboard read and no clipboard content returned to Node/logs.
    const copied = await page.evaluate(async () => {
      const text = await navigator.clipboard.readText();
      const expected = document.getElementById('context-preview').value;
      return {matches: text === expected, characters: text.length,
        versions: text.includes('SyntheticTopic001/1') && text.includes('SyntheticTopic001/2'),
        fixture: text.includes('Fixture tổng hợp: có'), sourcePaths: text.includes('raw/topic-001/source-v1.md') && text.includes('raw/topic-001/source-v2.md')};
    });
    assert(copied.matches && copied.versions && copied.fixture && copied.sourcePaths);
    assert(copied.characters > 0 && copied.characters <= 16000);
    return {...native, ...copied, browserClipboardOnly: true, osClipboardReadOrWritten: false};
  });

  const pageSession = await context.newCDPSession(page);
  const {targetInfo} = await pageSession.send('Target.getTargetInfo');
  const ownWindow = await browserSession.send('Browser.getWindowForTarget', {targetId: targetInfo.targetId});
  const other = await browserSession.send('Target.createTarget', {url: 'about:blank', browserContextId: targetInfo.browserContextId, newWindow: false, background: false});
  const otherWindow = await browserSession.send('Browser.getWindowForTarget', {targetId: other.targetId});
  report.same_window_verified = ownWindow.windowId === otherWindow.windowId;
  let hidden = false;
  for (const attempt of ['activate sibling target', 'bring sibling page to front']) {
    if (attempt === 'activate sibling target') await browserSession.send('Target.activateTarget', {targetId: other.targetId});
    else {
      const sibling = context.pages().find(p => p !== page);
      if (sibling) await sibling.bringToFront();
    }
    await delay(350);
    const state = await page.evaluate(() => ({hidden: document.hidden, visibility: document.visibilityState,
      overridden: Object.hasOwn(document, 'hidden') || Object.hasOwn(document, 'visibilityState')}));
    report.visibility_attempts.push({attempt, ...state});
    assert.equal(state.overridden, false);
    if (state.hidden && state.visibility === 'hidden' && report.same_window_verified) { hidden = true; break; }
  }
  if (hidden) {
    await group('native same-window tab visibility pauses auto-refresh and resumes a real interval', async () => {
      await browserSession.send('Target.activateTarget', {targetId: targetInfo.targetId});
      await page.waitForFunction(() => !document.hidden);
      await page.locator('#data-tools').evaluate(el => { el.open = true; });
      await page.locator('#refresh-interval').selectOption('15');
      await page.locator('#auto-refresh').check();
      await browserSession.send('Target.activateTarget', {targetId: other.targetId});
      await page.waitForFunction(() => document.hidden);
      const before = graphRequests; await delay(16100);
      assert.equal(graphRequests, before);
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/graph', {timeout: 24000});
      const started = performance.now(); await browserSession.send('Target.activateTarget', {targetId: targetInfo.targetId});
      assert.equal((await response).status(), 200);
      const elapsed = performance.now() - started;
      assert(elapsed >= 14000);
      await page.locator('#auto-refresh').uncheck();
      return {sameWindow: true, visibilityUnmodified: true, hiddenPauseMs: 16100, resumedIntervalMs: elapsed};
    });
  } else {
    report.results.push({name: 'native same-window tab visibility pauses auto-refresh', status: 'unsupported',
      reason: report.same_window_verified ? 'The real sibling-tab activation attempts left document.visibilityState visible; no document or timer overrides were used.' : 'CDP did not place the sibling target in the same window; native hidden-tab behavior was not proven.'});
    console.log('UNSUPPORTED native hidden-tab pause: bounded real-target attempts did not produce hidden state');
  }
  await browserSession.send('Target.closeTarget', {targetId: other.targetId});
  await group('native proof has no page errors or external page requests', async () => {
    assert.deepEqual(report.page_errors, []); assert.deepEqual(report.external_requests, []);
    return {pageErrors: 0, externalRequests: 0};
  });
}
main().catch(error => { report.results.push({name: 'native runner setup/completion', status: 'failed', error: error.message}); console.error(error.message); })
  .finally(async () => {
    if (browser) await browser.close().catch(() => {});
    if (server && server.exitCode === null) server.kill('SIGTERM');
    fs.rmSync(temporary, {recursive: true, force: true});
    report.finished_at = new Date().toISOString(); save();
    console.log(JSON.stringify({passed: report.passed, failed: report.failed, unsupported: report.unsupported, report: path.relative(repo, path.join(output, 'native-report.json'))}));
    process.exitCode = report.failed ? 1 : 0;
  });

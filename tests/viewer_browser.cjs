#!/usr/bin/env node
'use strict';

// Real Chromium integration tests. Only disposable fixture/output directories are
// written; canonical knowledge is read-only. No API responses are mocked.
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright-core CHROME_PATH=/path/to/chrome
// node tests/viewer_browser.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn, execFileSync} = require('node:child_process');
const {performance} = require('node:perf_hooks');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');

const repo = path.resolve(__dirname, '..');
const canonical = path.resolve(process.env.VIEWER_ROOT || repo);
const output = path.resolve(process.env.VIEWER_BROWSER_OUTPUT || path.join(repo, '.cache/viewer-browser'));
const python = process.env.PYTHON || 'python3';
const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
fs.mkdirSync(output, {recursive: true});
const temporary = fs.mkdtempSync(path.join(repo, '.cache/viewer-browser-fixtures-'));
const report = {
  suite: 'Real browser integration; actual temporary-file data and loopback API, no response mocks',
  started_at: new Date().toISOString(),
  environment: {platform: os.platform(), architecture: os.arch(), node: process.version,
    cpu: os.cpus()[0]?.model, logical_cpus: os.cpus().length, memory_gib: Math.round(os.totalmem() / 2 ** 30)},
  metric_notes: 'graph_ready_ms is navigation-to-ready in the browser; layout_ms uses Cytoscape layout events; action_ms includes Playwright dispatch/wait overhead. Single-run observations, not production capacity claims.',
  results: [], metrics: {}, screenshots: [], unexpected_requests: [], page_errors: [], csp_violations: [],
};
const servers = [];
const opened = [];
let browser;

function save() {
  report.passed = report.results.filter(r => r.status === 'passed').length;
  report.failed = report.results.filter(r => r.status === 'failed').length;
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function server(root) {
  const child = spawn(python, ['-u', path.join(repo, 'scripts/viewer.py'), '--root', root, '--port', '0'],
    {cwd: repo, stdio: ['ignore', 'pipe', 'pipe']});
  servers.push(child);
  return await new Promise((resolve, reject) => {
    let stdout = '', stderr = '';
    const timer = setTimeout(() => reject(new Error('Local server startup timed out: ' + stderr)), 10000);
    child.stdout.on('data', chunk => {
      stdout += chunk;
      const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', code => { clearTimeout(timer); if (!stdout.includes('http://')) reject(new Error('Local server exited ' + code + ': ' + stderr)); });
  });
}

async function open(root, label, viewport = {width: 1440, height: 1000}) {
  const url = await server(root);
  const context = await browser.newContext({viewport, deviceScaleFactor: 1,
    reducedMotion: 'reduce', locale: 'vi-VN', timezoneId: 'UTC'});
  const requests = [];
  await context.route('**/*', route => {
    const address = route.request().url();
    if (!address.startsWith(url)) {
      report.unexpected_requests.push({case: label, url: address});
      return route.abort('blockedbyclient');
    }
    requests.push(new URL(address).pathname);
    return route.continue();
  });
  // Read-only timing observer installed before app initialization. Interactions
  // below still use DOM controls and actual canvas mouse coordinates.
  await context.addInitScript(() => {
    window.__browserMetrics = {layouts: [], started: null, csp: []};
    document.addEventListener('securitypolicyviolation', event => {
      window.__browserMetrics.csp.push({directive: event.effectiveDirective, blocked: event.blockedURI});
    });
    Object.defineProperty(window, 'wikiViewer', {configurable: true, set(value) {
      Object.defineProperty(window, 'wikiViewer', {value, configurable: true});
      value.cy.on('layoutstart', () => { window.__browserMetrics.started = performance.now(); });
      value.cy.on('layoutstop', () => {
        window.__browserMetrics.layouts.push(performance.now() - window.__browserMetrics.started);
      });
    }});
  });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => report.page_errors.push({case: label, message: error.message}));
  await page.goto(url, {waitUntil: 'domcontentloaded'});
  await ready(page);
  const timings = await page.evaluate(() => ({graph_ready_ms: performance.now(),
    layout_ms: window.__browserMetrics.layouts.at(-1) ?? null,
    api_ms: performance.getEntriesByType('resource').find(e => e.name.endsWith('/api/graph'))?.duration ?? null}));
  const value = {page, context, requests, label, url, timings};
  opened.push(value);
  report.metrics[label] = timings;
  return value;
}

async function ready(page) {
  await page.waitForFunction(() => window.wikiViewer?.getSnapshot() &&
    !document.getElementById('refresh').disabled && document.getElementById('graph-state').hidden,
    null, {timeout: 30000});
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function screenshot(page, name) {
  await page.screenshot({path: path.join(output, name), fullPage: true});
  report.screenshots.push(name);
}
async function stats(page) {
  return page.evaluate(() => ({nodes: window.wikiViewer.cy.nodes().length,
    edges: window.wikiViewer.cy.edges().length,
    visible_nodes: window.wikiViewer.cy.nodes().not('.filtered').length,
    visible_edges: window.wikiViewer.cy.edges().not('.filtered').length}));
}
async function selectNote(page, id) {
  await page.locator('#search').fill(id);
  await page.locator('#search').press('ArrowDown');
  await page.locator('#search').press('Enter');
  await page.waitForFunction(id => window.wikiViewer.cy.getElementById(id).hasClass('active'), id);
  assert.equal(await page.locator('#detail-header .note-path').innerText(), id);
}
async function point(page, id, edge = false) {
  return page.evaluate(({id, edge}) => {
    const element = window.wikiViewer.cy.getElementById(id);
    const p = edge ? element.renderedMidpoint() : element.renderedPosition();
    const r = document.getElementById('graph').getBoundingClientRect();
    return {x: r.x + p.x, y: r.y + p.y};
  }, {id, edge});
}
async function group(name, fn, page) {
  const start = performance.now();
  try {
    const evidence = await fn();
    report.results.push({name, status: 'passed', duration_ms: performance.now() - start, evidence});
    process.stdout.write('PASS ' + name + '\n');
  } catch (error) {
    const result = {name, status: 'failed', duration_ms: performance.now() - start, error: error.message};
    if (page && !page.isClosed()) {
      const name = 'failure-' + report.results.length + '.png';
      try { await screenshot(page, name); result.screenshot = name; } catch (_) {}
    }
    report.results.push(result);
    process.stdout.write('FAIL ' + name + ': ' + error.message + '\n');
  }
  save();
}
function mutateNote(root, relative, mutate) {
  const file = path.join(root, relative);
  const original = fs.readFileSync(file, 'utf8');
  const match = original.match(/^---json\n([\s\S]*?)\n---\n([\s\S]*)$/);
  assert(match, 'Fixture has metadata');
  const metadata = JSON.parse(match[1]);
  let body = match[2];
  body = mutate(metadata, body) ?? body;
  fs.writeFileSync(file, '---json\n' + JSON.stringify(metadata, null, 2) + '\n---\n' + body);
  execFileSync(python, ['-c', "import sys; from pathlib import Path; sys.path.insert(0,'scripts'); import wiki; r=Path(sys.argv[1]); (r/'wiki/index.md').write_text(wiki.index_text(r),encoding='utf-8')", root], {cwd: repo});
}

async function main() {
  browser = await chromium.launch({executablePath: chrome, headless: true,
    args: ['--no-first-run', '--no-default-browser-check', '--disable-background-networking',
      '--disable-component-update', '--disable-sync', '--disable-default-apps', '--metrics-recording-only']});
  report.environment.browser = browser.version();
  const canonicalPage = await open(canonical, 'canonical');
  const page = canonicalPage.page;
  const queue = 'wiki/concepts/queue.md';
  await group('canonical snapshot renders only its four nodes and nine declared edges', async () => {
    assert.deepEqual(await stats(page), {nodes: 4, edges: 9, visible_nodes: 4, visible_edges: 9});
    assert.equal(await page.locator('#graph canvas').count() > 0, true);
    assert.match(await page.locator('#fixture-text').innerText(), /3 \/ 4/);
    const initial = canonicalPage.requests.filter(p => p === '/api/graph').length;
    await sleep(400);
    assert.equal(canonicalPage.requests.filter(p => p === '/api/graph').length, initial);
    await screenshot(page, 'canonical.png');
    return {nodes: 4, edges: 9, automatic_refresh_observed: false};
  }, page);

  await group('title and path search, keyboard focus, list selection and link directions', async () => {
    await page.locator('#search').fill('Fixture queue');
    assert.equal(await page.locator('#search-results [role=option]').count(), 1);
    await page.locator('#search').press('ArrowDown');
    assert.equal(await page.locator('#search').getAttribute('aria-activedescendant'), 'search-result-0');
    await page.locator('#search').press('Enter');
    assert.equal(await page.locator('#detail-header .note-path').innerText(), queue);
    await page.locator('#tab-links').click();
    const links = await page.locator('#panel-links').innerText();
    assert.match(links, /Đi ra/); assert.match(links, /Đi vào \/ backlinks/);
    const counts = await page.evaluate(id => {
      const edges = window.wikiViewer.getSnapshot().edges;
      return [edges.filter(e => e.source === id).length, edges.filter(e => e.target === id).length];
    }, queue);
    assert.equal(await page.locator('#panel-links .relation-list li').count(), counts[0] + counts[1]);
    await page.locator('#clear-selection').click();
    await page.locator('#clear-search').click();
    await page.locator('#note-list button[title="raw/fixture-v1.md"]').click();
    assert.equal(await page.locator('#detail-header .note-path').innerText(), 'raw/fixture-v1.md');
    await selectNote(page, queue);
    assert.equal(await page.locator('#search').evaluate(el => el === document.activeElement), true);
    return {outgoing: counts[0], backlinks: counts[1]};
  }, page);

  await group('real canvas node click, neighbor highlight, zoom, pan, drag, fit and reset', async () => {
    await page.locator('#reset-view').click();
    await selectNote(page, queue);
    await page.locator('#clear-selection').click();
    const nodePoint = await point(page, queue);
    await page.mouse.click(nodePoint.x, nodePoint.y);
    assert.equal(await page.locator('#detail-header .note-path').innerText(), queue);
    assert(await page.evaluate(id => {
      const cy = window.wikiViewer.cy, selected = cy.getElementById(id);
      return selected.hasClass('active') && cy.nodes('.neighbor').length === selected.closedNeighborhood().nodes().length;
    }, queue));
    const before = await page.evaluate(() => window.wikiViewer.cy.zoom());
    await page.locator('#zoom-in').click();
    assert(await page.evaluate(() => window.wikiViewer.cy.zoom()) > before);
    await page.locator('#zoom-out').click();
    await page.locator('#fit').click();
    const background = await page.evaluate(() => {
      const cy = window.wikiViewer.cy, box = document.getElementById('graph').getBoundingClientRect();
      const candidates = [0.2, 0.4, 0.6, 0.8].flatMap(x => [0.35, 0.5, 0.65].map(y => ({x: box.width * x, y: box.height * y})));
      candidates.sort((a, b) => Math.min(...cy.nodes().map(n => Math.hypot(n.renderedPosition().x - b.x, n.renderedPosition().y - b.y))) - Math.min(...cy.nodes().map(n => Math.hypot(n.renderedPosition().x - a.x, n.renderedPosition().y - a.y))));
      return {x: box.x + candidates[0].x, y: box.y + candidates[0].y, pan: cy.pan()};
    });
    await page.mouse.move(background.x, background.y); await page.mouse.down();
    await page.mouse.move(background.x + 70, background.y + 40, {steps: 10}); await page.mouse.up();
    const pan = await page.evaluate(() => window.wikiViewer.cy.pan());
    assert(Math.hypot(pan.x - background.pan.x, pan.y - background.pan.y) > 20);
    await selectNote(page, queue);
    const start = await point(page, queue);
    const position = await page.evaluate(id => window.wikiViewer.cy.getElementById(id).position(), queue);
    await page.mouse.move(start.x, start.y); await page.mouse.down();
    await page.mouse.move(start.x + 50, start.y + 35, {steps: 12}); await page.mouse.up();
    const moved = await page.evaluate(id => window.wikiViewer.cy.getElementById(id).position(), queue);
    assert(Math.hypot(moved.x - position.x, moved.y - position.y) > 10);
    const layoutCount = await page.evaluate(() => window.__browserMetrics.layouts.length);
    await page.locator('#relayout').click();
    assert(await page.evaluate(() => window.__browserMetrics.layouts.length) > layoutCount);
    await page.locator('#reset-view').click();
    assert.equal(await page.locator('#search').inputValue(), '');
    assert.equal(await page.evaluate(() => window.wikiViewer.cy.elements('.active').length), 0);
    return {canvas_node_clicked: true, node_dragged: true, background_panned: true};
  }, page);

  await group('real canvas edge click opens declared provenance', async () => {
    await page.locator('#reset-view').click();
    const candidates = await page.evaluate(() => window.wikiViewer.cy.edges().map(e => e.id()));
    let selected;
    for (const id of candidates) {
      const p = await point(page, id, true);
      await page.mouse.click(p.x, p.y);
      selected = await page.evaluate(() => window.wikiViewer.cy.edges('.active').map(e => e.data()));
      if (selected.length) break;
    }
    assert(selected?.length, 'An edge can be selected at its actual rendered midpoint');
    const body = await page.locator('#panel-body').innerText();
    assert.match(body, /Vị trí khai báo/);
    assert(body.includes(selected[0].provenance.file));
    assert(body.includes(selected[0].provenance.section));
    await page.locator('#tab-metadata').click();
    assert((await page.locator('#panel-metadata').innerText()).includes(selected[0].id));
    return {kind: selected[0].kind, provenance: selected[0].provenance};
  }, page);

  const demoRoot = path.join(temporary, 'demo');
  execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', demoRoot, '--topics', '8'], {cwd: repo});
  const demoPage = await open(demoRoot, 'demo_49_nodes');
  await group('demo is 49 real synthetic nodes; type AND tag filters and select-all work', async () => {
    const p = demoPage.page;
    assert.deepEqual(await stats(p), {nodes: 49, edges: 227, visible_nodes: 49, visible_edges: 227});
    await screenshot(p, 'demo-49.png');
    await p.locator('details').filter({has: p.locator('#tag-filters')}).locator('summary').click();
    for (const box of await p.locator('#tag-filters input').all()) await box.uncheck();
    await p.locator('#tag-filters input[data-value="topic-001"]').check();
    for (const box of await p.locator('#type-filters input').all()) await box.uncheck();
    const start = performance.now();
    await p.locator('#type-filters input[data-value="concept"]').check();
    assert.equal((await stats(p)).visible_nodes, 3);
    report.metrics.demo_49_nodes.filter_action_ms = performance.now() - start;
    await p.locator('#select-all-types').click();
    assert.equal((await stats(p)).visible_nodes, 6);
    await p.locator('#relayout').click();
    await selectNote(p, 'wiki/concepts/topic-001/comparison.md');
    await p.locator('#clear-search').click();
    await screenshot(p, 'demo-topic-focus.png');
    await p.locator('#panel-body .claim-card.contradiction').scrollIntoViewIfNeeded();
    await screenshot(p, 'demo-comparison-detail.png');
    await p.locator('#select-all-tags').click();
    assert.equal((await stats(p)).visible_nodes, 49);
    await p.locator('details').filter({has: p.locator('#relation-filters')}).locator('summary').click();
    for (const box of await p.locator('#relation-filters input').all()) await box.uncheck();
    assert.equal((await stats(p)).visible_edges, 0);
    await selectNote(p, 'wiki/concepts/topic-001/comparison.md');
    assert.equal(await p.evaluate(() => window.wikiViewer.cy.nodes('.neighbor').not('.active').length), 0,
      'Hidden relationships must not highlight unrelated visible nodes');
    await p.locator('#select-all-relations').click();
    assert.equal((await stats(p)).visible_edges, 227);
    await p.locator('#reset-view').click();
    return {nodes: 49, edges: 227, concept_and_topic: 3, all_types_one_topic: 6};
  }, demoPage.page);

  const hostileRoot = path.join(temporary, 'hostile');
  fs.mkdirSync(hostileRoot);
  fs.cpSync(path.join(canonical, 'raw'), path.join(hostileRoot, 'raw'), {recursive: true});
  fs.cpSync(path.join(canonical, 'wiki'), path.join(hostileRoot, 'wiki'), {recursive: true});
  mutateNote(hostileRoot, queue, (meta, body) => {
    meta.title = 'Security fixture <img src=x onerror="window.__viewerXss=1">';
    meta.claims[0].text = '<svg onload="window.__viewerXss=2"> synthetic claim';
    return body + '\n<script>window.__viewerXss=3</script>\n' +
      '<img src="https://example.invalid/tracker.png" onerror="window.__viewerXss=4">\n' +
      '![remote image](https://example.invalid/pixel.png)\n' +
      '[unsafe](javascript:window.__viewerXss=5)\n' +
      '[external reference](https://example.invalid/reference)\n';
  });
  mutateNote(hostileRoot, 'raw/fixture-v1.md', meta => { meta.origin = 'https://example.invalid/source'; });
  const hostilePage = await open(hostileRoot, 'actual_malicious_fixture');
  await group('actual untrusted source HTML/scripts/images stay inert; external links isolate origin', async () => {
    const p = hostilePage.page;
    await selectNote(p, queue);
    assert.equal(await p.evaluate(() => window.__viewerXss), undefined);
    assert.equal(await p.locator('#detail-content script, #detail-content img, #detail-content svg, #detail-content iframe').count(), 0);
    assert.equal(await p.locator('#detail-content a[href^="javascript:"]').count(), 0);
    assert.equal(await p.locator('#panel-body .image-placeholder').count(), 1);
    assert((await p.locator('#detail-header').innerText()).includes('<img'));
    const external = p.locator('#panel-body a[href="https://example.invalid/reference"]');
    assert.equal(await external.getAttribute('target'), '_blank');
    assert.match(await external.getAttribute('rel'), /noopener/);
    assert.match(await external.getAttribute('rel'), /noreferrer/);
    assert.equal(await external.getAttribute('referrerpolicy'), 'no-referrer');
    await screenshot(p, 'untrusted-note.png');
    await selectNote(p, 'raw/fixture-v1.md');
    const origin = p.locator('#panel-body a[href="https://example.invalid/source"]');
    assert.equal(await origin.getAttribute('target'), '_blank');
    assert.match(await origin.getAttribute('rel'), /noopener noreferrer/);
    assert.equal(report.unexpected_requests.length, 0);
    return {actual_fixture_files: true, html_executed: false, images_loaded: false, external_link_policy: 'noopener noreferrer; no-referrer'};
  }, hostilePage.page);

  await group('manual refresh reads changed files; invalid snapshot visibly clears stale data and recovers', async () => {
    const p = hostilePage.page;
    const oldDigest = await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest);
    const requestCount = hostilePage.requests.filter(p => p === '/api/graph').length;
    mutateNote(hostileRoot, queue, meta => { meta.title = 'REFRESHED SYNTHETIC FIXTURE'; });
    await sleep(700);
    assert.equal(await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest), oldDigest);
    assert.equal(hostilePage.requests.filter(p => p === '/api/graph').length, requestCount);
    await p.locator('#refresh').click(); await ready(p);
    assert.notEqual(await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest), oldDigest);
    await selectNote(p, queue);
    assert.equal(await p.locator('#detail-header h2').innerText(), 'REFRESHED SYNTHETIC FIXTURE');
    const source = path.join(hostileRoot, 'raw/fixture-v1.md');
    const original = fs.readFileSync(source);
    mutateNote(hostileRoot, 'raw/fixture-v1.md', meta => { delete meta.version; });
    await p.locator('#refresh').click();
    await p.waitForFunction(() => document.getElementById('graph-state').classList.contains('is-error') && !document.getElementById('refresh').disabled);
    assert.equal(await p.evaluate(() => window.wikiViewer.getSnapshot()), null);
    assert.equal((await stats(p)).nodes, 0);
    assert.match(await p.locator('#snapshot-label').innerText(), /Không hiển thị dữ liệu cũ/);
    assert.equal(await p.locator('#type-filters input, #tag-filters input, #relation-filters input').count(), 0);
    assert.equal(await p.locator('#detail-header').innerText(), '');
    assert.equal(await p.locator('#snapshot-label').getAttribute('title') || '', '');
    assert.equal(await p.locator('#load-status').getAttribute('title') || '', '');
    await screenshot(p, 'invalid-snapshot.png');
    fs.writeFileSync(source, original);
    await p.locator('#refresh').click(); await ready(p);
    assert.equal((await stats(p)).nodes, 4);
    return {automatic_refresh_observed: false, invalid_data_action: 'clear graph and show error', recovered: true};
  }, hostilePage.page);

  await group('small screen remains usable without horizontal document overflow', async () => {
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('#reset-view').click();
    await selectNote(page, queue);
    await page.locator('#tab-metadata').click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    assert(await page.locator('#search').isVisible());
    assert(await page.locator('#refresh').isVisible());
    await screenshot(page, 'mobile-390.png');
    await page.setViewportSize({width: 1440, height: 1000});
    return {viewport: '390x844', horizontal_document_overflow: false};
  }, page);

  const benchmarkRoot = path.join(temporary, 'benchmark');
  execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', benchmarkRoot, '--topics', '50'], {cwd: repo});
  const benchmark = await open(benchmarkRoot, 'benchmark_301_nodes');
  await group('modest benchmark renders 301 nodes/1403 edges with measured search/filter response', async () => {
    const p = benchmark.page;
    assert.deepEqual(await stats(p), {nodes: 301, edges: 1403, visible_nodes: 301, visible_edges: 1403});
    let start = performance.now();
    await p.locator('#search').fill('wiki/concepts/topic-050/current.md');
    assert.equal(await p.locator('#search-results [role=option]').count(), 1);
    report.metrics.benchmark_301_nodes.search_action_ms = performance.now() - start;
    await p.locator('#search').press('Enter');
    assert.equal(await p.locator('#detail-header .note-path').innerText(), 'wiki/concepts/topic-050/current.md');
    start = performance.now();
    await p.locator('#type-filters input[data-value="source"]').uncheck();
    assert.equal((await stats(p)).visible_nodes, 201);
    report.metrics.benchmark_301_nodes.filter_action_ms = performance.now() - start;
    await p.locator('#reset-view').click();
    await screenshot(p, 'benchmark-301.png');
    return {nodes: 301, edges: 1403, metrics: report.metrics.benchmark_301_nodes};
  }, benchmark.page);

  await group('all browser contexts make no external requests, uncaught page errors or CSP violations', async () => {
    for (const item of opened) {
      const violations = await item.page.evaluate(() => window.__browserMetrics.csp);
      report.csp_violations.push(...violations.map(violation => ({case: item.label, ...violation})));
    }
    assert.deepEqual(report.unexpected_requests, []);
    assert.deepEqual(report.page_errors, []);
    assert.deepEqual(report.csp_violations, []);
    return {contexts: opened.length, external_requests: 0, uncaught_page_errors: 0, csp_violations: 0};
  });
}

main().catch(error => {
  report.results.push({name: 'runner setup/completion', status: 'failed', error: error.stack});
  console.error(error.message);
}).finally(async () => {
  for (const item of opened) await item.context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  for (const process of servers) if (process.exitCode === null) process.kill('SIGTERM');
  fs.rmSync(temporary, {recursive: true, force: true});
  report.finished_at = new Date().toISOString();
  save();
  console.log(JSON.stringify({passed: report.passed, failed: report.failed, report: path.relative(repo, path.join(output, 'report.json'))}));
  process.exitCode = report.failed ? 1 : 0;
});

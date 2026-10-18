'use strict';

// P1 cases called by viewer_browser.cjs. All graph responses come from real
// loopback servers reading disposable fixtures. The clipboard adapter alone is
// captured to avoid overwriting or reading the user's operating-system clipboard.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {performance} = require('node:perf_hooks');

module.exports = async function p1Tests(h) {
  const {repo, temporary, python, report, open, ready, stats, selectNote,
    screenshot, group, mutateNote, sleep} = h;
  const comparison = 'wiki/concepts/topic-001/comparison.md';
  const current = 'wiki/concepts/topic-001/current.md';
  const prior = 'wiki/concepts/topic-001/prior.md';
  const lesson = 'wiki/lessons/topic-001.md';
  const raw = 'raw/topic-001/source-v1.md';
  const raw2 = 'raw/topic-001/source-v2.md';
  const root = path.join(temporary, 'p1');
  execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', root, '--topics', '8'], {cwd: repo});
  mutateNote(root, comparison, (meta, body) => body + '\nBodyNeedle-P1 <img src=x onerror="window.__p1Xss=1">.\n');
  mutateNote(root, lesson, meta => { meta.summary += ' SummaryNeedle-P1'; });
  mutateNote(root, current, meta => { meta.claims[0].text += ' ClaimNeedle-P1'; });
  const pageCase = await open(root, 'p1_49_nodes');
  const p = pageCase.page;

  async function expand(id) { await p.locator(id).evaluate(el => { el.open = true; }); }
  async function visible() { return p.evaluate(() => ({nodes: window.wikiViewer.cy.nodes().not('.filtered').map(e => e.id()).sort(), edges: window.wikiViewer.cy.edges().not('.filtered').map(e => e.id()).sort()})); }
  async function explorationLegible() {
    assert.deepEqual(await p.evaluate(() => window.wikiViewer.cy.elements('.dimmed').not('.filtered').map(e => e.id())), [],
      'Every visible exploration node and edge stays legible, including steps beyond selected-node neighbors');
  }
  async function selected(id) { await p.waitForFunction(id => window.wikiViewer.cy.getElementById(id).hasClass('active'), id); }
  async function baseGraph() {
    // Read public snapshot and checked controls; independently traverse in Node,
    // without calling any frontend traversal implementation.
    return p.evaluate(() => {
      const graph = window.wikiViewer.getSnapshot();
      const checked = id => [...document.querySelectorAll(id + ' input:checked')].map(e => e.dataset.value);
      const types = checked('#type-filters'), tags = checked('#tag-filters'), relations = checked('#relation-filters');
      const status = document.getElementById('status-filter').value;
      const nodes = graph.nodes.filter(n => types.includes(n.kind) && (n.tags.length ? n.tags : ['']).some(t => tags.includes(t)) &&
        (status === 'all' || (status === 'archived') === ['superseded', 'deprecated'].includes(n.status)));
      const ids = new Set(nodes.map(n => n.id));
      return {nodes, edges: graph.edges.filter(e => ids.has(e.source) && ids.has(e.target) && relations.includes(e.kind))};
    });
  }
  function expected(graph, start, mode, depth = 1, target) {
    const ids = new Set(graph.nodes.map(n => n.id));
    if (!ids.has(start)) return {nodes: [], edges: []};
    const allowed = mode === 'sources' ? graph.edges.filter(e => ['sources', 'claim', 'contradiction', 'verification_evidence'].includes(e.kind)) : graph.edges;
    const visited = new Set([start]), frontier = [[start, 0]], previous = new Map(), used = new Set();
    for (const [id, level] of frontier) {
      if (mode === 'hops' && level === depth) continue;
      if (mode === 'sources' && graph.nodes.find(n => n.id === id).kind === 'source') continue;
      for (const edge of allowed) {
        let neighbor = edge.source === id ? edge.target : mode === 'hops' && edge.target === id ? edge.source : null;
        if (neighbor === null) continue;
        if (mode === 'sources') used.add(edge.id);
        if (!visited.has(neighbor)) { visited.add(neighbor); frontier.push([neighbor, level + 1]); previous.set(neighbor, edge); }
      }
    }
    if (mode === 'hops') for (const edge of allowed) if (visited.has(edge.source) && visited.has(edge.target)) used.add(edge.id);
    if (mode === 'path') {
      const route = new Set([start]);
      if (visited.has(target)) for (let cursor = target; cursor !== start;) { const edge = previous.get(cursor); route.add(cursor); used.add(edge.id); cursor = edge.source; }
      return {nodes: [...route].sort(), edges: [...used].sort()};
    }
    return {nodes: [...visited].sort(), edges: [...used].sort()};
  }
  async function checkTraversal(start, mode, depth, target) {
    const wanted = expected(await baseGraph(), start, mode, depth, target);
    assert.deepEqual(await visible(), wanted);
    return {nodes: wanted.nodes.length, edges: wanted.edges.length};
  }
  async function apiStatus(action) {
    const response = p.waitForResponse(response => new URL(response.url()).pathname === '/api/graph');
    await action();
    return await response;
  }

  await group('P1 full-text body and summary search produces safe snippets and keeps filters', async () => {
    await p.locator('#search').fill('BodyNeedle-P1');
    assert.deepEqual(await p.locator('#search-results .result-path').allTextContents(), [comparison]);
    assert.match(await p.locator('#search-results .result-field').innerText(), /Nội dung/);
    assert((await p.locator('#search-results .result-snippet').innerText()).includes('<img'));
    assert.equal(await p.locator('#search-results img, #search-results script').count(), 0);
    await p.locator('#search').press('Enter'); await selected(comparison);
    await p.locator('#search').fill('SummaryNeedle-P1');
    const summary = p.locator('#search-results [role=option]').filter({has: p.locator('.result-path', {hasText: lesson})});
    assert.match(await summary.locator('.result-field').innerText(), /Tóm tắt/);
    await p.locator('#type-filters input[data-value="lesson"]').uncheck();
    assert(!(await p.locator('#search-results .result-path').allTextContents()).includes(lesson));
    await p.locator('#search').fill('ClaimNeedle-P1');
    assert.deepEqual(await p.locator('#search-results .result-path').allTextContents(), [current]);
    assert.match(await p.locator('#search-results .result-field').innerText(), /Claim đã khai báo/);
    assert.equal(await p.evaluate(() => window.__p1Xss), undefined);
    await p.locator('#reset-view').click();
    return {body_only_match: comparison, summary_match: lesson, claim_only_match: current, snippet_html_inert: true};
  }, p);

  await group('P1 one/two-hop and source traces follow actual filtered edges', async () => {
    await p.locator('#reset-view').click(); await expand('#exploration');
    await p.locator('details').filter({has: p.locator('#relation-filters')}).evaluate(el => { el.open = true; });
    await p.locator('#type-filters input[data-value="navigation"]').uncheck();
    await selectNote(p, comparison); await p.locator('#hop-one').click();
    const one = await checkTraversal(comparison, 'hops', 1);
    await p.locator('#hop-two').click(); const two = await checkTraversal(comparison, 'hops', 2);
    assert(two.nodes >= one.nodes);
    await explorationLegible();
    await p.locator('#status-filter').selectOption('current');
    await checkTraversal(comparison, 'hops', 2);
    assert(!(await visible()).nodes.includes(prior));
    await p.locator('details').filter({has: p.locator('#tag-filters')}).evaluate(el => { el.open = true; });
    for (const box of await p.locator('#tag-filters input').all()) await box.uncheck();
    await p.locator('#tag-filters input[data-value="topic-001"]').check();
    await checkTraversal(comparison, 'hops', 2);
    await selectNote(p, comparison); await p.locator('#trace-sources').click();
    const sources = await checkTraversal(comparison, 'sources');
    assert.deepEqual((await visible()).nodes, [comparison, raw, raw2].sort());
    for (const box of await p.locator('#relation-filters input').all()) await box.uncheck();
    assert.deepEqual(await visible(), {nodes: [comparison], edges: []});
    await p.locator('#select-all-relations').click(); await checkTraversal(comparison, 'sources');
    await screenshot(p, 'p1-source-trace.png');
    await p.locator('#reset-view').click();
    return {one_hop: one, two_hops: two, source_trace: sources, hidden_relations_cannot_be_traversed: true};
  }, p);

  await group('P1 directed paths expose real provenance and reject filtered or reversed routes', async () => {
    await p.locator('#reset-view').click(); await expand('#exploration');
    await p.locator('details').filter({has: p.locator('#relation-filters')}).evaluate(el => { el.open = true; });
    for (const box of await p.locator('#relation-filters input').all()) await box.uncheck();
    await p.locator('#relation-filters input[data-value="link"]').check();
    const target = 'wiki/lessons/topic-004.md';
    await selectNote(p, lesson); await p.locator('#path-start').click();
    await selectNote(p, target); await p.locator('#path-find').click();
    const route = await checkTraversal(lesson, 'path', 1, target);
    assert.equal(route.edges, 3); assert.equal(route.nodes, 4);
    await explorationLegible();
    const graph = await baseGraph();
    const displayed = await visible();
    const routeText = await p.locator('#exploration-results').innerText();
    for (const id of displayed.edges) {
      const edge = graph.edges.find(e => e.id === id);
      assert(routeText.includes(edge.provenance.file)); assert(routeText.includes(edge.provenance.section));
    }
    await screenshot(p, 'p1-directed-path.png');
    await p.locator('#relation-filters input[data-value="link"]').uncheck();
    await checkTraversal(lesson, 'path', 1, target);
    assert.match(await p.locator('#exploration-summary').innerText(), /Không có đường/);
    await p.locator('#reset-view').click();
    await selectNote(p, raw); await p.locator('#path-start').click();
    await selectNote(p, comparison); await p.locator('#path-find').click();
    await checkTraversal(raw, 'path', 1, comparison);
    assert.match(await p.locator('#exploration-summary').innerText(), /Không có đường/);
    await p.locator('#reset-view').click();
    return {directed_route: route, reversed_evidence_route: false, filtered_link_route: false};
  }, p);

  await group('P1 status filter distinguishes archived pages and composes with types/tags', async () => {
    await p.locator('#reset-view').click();
    await p.locator('#status-filter').selectOption('archived');
    assert.equal((await stats(p)).visible_nodes, 8);
    assert((await visible()).nodes.every(id => id.endsWith('/prior.md')));
    await p.locator('#type-filters input[data-value="concept"]').uncheck();
    assert.equal((await stats(p)).visible_nodes, 0);
    await p.locator('#select-all-types').click();
    await p.locator('#status-filter').selectOption('current');
    assert.equal((await stats(p)).visible_nodes, 41);
    await p.locator('#status-filter').selectOption('all');
    assert.equal((await stats(p)).visible_nodes, 49);
    return {archived: 8, current: 41, all: 49, archived_without_concepts: 0};
  }, p);

  await group('P1 real browser back/forward restores note tab and hops; repeat clicks do not add history', async () => {
    await p.locator('#reset-view').click();
    await selectNote(p, current);
    const currentHash = new URL(p.url()).hash;
    const length = await p.evaluate(() => history.length);
    const sameResult = p.locator('#search-results [role=option]').filter({has: p.locator('.result-path', {hasText: current})});
    await sameResult.click(); await sameResult.click();
    assert.equal(await p.evaluate(() => history.length), length);
    await p.locator('#tab-links').click();
    const linksHash = new URL(p.url()).hash;
    assert.notEqual(linksHash, currentHash);
    await selectNote(p, comparison); const comparisonHash = new URL(p.url()).hash;
    const apiCalls = pageCase.requests.filter(path => path === '/api/graph').length;
    await p.goBack(); await selected(current);
    assert.equal(new URL(p.url()).hash, linksHash);
    assert.equal(await p.locator('#tab-links').getAttribute('aria-selected'), 'true');
    await p.goBack(); await selected(current);
    assert.equal(new URL(p.url()).hash, currentHash);
    assert.equal(await p.locator('#tab-body').getAttribute('aria-selected'), 'true');
    await p.goForward(); await selected(current);
    await p.goForward(); await selected(comparison);
    assert.equal(new URL(p.url()).hash, comparisonHash);
    await p.locator('#hop-one').click(); const hops = await visible();
    await p.locator('#clear-exploration').click();
    await p.goBack(); await selected(comparison);
    assert.deepEqual(await visible(), hops);
    await p.goForward();
    assert.equal((await stats(p)).visible_nodes, 49);
    assert.equal(pageCase.requests.filter(path => path === '/api/graph').length, apiCalls);
    const beforeRefresh = await p.evaluate(() => history.length);
    await p.locator('#refresh').click(); await ready(p);
    assert.equal(await p.evaluate(() => history.length), beforeRefresh);
    return {actual_back_forward: true, duplicate_clicks_add_entries: false, navigation_fetches: 0, refresh_pushes_entry: false};
  }, p);

  await group('P1 initial deep links restore existing nodes and reject unknown paths without fetching files', async () => {
    const hash = '#' + new URLSearchParams({v: '1', note: comparison, tab: 'metadata', mode: 'sources', root: comparison});
    const linked = await open(root, 'p1_initial_deep_link', undefined, {hash});
    const q = linked.page;
    assert.equal(await q.locator('#detail-header .note-path').innerText(), comparison);
    assert.equal(await q.locator('#tab-metadata').getAttribute('aria-selected'), 'true');
    assert.equal((await stats(q)).visible_nodes, 3);
    const callCount = linked.requests.length;
    for (const invalid of [
      '#v=1&note=..%2Foutside-private.md', '#v=1&note=' + encodeURIComponent(comparison) + '&note=' + encodeURIComponent(raw),
      '#v=2&note=' + encodeURIComponent(raw), '#v=1&mode=hops&root=' + encodeURIComponent(raw) + '&depth=200',
    ]) {
      await q.evaluate(hash => { location.hash = hash; }, invalid);
      await q.waitForFunction(() => !document.getElementById('navigation-status').hidden);
      assert.equal(await q.evaluate(() => window.wikiViewer.cy.elements('.active').length), 0);
    }
    assert.equal(linked.requests.length, callCount);
    return {initial_link: 'existing comparison + source trace + metadata', rejected_invalid_links: 4, arbitrary_file_requests: 0};
  }, p);

  await group('P1 cited context preserves versions evidence and hostile text with safe clipboard fallback', async () => {
    await p.locator('#reset-view').click(); await selectNote(p, comparison);
    await p.evaluate(() => {
      window.__clipboardCalls = [];
      Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async text => { window.__clipboardCalls.push(text); }}});
    });
    await p.locator('#copy-context').click();
    const context = await p.locator('#context-preview').inputValue();
    assert.equal(context, await p.evaluate(() => window.__clipboardCalls.at(-1)));
    for (const value of [raw, raw2, 'SyntheticTopic001/1', 'SyntheticTopic001/2', 'OPEN synthetic contradiction', 'Fixture tổng hợp: có', 'draft', 'BodyNeedle-P1', '<img']) assert(context.includes(value), 'Cited context includes ' + value);
    assert(context.length <= 16000);
    assert(context.indexOf('## Mâu thuẫn khai báo') < context.indexOf('## Nội dung'));
    assert.match(context, /Trạng thái: open/);
    assert.equal(await p.locator('#context-preview').getAttribute('readonly'), '');
    assert.equal(await p.evaluate(() => window.__p1Xss), undefined);
    await selectNote(p, lesson); await p.locator('#copy-context').click();
    assert.match(await p.locator('#context-preview').inputValue(), /\[Suy luận\]/);
    await p.evaluate(() => { navigator.clipboard.writeText = async () => { throw new Error('Test-only permission denial'); }; });
    await p.locator('#copy-context').click();
    assert.match(await p.locator('#copy-status').innerText(), /sao chép thủ công/);
    assert(await p.locator('#context-preview').evaluate(el => el.selectionStart === 0 && el.selectionEnd === el.value.length));
    await screenshot(p, 'p1-cited-context.png');
    return {clipboard: 'test adapter captures writeText payload; OS clipboard untouched and not tested', inference_preserved: true, hostile_markup_inert: true, fallback_selected_text: true};
  }, p);

  await group('P1 real structural diagnostics remain navigable without phantom nodes or private payloads', async () => {
    await p.locator('#reset-view').click();
    // Excluded project area contains only an invented sentinel, never real data.
    fs.mkdirSync(path.join(root, 'knowledge/project'), {recursive: true});
    fs.writeFileSync(path.join(root, 'knowledge/project/private.md'), 'SYNTHETIC_PRIVATE_SENTINEL_OUTSIDE_SCOPE');
    fs.copyFileSync(path.join(root, lesson), path.join(root, 'wiki/lessons/orphan.md'));
    mutateNote(root, 'wiki/lessons/orphan.md', (meta, body) => { meta.id = 'p1-orphan'; meta.title = 'SYNTHETIC orphan'; return '# SYNTHETIC orphan\nNo knowledge page links here.\n'; });
    mutateNote(root, comparison, (meta, body) => body + '\n[Missing page](missing-p1.md)\n');
    fs.unlinkSync(path.join(root, raw2));
    fs.appendFileSync(path.join(root, 'wiki/index.md'), '\nSYNTHETIC index drift\n');
    const response = await apiStatus(() => p.locator('#refresh').click());
    assert.equal(response.status(), 200); await ready(p);
    const snapshot = await p.evaluate(() => window.wikiViewer.getSnapshot());
    const codes = new Set(snapshot.diagnostics.map(d => d.code));
    for (const code of ['missing_source', 'broken_link', 'orphan_page', 'index_drift']) assert(codes.has(code), code);
    const ids = new Set(snapshot.nodes.map(n => n.id));
    assert(!ids.has(raw2));
    assert(snapshot.edges.every(e => ids.has(e.source) && ids.has(e.target) && e.explicit));
    assert(snapshot.diagnostics.every(d => ids.has(d.source)));
    assert.equal(snapshot.nodes.find(n => n.id === comparison).evidence_complete, false);
    assert(!JSON.stringify(snapshot).includes('SYNTHETIC_PRIVATE_SENTINEL_OUTSIDE_SCOPE'));
    assert.equal(Number(await p.locator('#diagnostic-count').innerText()), snapshot.diagnostics.length);
    assert.equal(snapshot.nodes.find(n => n.id === 'wiki/index.md').body_withheld, true);
    assert(!JSON.stringify(snapshot).includes('SYNTHETIC index drift'));
    await p.locator('#search').fill('SYNTHETIC index drift');
    assert.equal(await p.locator('#search-results [role=option]').count(), 0);
    await selectNote(p, 'wiki/index.md'); await p.locator('#copy-context').click();
    const indexContext = await p.locator('#context-preview').inputValue();
    assert(!indexContext.includes('SYNTHETIC index drift'));
    assert(indexContext.includes('Nội dung bị giữ lại: CÓ'));
    await expand('#diagnostics');
    assert.equal(await p.locator('#diagnostic-list button[title="' + raw2 + '"]').count(), 0);
    await p.locator('#diagnostic-list button[title="' + comparison + '"]').first().click();
    await selected(comparison); await p.locator('#copy-context').click();
    const context = await p.locator('#context-preview').inputValue();
    assert(context.includes('THIẾU NGUỒN')); assert(context.includes('missing_source'));
    await screenshot(p, 'p1-structural-diagnostics.png');
    const sourcePath = path.join(root, raw), sourceBytes = fs.readFileSync(sourcePath);
    mutateNote(root, raw, meta => { meta.scope = 'project'; meta.title = 'SYNTHETIC_PRIVATE_SENTINEL_IN_SCOPE'; });
    const rejected = await apiStatus(() => p.locator('#refresh').click());
    assert.equal(rejected.status(), 422);
    const payload = await rejected.text();
    assert(!payload.includes('SYNTHETIC_PRIVATE_SENTINEL')); assert(!payload.includes('"nodes"'));
    await p.waitForFunction(() => !document.getElementById('refresh').disabled);
    assert.equal(await p.evaluate(() => window.wikiViewer.getSnapshot()), null);
    assert.equal(await p.locator('#context-preview').inputValue(), '');
    assert.equal(await p.locator('#diagnostic-list').innerText(), '');
    assert.equal((await stats(p)).nodes, 0);
    fs.writeFileSync(sourcePath, sourceBytes);
    await p.locator('#refresh').click(); await ready(p);
    return {diagnostic_codes: [...codes].sort(), count: snapshot.diagnostics.length, diagnostic_http: 200, private_scope_http: 422, private_payload_returned: false, dangling_edges: 0};
  }, p);

  await group('P1 manual refresh preserves valid filtered hops and updates body only on request', async () => {
    await p.locator('#reset-view').click(); await selectNote(p, comparison);
    await p.locator('#status-filter').selectOption('current'); await p.locator('#hop-one').click();
    const before = await visible(), beforeHash = new URL(p.url()).hash;
    const oldDigest = await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest);
    const requestCount = pageCase.requests.filter(path => path === '/api/graph').length;
    mutateNote(root, comparison, (meta, body) => body + '\nP1 manual refresh body marker\n');
    await sleep(400);
    assert.equal(await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest), oldDigest);
    assert.equal(pageCase.requests.filter(path => path === '/api/graph').length, requestCount);
    await p.locator('#refresh').click(); await ready(p);
    assert.equal(new URL(p.url()).hash, beforeHash);
    assert.deepEqual(await visible(), before);
    assert.equal(await p.locator('#status-filter').inputValue(), 'current');
    assert((await p.locator('#panel-body').innerText()).includes('P1 manual refresh body marker'));
    assert.notEqual(await p.evaluate(() => window.wikiViewer.getSnapshot().source_digest), oldDigest);
    return {filter_mode_selection_preserved: true, automatic_refresh: false, body_updated: true};
  }, p);

  await group('P1 selected-all refresh includes new tags and relation kinds without losing state', async () => {
    const refreshRoot = path.join(temporary, 'p1-refresh-new-kind');
    execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', refreshRoot, '--topics', '1'], {cwd: repo});
    mutateNote(refreshRoot, current, meta => { delete meta.supersedes; });
    mutateNote(refreshRoot, prior, meta => { delete meta.superseded_by; meta.status = 'draft'; });
    const refreshCase = await open(refreshRoot, 'p1_new_tag_relation');
    const q = refreshCase.page;
    await selectNote(q, comparison);
    assert.equal(await q.locator('#relation-filters input[data-value="supersedes"]').count(), 0);
    mutateNote(refreshRoot, current, meta => { meta.supersedes = [prior]; });
    mutateNote(refreshRoot, prior, meta => { meta.superseded_by = current; meta.status = 'superseded'; });
    mutateNote(refreshRoot, comparison, meta => {
      meta.tags.push('new-p1-tag');
      meta.updated_at = '2025-01-01';
    });
    await q.locator('#refresh').click(); await ready(q);
    assert.equal(await q.locator('#tag-filters input[data-value="new-p1-tag"]').isChecked(), true);
    assert.equal(await q.locator('#relation-filters input[data-value="supersedes"]').isChecked(), true);
    const snapshot = await q.evaluate(() => window.wikiViewer.getSnapshot());
    assert(await q.evaluate(id => !window.wikiViewer.cy.getElementById(id).hasClass('filtered'), snapshot.edges.find(e => e.kind === 'supersedes').id));
    assert(snapshot.warnings.length > 0, 'Deliberately stale fixture must carry a warning');
    mutateNote(refreshRoot, comparison, (meta, body) => body + '\n' + 'SYNTHETIC bounded context text. '.repeat(700));
    await q.locator('#refresh').click(); await ready(q);
    await q.evaluate(() => { Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async () => {}}}); });
    await q.locator('#copy-context').click();
    const context = await q.locator('#context-preview').inputValue();
    assert(context.length <= 16000);
    assert(context.indexOf('Trạng thái: open') < context.indexOf('## Nội dung'));
    assert(context.indexOf('- Cảnh báo snapshot:') < context.indexOf('## Nội dung'));
    assert(context.includes('[cắt ngắn]'));
    return {new_tag_selected: true, new_relation_selected: true, warnings_and_open_contradiction_before_truncated_body: true};
  }, p);

  const largeRoot = path.join(temporary, 'p1-large');
  execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', largeRoot, '--topics', '200'], {cwd: repo});
  const large = await open(largeRoot, 'p1_large_1201_nodes', undefined, {timeout: 60000});
  await group('P1 larger synthetic graph renders 1201 nodes/5603 edges with usable full-text and source trace', async () => {
    const q = large.page;
    assert.deepEqual(await stats(q), {nodes: 1201, edges: 5603, visible_nodes: 1201, visible_edges: 5603});
    let start = performance.now();
    await q.locator('#search').fill('capacities 406 and 414');
    // This body-only phrase belongs to topic 200; metadata title/path lacks it.
    assert((await q.locator('#search-results .result-path').allTextContents()).includes('wiki/concepts/topic-200/comparison.md'));
    report.metrics.p1_large_1201_nodes.fulltext_action_ms = performance.now() - start;
    await selectNote(q, 'wiki/concepts/topic-200/comparison.md');
    await q.locator('#exploration').evaluate(el => { el.open = true; });
    start = performance.now(); await q.locator('#trace-sources').click();
    assert.equal((await stats(q)).visible_nodes, 3);
    report.metrics.p1_large_1201_nodes.source_trace_action_ms = performance.now() - start;
    await screenshot(q, 'p1-large-focused.png');
    return {nodes: 1201, edges: 5603, source_trace_nodes: 3, metrics: report.metrics.p1_large_1201_nodes, capacity_claim: 'single synthetic run only'};
  }, large.page);
  return {large};
};

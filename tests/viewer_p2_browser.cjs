'use strict';

// Invoked by viewer_browser.cjs. Only generated fixtures and disposable browser
// state are written; comparison/refresh/export use the actual loopback API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {performance} = require('node:perf_hooks');

module.exports = async function p2Tests(h) {
  const {repo, temporary, output, python, report, open, ready, stats, selectNote,
    screenshot, group, mutateNote, sleep, phases} = h;
  const comparison = 'wiki/concepts/topic-001/comparison.md';
  const current = 'wiki/concepts/topic-001/current.md';
  const source = 'raw/topic-001/source-v1.md';
  const makeDemo = (name, topics = 3) => {
    const root = path.join(temporary, name);
    execFileSync(python, [path.join(repo, 'scripts/viewer_demo.py'), '--output', root, '--topics', String(topics)], {cwd: repo});
    return root;
  };
  const git = (root, ...args) => execFileSync('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', '-c', 'core.fsmonitor=false', '-c', 'user.name=Synthetic Browser Fixture',
    '-c', 'user.email=synthetic@example.invalid', ...args], {cwd: root, encoding: 'utf8'}).trim();
  const commit = (root, message) => { git(root, 'add', 'raw', 'wiki'); git(root, 'commit', '-q', '-m', message); return git(root, 'rev-parse', 'HEAD'); };
  const root = makeDemo('p2-clusters');
  fs.mkdirSync(path.join(root, 'knowledge/project'), {recursive: true});
  fs.writeFileSync(path.join(root, 'knowledge/project/excluded.md'), 'SYNTHETIC_EXCLUDED_FROM_DOWNLOAD');
  const pageCase = await open(root, 'p2_clusters_19_nodes');
  const p = pageCase.page;
  const graph = await p.evaluate(() => window.wikiViewer.getSnapshot());

  // Additional P2 groups are below. Fixtures never modify canonical knowledge.
  async function expand(page, id) { await page.locator(id).evaluate(el => { el.open = true; }); }
  async function positions(page) { return page.evaluate(() => Object.fromEntries(window.wikiViewer.getSnapshot().nodes.map(n => [n.id, window.wikiViewer.cy.getElementById(n.id).position()]))); }
  async function dragNode(page, id) {
    await selectNote(page, id);
    const at = await page.evaluate(id => {
      const node = window.wikiViewer.cy.getElementById(id), point = node.renderedPosition();
      const box = document.getElementById('graph').getBoundingClientRect();
      return {x: box.x + point.x, y: box.y + point.y};
    }, id);
    await page.mouse.move(at.x, at.y); await page.mouse.down();
    await page.mouse.move(at.x + 60, at.y + 45, {steps: 12}); await page.mouse.up();
  }
  async function derived(page) { return page.evaluate(() => ({nodes: window.wikiViewer.cy.nodes('[derived]').map(n => n.data()), edges: window.wikiViewer.cy.edges('[derived]').map(e => e.data())})); }
  async function canvasClick(page, id, edge = false) {
    const at = await page.evaluate(({id, edge}) => {
      const element = window.wikiViewer.cy.getElementById(id);
      const point = edge ? element.renderedMidpoint() : element.renderedPosition();
      const box = document.getElementById('graph').getBoundingClientRect();
      return {x: box.x + point.x, y: box.y + point.y};
    }, {id, edge});
    await page.mouse.click(at.x, at.y);
  }
  await group('P2 deterministic type and rare-tag groups collapse real members and preserve counts', async () => {
    await expand(p, '#view-options'); await p.locator('#group-mode').selectOption('type');
    const initial = await derived(p);
    assert.equal(initial.nodes.length, 4);
    const groupsByType = Object.fromEntries(initial.nodes.map(n => [decodeURIComponent(n.id.split(':').at(-1)), n.member_ids.slice().sort()]));
    for (const kind of ['source', 'concept', 'lesson', 'navigation']) assert.deepEqual(groupsByType[kind], graph.nodes.filter(n => n.kind === kind).map(n => n.id).sort());
    assert(initial.nodes.every(n => n.derived === true && n.explicit === false && n.count === n.member_ids.length));
    await p.locator('#collapse-groups').click(); await p.locator('#collapse-groups').click();
    assert.deepEqual((await derived(p)).nodes.map(n => [n.id, n.member_ids]), initial.nodes.map(n => [n.id, n.member_ids]));
    await p.locator('#expand-groups').click(); await p.locator('#expand-groups').click();
    assert.equal((await derived(p)).nodes.length, 0);
    assert.deepEqual(await stats(p), {nodes: 19, edges: 86, visible_nodes: 19, visible_edges: 86});
    await p.locator('#collapse-groups').click(); await p.locator('#relayout').click();
    const groupId = initial.nodes.find(n => n.id.endsWith(':concept')).id;
    await canvasClick(p, groupId);
    assert.match(await p.locator('#detail-header').innerText(), /Nhóm giao diện/);
    assert.equal(await p.locator('#panel-body .group-member-list button').count(), 9);
    await p.locator('#expand-selected-group').click();
    assert.equal((await derived(p)).nodes.length, 3);
    await p.locator('#group-mode').selectOption('tag');
    const tagGroups = await derived(p);
    const counts = new Map();
    for (const node of graph.nodes) for (const tag of node.tags.length ? node.tags : ['']) counts.set(tag, (counts.get(tag) || 0) + 1);
    for (const groupNode of tagGroups.nodes) for (const id of groupNode.member_ids) {
      const node = graph.nodes.find(n => n.id === id);
      const least = (node.tags.length ? node.tags : ['']).slice().sort((a, b) => counts.get(a) - counts.get(b) || (a < b ? -1 : a > b ? 1 : 0))[0];
      assert.equal(groupNode.id, 'ui:group:tag:' + encodeURIComponent(least));
    }
    await p.locator('#type-filters input[data-value="source"]').uncheck();
    assert.match(await p.locator('#graph-stats').innerText(), /^13 \/ 19 ghi chú/);
    assert.equal((await derived(p)).nodes.reduce((sum, n) => sum + n.count, 0), 13);
    assert.deepEqual(await p.evaluate(() => window.wikiViewer.getSnapshot()), graph);
    await screenshot(p, 'p2-groups.png');
    return {canonical_nodes: 19, canonical_edges: 86, type_groups: 4, tag_groups: 4, filtered_members: 13, repeated_controls_idempotent: true};
  }, p);

  await group('P2 aggregate edges expose only underlying declared edge provenance', async () => {
    await p.locator('#reset-view').click(); await expand(p, '#view-options'); await p.locator('#group-mode').selectOption('type');
    await p.locator('#collapse-groups').click(); await p.locator('#relayout').click();
    const grouped = await derived(p), real = new Map(graph.edges.map(e => [e.id, e]));
    assert(grouped.edges.length > 0);
    const mappedIds = grouped.edges.flatMap(e => e.underlying_edge_ids).sort();
    assert.deepEqual(mappedIds, graph.edges.map(e => e.id).sort());
    for (const edge of grouped.edges) {
      assert.equal(edge.explicit, false); assert.equal(edge.derived, true);
      assert.equal(edge.count, edge.underlying_edge_ids.length);
      assert(edge.underlying_edge_ids.every(id => real.get(id)?.kind === edge.kind));
    }
    let chosen;
    for (const edge of grouped.edges.filter(e => e.source !== e.target)) {
      await canvasClick(p, edge.id, true);
      if ((await p.locator('#detail-header').innerText()).includes('Cạnh tổng hợp')) {
        chosen = await p.evaluate(() => window.wikiViewer.cy.edges('.active').first().data()); break;
      }
    }
    assert(chosen, 'An aggregate can be selected using its real canvas midpoint');
    const text = await p.locator('#panel-body').innerText();
    for (const id of chosen.underlying_edge_ids.slice(0, 60)) {
      const edge = real.get(id); assert(text.includes(edge.provenance.file)); assert(text.includes(edge.provenance.section));
    }
    return {canonical_edges_covered_once: mappedIds.length, selected_aggregate_members: chosen.count, all_provenance_real: true};
  }, p);

  await group('P2 saved layout restores coordinates and preferences and rejects malformed or foreign storage', async () => {
    await p.locator('#reset-view').click(); await p.locator('#group-mode').selectOption('none');
    await dragNode(p, current);
    await p.locator('#type-filters input[data-value="navigation"]').uncheck();
    await p.locator('#status-filter').selectOption('current');
    await p.locator('#save-layout').click();
    const key = 'agent-knowledge.viewer.v1.' + graph.corpus_id;
    const stored = await p.evaluate(key => localStorage.getItem(key), key);
    assert(stored, 'Record is keyed by the corpus identity');
    const record = JSON.parse(stored), before = await positions(p);
    assert.equal(record.corpus_id, graph.corpus_id); assert.equal(record.format, 1);
    assert(!stored.includes('Invented fixture')); assert(!stored.includes('capacity is'));
    await p.locator('#reset-view').click(); await dragNode(p, current);
    await p.locator('#restore-layout').click();
    assert.deepEqual(await positions(p), before);
    assert.equal(await p.locator('#status-filter').inputValue(), 'current');
    assert.equal(await p.locator('#type-filters input[data-value="navigation"]').isChecked(), false);
    await p.evaluate(() => history.replaceState(null, '', location.pathname));
    await p.reload(); await ready(p);
    assert.deepEqual(await positions(p), before);
    assert.equal(await p.locator('#status-filter').inputValue(), 'current');
    const otherRoot = makeDemo('p2-other-corpus', 3), otherCase = await open(otherRoot, 'p2_other_corpus');
    const otherCorpus = await otherCase.page.evaluate(() => window.wikiViewer.getSnapshot().corpus_id);
    assert.notEqual(otherCorpus, graph.corpus_id, 'Identical bytes in a different corpus must use a distinct storage identity');
    const foreign = {...record, corpus_id: otherCorpus, positions: record.positions.map(v => ({...v, x: 999999, y: 999999}))};
    await p.evaluate(({key, foreign}) => localStorage.setItem(key, JSON.stringify(foreign)), {key, foreign});
    await p.evaluate(() => history.replaceState(null, '', location.pathname));
    await p.reload(); await ready(p);
    assert(Object.values(await positions(p)).every(v => Math.abs(v.x) < 999999 && Math.abs(v.y) < 999999));
    assert.equal(await p.locator('#status-filter').inputValue(), 'all');
    await p.evaluate(key => localStorage.setItem(key, '{malformed-json'), key);
    await p.reload(); await ready(p);
    assert.equal((await p.evaluate(() => window.wikiViewer.getSnapshot().nodes)).length, 19);
    await expand(p, '#view-options'); await p.locator('#clear-layout').click();
    assert.equal(await p.evaluate(key => localStorage.getItem(key), key), null);
    return {reload_restores: true, coordinates_exact: true, bodies_stored: false, foreign_corpus_rejected: true, malformed_storage_ignored: true};
  }, p);

  await group('P2 JSON and PNG downloads require privacy confirmation and export only eligible data', async () => {
    await p.locator('#reset-view').click(); await expand(p, '#view-options'); await expand(p, '#data-tools');
    await p.locator('#group-mode').selectOption('tag'); await p.locator('#collapse-groups').click();
    await p.locator('#type-filters input[data-value="source"]').uncheck();
    const downloaded = [];
    p.on('download', value => downloaded.push(value));
    await p.locator('#export-json').click();
    assert(await p.locator('#export-confirm').isVisible());
    assert.match(await p.locator('#export-confirm').innerText(), /quyền chia sẻ/);
    await p.locator('#cancel-export').click(); await sleep(200);
    assert.equal(downloaded.length, 0);
    await p.locator('#export-json').click();
    const jsonPromise = p.waitForEvent('download'); await p.locator('#confirm-export').click();
    const jsonDownload = await jsonPromise, jsonFile = path.join(output, 'p2-visible-graph.json');
    await jsonDownload.saveAs(jsonFile);
    const text = fs.readFileSync(jsonFile, 'utf8'), exported = JSON.parse(text);
    assert.equal(exported.format, 'agent-knowledge-visible-graph/v1');
    const expectedNodes = graph.nodes.filter(n => n.kind !== 'source');
    const ids = new Set(expectedNodes.map(n => n.id));
    assert.deepEqual(exported.nodes.map(n => n.id).sort(), [...ids].sort());
    assert.deepEqual(exported.edges.map(e => e.id).sort(), graph.edges.filter(e => ids.has(e.source) && ids.has(e.target)).map(e => e.id).sort());
    assert(exported.edges.every(e => e.explicit === true && e.provenance.file));
    assert(!exported.nodes.some(n => n.id.startsWith('ui:')));
    assert(!exported.edges.some(e => e.id.startsWith('ui:')));
    assert(!text.includes('SYNTHETIC_EXCLUDED_FROM_DOWNLOAD'));
    assert(exported.display.nodes.some(n => n.derived === true || n.data?.derived === true));
    await p.locator('#export-png').click(); await p.locator('#cancel-export').click(); await sleep(200);
    assert.equal(downloaded.length, 1);
    await p.locator('#export-png').click();
    const pngPromise = p.waitForEvent('download'); await p.locator('#confirm-export').click();
    const pngDownload = await pngPromise, pngFile = path.join(output, 'p2-visible-graph.png');
    await pngDownload.saveAs(pngFile);
    const png = fs.readFileSync(pngFile);
    assert.deepEqual([...png.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
    assert(png.readUInt32BE(16) > 0 && png.readUInt32BE(20) > 0);
    return {cancel_downloads: 0, confirmed_downloads: 2, exported_nodes: exported.nodes.length, exported_edges: exported.edges.length, derived_geometry_separate: true, outside_scope_omitted: true, png_signature_dimensions_valid: true};
  }, p);

  await group('P2 opt-in refresh uses a real 15-second interval and preserves reader filters and dragged positions', async () => {
    const autoRoot = makeDemo('p2-auto', 1);
    const autoCase = await open(autoRoot, 'p2_auto_15s'); const q = autoCase.page;
    await expand(q, '#data-tools');
    assert.equal(await q.locator('#auto-refresh').isChecked(), false);
    const originalRequests = autoCase.requests.filter(value => value === '/api/graph').length;
    await sleep(650);
    assert.equal(autoCase.requests.filter(value => value === '/api/graph').length, originalRequests);
    await q.locator('#type-filters input[data-value="navigation"]').uncheck();
    await q.locator('#status-filter').selectOption('current');
    await dragNode(q, current);
    const beforePositions = await positions(q), beforeHash = new URL(q.url()).hash;
    const active = new Set(); let maximumConcurrent = 0;
    q.on('request', request => { if (new URL(request.url()).pathname === '/api/graph') { active.add(request); maximumConcurrent = Math.max(maximumConcurrent, active.size); } });
    q.on('requestfinished', request => active.delete(request)); q.on('requestfailed', request => active.delete(request));
    await q.locator('#refresh-interval').selectOption('15');
    const responsePromise = q.waitForResponse(response => new URL(response.url()).pathname === '/api/graph', {timeout: 24000});
    const started = performance.now(); await q.locator('#auto-refresh').check();
    mutateNote(autoRoot, current, (meta, body) => body + '\nSYNTHETIC timed refresh marker\n');
    const staleDownloads = []; q.on('download', download => staleDownloads.push(download));
    await q.locator('#export-json').click();
    assert(await q.locator('#export-confirm').isVisible());
    const response = await responsePromise; const elapsed = performance.now() - started;
    assert.equal(response.status(), 200); assert(elapsed >= 14000, 'Core refresh waits a real interval, without fake timers');
    await ready(q);
    assert.equal(await q.locator('#export-confirm').isVisible(), false, 'New snapshot invalidates the pending export confirmation');
    assert.equal(staleDownloads.length, 0);
    assert.equal(new URL(q.url()).hash, beforeHash);
    assert.equal(await q.locator('#detail-header .note-path').innerText(), current);
    assert.equal(await q.locator('#status-filter').inputValue(), 'current');
    assert.equal(await q.locator('#type-filters input[data-value="navigation"]').isChecked(), false);
    assert.deepEqual(await positions(q), beforePositions);
    assert((await q.locator('#panel-body').innerText()).includes('SYNTHETIC timed refresh marker'));
    // Native Chrome in this environment reports all test tabs visible, even when
    // backgrounded. This adapter tests the visibility-event branch, not native
    // operating-system tab detection; timers and network remain real.
    await q.evaluate(() => {
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
      Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const hiddenRequests = autoCase.requests.filter(value => value === '/api/graph').length;
    await sleep(16100);
    assert.equal(autoCase.requests.filter(value => value === '/api/graph').length, hiddenRequests);
    const sourcePath = path.join(autoRoot, source), bytes = fs.readFileSync(sourcePath);
    mutateNote(autoRoot, source, meta => { delete meta.version; });
    const errorResponse = q.waitForResponse(response => new URL(response.url()).pathname === '/api/graph', {timeout: 24000});
    await q.evaluate(() => { delete document.hidden; delete document.visibilityState; document.dispatchEvent(new Event('visibilitychange')); });
    assert.equal((await errorResponse).status(), 422);
    await q.waitForFunction(() => !document.getElementById('refresh').disabled && document.getElementById('graph-state').classList.contains('is-error'));
    assert.equal(await q.evaluate(() => window.wikiViewer.getSnapshot()), null);
    assert.equal(await q.locator('#auto-refresh').isChecked(), false, 'Automatic refresh stops after a rejected snapshot');
    fs.writeFileSync(sourcePath, bytes);
    await q.locator('#refresh').click(); await ready(q);
    assert.equal(maximumConcurrent, 1);
    report.metrics.p2_auto_15s.observed_first_refresh_ms = elapsed;
    return {opt_in_default: false, actual_interval_ms: elapsed, concurrent_requests_max: maximumConcurrent,
      reader_filters_positions_preserved: true, invalid_snapshot_cleared_and_recovered: true,
      stale_export_confirmation_cancelled: true,
      hidden_pause: '16.1 seconds with explicit document visibility adapter; native background-tab behavior not verified'};
  }, p);

  const gitRoot = makeDemo('p2-git', 1);
  git(gitRoot, 'init', '-q', '--initial-branch=contrib/synthetic-browser');
  const base = commit(gitRoot, 'Synthetic baseline');
  mutateNote(gitRoot, comparison, (meta, body) => { meta.claims[0].text += ' Synthetic comparison revision two.'; return body + '\nSynthetic revision two body.\n'; });
  fs.copyFileSync(path.join(gitRoot, 'wiki/lessons/topic-001.md'), path.join(gitRoot, 'wiki/lessons/added.md'));
  mutateNote(gitRoot, 'wiki/lessons/added.md', meta => { meta.id = 'p2-added'; meta.title = 'SYNTHETIC added lesson'; });
  fs.unlinkSync(path.join(gitRoot, 'wiki/lessons/topic-001.md'));
  mutateNote(gitRoot, comparison, () => {}); // Rebuild the actual index after removal.
  const target = commit(gitRoot, 'Synthetic changed added and removed notes');
  const originalSource = fs.readFileSync(path.join(gitRoot, source));
  mutateNote(gitRoot, source, meta => { meta.scope = 'project'; meta.title = 'SYNTHETIC_PRIVATE_OLD_REVISION'; });
  const privateRevision = commit(gitRoot, 'Synthetic private revision to deny');
  fs.writeFileSync(path.join(gitRoot, source), originalSource);
  commit(gitRoot, 'Restore valid synthetic working revision');
  const gitCase = await open(gitRoot, 'p2_real_git');
  const g = gitCase.page;
  await group('P2 compares real Git revisions and denies a private historical snapshot without changing checkout', async () => {
    await expand(g, '#data-tools');
    const beforeHead = git(gitRoot, 'rev-parse', 'HEAD');
    const beforeStatus = git(gitRoot, 'status', '--porcelain');
    await g.locator('#compare-base').fill(base); await g.locator('#compare-target').fill(target);
    const responsePromise = g.waitForResponse(response => new URL(response.url()).pathname === '/api/compare');
    await g.locator('#compare-run').click();
    const response = await responsePromise;
    assert.equal(response.status(), 200);
    const diff = await response.json();
    assert.equal(diff.base_revision, base); assert.equal(diff.target_revision, target);
    assert.equal(diff.nodes.added.some(node => node.id === 'wiki/lessons/added.md'), true);
    assert.equal(diff.nodes.removed.some(node => node.id === 'wiki/lessons/topic-001.md'), true);
    assert.equal(diff.nodes.changed.some(node => node.id === comparison), true);
    await g.waitForFunction(() => !document.getElementById('compare-run').disabled);
    await g.locator('#compare-results .diff-entry').evaluateAll(entries => entries.forEach(entry => { entry.open = true; }));
    const rendered = await g.locator('#compare-results').innerText();
    assert(rendered.includes('wiki/lessons/added.md')); assert(rendered.includes('wiki/lessons/topic-001.md'));
    await screenshot(g, 'p2-git-comparison.png');
    await g.locator('#compare-target').fill(privateRevision);
    const rejectedPromise = g.waitForResponse(response => new URL(response.url()).pathname === '/api/compare');
    await g.locator('#compare-run').click(); const rejected = await rejectedPromise;
    assert.equal(rejected.status(), 422);
    assert(!(await rejected.text()).includes('SYNTHETIC_PRIVATE_OLD_REVISION'));
    await g.waitForFunction(() => !document.getElementById('compare-run').disabled);
    assert(!(await g.locator('body').innerText()).includes('SYNTHETIC_PRIVATE_OLD_REVISION'));
    assert.equal(await g.locator('#compare-results').innerText(), '');
    assert.equal(git(gitRoot, 'rev-parse', 'HEAD'), beforeHead);
    assert.equal(git(gitRoot, 'status', '--porcelain'), beforeStatus);
    return {actual_git_commits: 4, base_target: 'full SHAs on selected HEAD ancestry', diff: diff.stats, private_revision_http: 422, checkout_unchanged: true};
  }, g);

  await group('P2 large graph uses an explicitly labeled deterministic grid with measured response', async () => {
    const q = phases.large.page;
    await q.locator('#reset-view').click();
    assert.match(await q.locator('#layout-label').innerText(), /grid|lưới/i);
    const started = performance.now(); await q.locator('#relayout').click();
    const first = await positions(q);
    await q.locator('#relayout').click();
    const second = await positions(q);
    const different = Object.keys(first).find(id => first[id].x !== second[id]?.x || first[id].y !== second[id]?.y);
    assert.equal(different, undefined, 'Repeated grid must keep coordinates: ' + JSON.stringify(different ? {id: different, first: first[different], second: second[different]} : {}));
    assert.equal(Object.keys(first).length, 1201);
    assert.equal(new Set(Object.values(first).map(v => v.x + ':' + v.y)).size, 1201);
    report.metrics.p1_large_1201_nodes.two_grid_relayouts_action_ms = performance.now() - started;
    await screenshot(q, 'p2-large-grid.png');
    return {nodes: 1201, edges: 5603, layout: 'deterministic grid', duplicate_positions: 0, metrics: report.metrics.p1_large_1201_nodes};
  }, phases.large.page);
};

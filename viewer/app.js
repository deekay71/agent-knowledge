'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const TYPES = {
    source: {label: 'Nguồn', color: '#5dd6be'},
    concept: {label: 'Khái niệm', color: '#ac94f5'},
    lesson: {label: 'Bài học', color: '#f4ad68'},
    page: {label: 'Trang', color: '#75aef3'},
    navigation: {label: 'Điều hướng', color: '#8896ac'},
  };
  const RELATIONS = {
    link: 'Liên kết trong nội dung', sources: 'Nguồn của trang', claim: 'Nguồn của claim',
    contradiction: 'Bằng chứng mâu thuẫn', supersedes: 'Thay thế trang trước',
    superseded_by: 'Được thay thế bởi', review_record: 'Biên bản review',
    verification_evidence: 'Bằng chứng kiểm chứng', navigation: 'Điều hướng',
  };
  const CLAIMS = {evidence: 'Bằng chứng', inference: 'Suy luận', unknown: 'Chưa rõ'};
  const UNTAGGED = '';
  let snapshot = null;
  let nodes = new Map();
  let edges = new Map();
  let cy = null;
  let selected = null;
  let selectedTab = 'body';
  let typeSelection = new Set(Object.keys(TYPES));
  let tagSelection = new Set();
  let relationSelection = new Set();
  let searchMatches = [];
  let activeResult = -1;
  let requestController = null;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const markdown = window.markdownit ? window.markdownit({html: false, linkify: false, typographer: false}) : null;
  if (markdown) {
    markdown.renderer.rules.image = (tokens, idx) => '<span class="image-placeholder">[Ảnh không tải: ' + markdown.utils.escapeHtml(tokens[idx].content || 'không có mô tả') + ']</span>';
  }

  function element(tag, className, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = String(value);
    return el;
  }
  function kindInfo(kind) { return Object.hasOwn(TYPES, kind) ? TYPES[kind] : TYPES.page; }
  function dot(kind) { const el = element('span', 'type-dot'); el.dataset.kind = Object.hasOwn(TYPES, kind) ? kind : 'page'; el.setAttribute('aria-hidden', 'true'); return el; }
  function normalize(text) { return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLocaleLowerCase('vi'); }
  function noteTags(node) { const tags = Array.isArray(node.tags) ? node.tags.filter((tag) => typeof tag === 'string' && tag !== '') : []; return tags.length ? tags : [UNTAGGED]; }
  function title(node) { return typeof node.title === 'string' && node.title ? node.title : node.id; }
  function nodeAllowed(node) { return typeSelection.has(node.kind) && noteTags(node).some((tag) => tagSelection.has(tag)); }
  function matchesSearch(node) { const query = normalize($('search').value.trim()); return !query || normalize(title(node)).includes(query) || normalize(node.id).includes(query); }
  function badge(text, className = '') { return element('span', 'badge ' + className, text); }
  function message(text) { return element('p', 'empty-note', text); }
  function reference(target, label) {
    const button = element('button', 'reference-button', label || (nodes.has(target) ? title(nodes.get(target)) : target));
    button.type = 'button';
    button.title = target;
    if (nodes.has(target)) button.addEventListener('click', () => selectNode(target, true));
    else { button.disabled = true; button.title = 'Không nằm trong snapshot đang đọc: ' + target; }
    return button;
  }
  function safeWebLink(value) {
    try {
      const url = new URL(value);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch (_) { return null; }
  }
  function remoteLink(href, label) {
    const anchor = element('a', 'external-link', label || href);
    anchor.href = href;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    anchor.referrerPolicy = 'no-referrer';
    anchor.title = 'Mở liên kết bên ngoài khi bạn chọn: ' + href;
    return anchor;
  }
  function resolveInternal(href, currentId) {
    if (!href || /[\u0000-\u001f\u007f]/.test(href) || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.includes('?')) return null;
    let path;
    try { path = decodeURIComponent(href.split('#')[0]); } catch (_) { return null; }
    if (!path) return currentId;
    if (path.startsWith('/') || path.includes('\\')) return null;
    const parts = currentId.split('/').slice(0, -1);
    for (const part of path.split('/')) {
      if (part === '..') { if (!parts.length) return null; parts.pop(); }
      else if (part && part !== '.') parts.push(part);
    }
    const target = parts.join('/');
    return nodes.has(target) ? target : null;
  }
  function renderMarkdown(body, currentId) {
    const container = element('div', 'markdown');
    if (!markdown || !window.DOMPurify) { container.textContent = body || ''; return container; }
    const fragment = window.DOMPurify.sanitize(markdown.render(typeof body === 'string' ? body : ''), {
      ALLOWED_TAGS: ['p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'em', 'strong', 's', 'del', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'span'],
      ALLOWED_ATTR: ['href', 'title', 'class'],
      ALLOW_DATA_ATTR: false,
      RETURN_DOM_FRAGMENT: true,
    });
    for (const anchor of fragment.querySelectorAll('a')) {
      const href = anchor.getAttribute('href') || '';
      const web = safeWebLink(href);
      if (web) {
        anchor.href = web; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
        anchor.referrerPolicy = 'no-referrer'; anchor.className = 'external-link';
        anchor.title = 'Mở liên kết bên ngoài khi bạn chọn: ' + web;
        continue;
      }
      const target = resolveInternal(href, currentId);
      if (target) {
        anchor.href = '#note=' + encodeURIComponent(target);
        anchor.title = target;
        anchor.addEventListener('click', (event) => { event.preventDefault(); selectNode(target, true); });
      } else {
        const disabled = element('span', 'blocked-link', anchor.textContent);
        disabled.title = 'Liên kết không thuộc snapshot hoặc không được hỗ trợ: ' + href;
        anchor.replaceWith(disabled);
      }
    }
    container.append(fragment);
    return container;
  }

  function setGraphState(mode, heading, description) {
    $('graph-state').hidden = mode === 'ready';
    $('graph-state').classList.toggle('is-error', mode === 'error');
    $('state-title').textContent = heading || '';
    $('state-description').textContent = description || '';
  }
  function formattedDate(value) {
    if (!value) return 'chưa có';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('vi-VN', {hour12: false});
  }
  function updateSnapshotLabels() {
    const info = snapshot.snapshot || {};
    const revision = typeof info.revision === 'string' ? info.revision.slice(0, 12) : 'chưa có commit';
    $('snapshot-label').textContent = 'HEAD ' + revision + ' · Index ' + formattedDate(info.index_updated_at);
    $('snapshot-label').title = 'HEAD: ' + (info.revision || 'chưa có') + ' (nội dung đang đọc có thể chưa commit)\nIndex: ' + formattedDate(info.index_updated_at) + '\nĐọc snapshot: ' + formattedDate(info.loaded_at);
    $('load-status').textContent = 'Đã tải · ' + formattedDate(info.loaded_at);
    $('load-status').title = 'Index cập nhật: ' + formattedDate(info.index_updated_at) + '\nDigest: ' + snapshot.source_digest;
  }

  function makeFilter(parentId, name, label, count, checked, onChange, kind) {
    const row = element('label', 'filter-label');
    const input = document.createElement('input');
    input.type = 'checkbox'; input.checked = checked; input.dataset.value = name;
    input.addEventListener('change', () => onChange(input.checked));
    row.append(input);
    if (kind) row.append(dot(kind));
    row.append(element('span', 'label-text', label), element('span', 'count', count));
    $(parentId).append(row);
  }
  function rebuildFilters(previousTags, previousRelations) {
    const tags = new Map(), relations = new Map();
    for (const node of nodes.values()) for (const tag of new Set(noteTags(node))) tags.set(tag, (tags.get(tag) || 0) + 1);
    for (const edge of edges.values()) relations.set(edge.kind, (relations.get(edge.kind) || 0) + 1);
    tagSelection = previousTags === null ? new Set(tags.keys()) : new Set([...previousTags].filter((tag) => tags.has(tag)));
    relationSelection = previousRelations === null ? new Set(relations.keys()) : new Set([...previousRelations].filter((kind) => relations.has(kind)));
    $('type-filters').replaceChildren(); $('tag-filters').replaceChildren(); $('relation-filters').replaceChildren();
    for (const [kind, info] of Object.entries(TYPES)) {
      const count = [...nodes.values()].filter((node) => node.kind === kind).length;
      makeFilter('type-filters', kind, info.label, count, typeSelection.has(kind), (checked) => { checked ? typeSelection.add(kind) : typeSelection.delete(kind); applyFilters(); }, kind);
    }
    for (const [tag, count] of [...tags].sort((a, b) => a[0].localeCompare(b[0], 'vi'))) {
      makeFilter('tag-filters', tag, tag || 'Không có tag', count, tagSelection.has(tag), (checked) => { checked ? tagSelection.add(tag) : tagSelection.delete(tag); applyFilters(); });
    }
    for (const [kind, count] of relations) {
      makeFilter('relation-filters', kind, RELATIONS[kind] || kind, count, relationSelection.has(kind), (checked) => { checked ? relationSelection.add(kind) : relationSelection.delete(kind); applyFilters(); });
    }
    $('tag-count').textContent = tags.size;
    $('relation-count').textContent = relations.size;
  }

  function initGraph() {
    cy = window.cytoscape({
      container: $('graph'), elements: [], minZoom: 0.12, maxZoom: 3.5,
      wheelSensitivity: 0.23, boxSelectionEnabled: false, autounselectify: true,
      style: [
        {selector: 'node', style: {'width': 29, 'height': 29, 'background-color': 'data(color)', 'border-color': '#d6dfef', 'border-width': 0, 'label': 'data(label)', 'color': '#bec9dc', 'font-family': 'system-ui, sans-serif', 'font-size': 11, 'min-zoomed-font-size': 8, 'font-weight': 400, 'text-valign': 'bottom', 'text-margin-y': 10, 'text-wrap': 'wrap', 'text-max-width': 150, 'text-outline-width': 2, 'text-outline-color': '#11151e', 'overlay-opacity': 0}},
        {selector: 'edge', style: {'width': 1.2, 'line-color': '#59647a', 'target-arrow-color': '#59647a', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.65, 'curve-style': 'bezier', 'control-point-step-size': 28, 'opacity': 0.65, 'overlay-opacity': 0, 'label': '', 'font-size': 9, 'color': '#c8c1d6', 'text-background-color': '#151a24', 'text-background-opacity': 1, 'text-background-padding': 3, 'text-rotation': 'autorotate', 'text-margin-y': -8}},
        {selector: 'edge[kind = "contradiction"]', style: {'line-color': '#ed7789', 'target-arrow-color': '#ed7789', 'line-style': 'dashed', 'width': 1.8}},
        {selector: 'edge[claim_kind = "inference"]', style: {'line-style': 'dotted', 'line-color': '#c3a879', 'target-arrow-color': '#c3a879'}},
        {selector: 'edge.hover', style: {'width': 2, 'opacity': 1, 'label': 'data(label)'}},
        {selector: '.dimmed', style: {'opacity': 0.13}},
        {selector: 'node.neighbor', style: {'border-width': 1.5, 'border-color': '#b6c5dc', 'opacity': 1}},
        {selector: 'node.active', style: {'width': 37, 'height': 37, 'border-width': 3, 'border-color': '#f1eaff', 'font-weight': 600, 'color': '#f1ebfc', 'opacity': 1}},
        {selector: 'edge.active', style: {'width': 2.2, 'opacity': 1, 'label': 'data(label)'}},
        {selector: 'node.search-hit', style: {'border-width': 2, 'border-color': '#eee4ff', 'opacity': 1}},
        {selector: '.filtered', style: {'display': 'none'}},
      ],
    });
    cy.on('tap', 'node', (event) => selectNode(event.target.id(), false));
    cy.on('tap', 'edge', (event) => selectEdge(event.target.id()));
    cy.on('tap', (event) => { if (event.target === cy) clearSelection(); });
    cy.on('mouseover', 'edge', (event) => event.target.addClass('hover'));
    cy.on('mouseout', 'edge', (event) => event.target.removeClass('hover'));
    cy.on('mouseover', 'node, edge', () => { $('graph').classList.add('is-hovering'); });
    cy.on('mouseout', 'node, edge', () => { $('graph').classList.remove('is-hovering'); });
    if (window.ResizeObserver) new ResizeObserver(() => cy.resize()).observe($('graph'));
    window.wikiViewer = Object.freeze({cy, getSnapshot: () => snapshot ? JSON.parse(JSON.stringify(snapshot)) : null});
  }
  function runLayout() {
    const visible = cy.elements().not('.filtered');
    if (!visible.nodes().length) return;
    visible.layout({name: 'cose', animate: false, randomize: true, fit: false, padding: 90,
      nodeDimensionsIncludeLabels: true,
      nodeRepulsion: () => 650000, idealEdgeLength: () => 180, edgeElasticity: () => 250,
      nodeOverlap: 24, gravity: 0.12, numIter: 700, componentSpacing: 180,
    }).run();
    fitGraph();
  }
  function fitGraph() {
    if (!cy) return;
    const visible = cy.elements().not('.filtered');
    if (!visible.nodes().length) return;
    cy.fit(visible, Math.min(105, $('graph').clientWidth * 0.16));
    if (cy.zoom() > 1.5) { cy.zoom(1.5); cy.center(visible); }
  }
  function zoom(multiplier) {
    if (!cy) return;
    const position = {x: $('graph').clientWidth / 2, y: $('graph').clientHeight / 2};
    cy.zoom({level: Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * multiplier)), renderedPosition: position});
  }
  function applyFilters() {
    if (!cy || !snapshot) return;
    cy.batch(() => {
      cy.nodes().forEach((el) => el.toggleClass('filtered', !nodeAllowed(nodes.get(el.id()))));
      cy.edges().forEach((el) => el.toggleClass('filtered', !relationSelection.has(el.data('kind')) || el.source().hasClass('filtered') || el.target().hasClass('filtered')));
    });
    if (selected && cy.getElementById(selected.id).hasClass('filtered')) clearSelection();
    const visibleNodes = cy.nodes().not('.filtered').length;
    const visibleEdges = cy.edges().not('.filtered').length;
    $('graph-stats').textContent = visibleNodes + ' / ' + nodes.size + ' ghi chú · ' + visibleEdges + ' / ' + edges.size + ' quan hệ';
    $('total-count').textContent = nodes.size + ' ghi chú';
    if (!visibleNodes) setGraphState('empty', 'Không có ghi chú trong bộ lọc', 'Chọn thêm loại nội dung hoặc tag, hoặc dùng Đặt lại.');
    else setGraphState('ready');
    renderSearch(); renderNoteList(); applyFocus();
  }
  function applyFocus() {
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass('dimmed active neighbor search-hit');
      if (selected) {
        const chosen = cy.getElementById(selected.id);
        const visibleEdges = chosen.connectedEdges().not('.filtered');
        const nearby = selected.type === 'node' ? chosen.union(visibleEdges).union(visibleEdges.connectedNodes()) : chosen.union(chosen.connectedNodes());
        cy.elements().not(nearby).addClass('dimmed');
        nearby.nodes().addClass('neighbor'); chosen.addClass('active');
      } else if ($('search').value.trim()) {
        cy.elements().addClass('dimmed');
        for (const node of searchMatches) cy.getElementById(node.id).removeClass('dimmed').addClass('search-hit');
      }
    });
  }
  function renderSearch() {
    const query = $('search').value.trim();
    searchMatches = [...nodes.values()].filter((node) => nodeAllowed(node) && matchesSearch(node)).sort((a, b) => title(a).localeCompare(title(b), 'vi'));
    activeResult = -1;
    $('search').removeAttribute('aria-activedescendant');
    $('clear-search').hidden = !query;
    $('search-results').replaceChildren();
    $('search-results').hidden = !query || searchMatches.length === 0;
    $('search').setAttribute('aria-expanded', String(Boolean(query && searchMatches.length)));
    $('search-hint').textContent = query ? searchMatches.length + ' kết quả trong bộ lọc · ↑ ↓ để chọn, Enter để đọc' : 'Tìm trong tiêu đề và đường dẫn ghi chú.';
    if (!query) return;
    searchMatches.forEach((node, index) => {
      const li = element('li'); li.id = 'search-result-' + index; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', 'false');
      const name = element('span', 'result-title'); name.append(dot(node.kind), document.createTextNode(title(node)));
      li.append(name, element('span', 'result-path', node.id));
      li.addEventListener('click', () => { activateResult(index); selectNode(node.id, true); });
      $('search-results').append(li);
    });
  }
  function activateResult(index) {
    if (!searchMatches.length) return;
    activeResult = Math.max(0, Math.min(index, searchMatches.length - 1));
    [...$('search-results').children].forEach((li, i) => li.setAttribute('aria-selected', String(i === activeResult)));
    const active = $('search-results').children[activeResult];
    $('search').setAttribute('aria-activedescendant', active.id); active.scrollIntoView({block: 'nearest'});
  }
  function renderNoteList() {
    $('note-list').replaceChildren();
    const visible = [...nodes.values()].filter(nodeAllowed);
    for (const node of visible.slice(0, 30)) {
      const button = element('button'); button.type = 'button'; button.title = node.id;
      button.append(dot(node.kind), element('span', '', title(node)));
      button.addEventListener('click', () => selectNode(node.id, true)); $('note-list').append(button);
    }
    if (visible.length > 30) $('note-list').append(message('Hiển thị 30 ghi chú đầu. Dùng tìm kiếm để mở ghi chú khác.'));
  }
  function clearSelection() {
    selected = null;
    $('detail-content').hidden = true; $('detail-empty').hidden = false; $('clear-selection').hidden = true;
    applyFocus();
  }
  function selectNode(id, center) {
    if (!nodes.has(id)) return;
    const node = nodes.get(id);
    // A reference may point to a filtered node. Reveal exactly its existing type/tag.
    if (!nodeAllowed(node)) {
      typeSelection.add(node.kind); for (const tag of noteTags(node)) tagSelection.add(tag);
      for (const input of $('type-filters').querySelectorAll('input')) input.checked = typeSelection.has(input.dataset.value);
      for (const input of $('tag-filters').querySelectorAll('input')) input.checked = tagSelection.has(input.dataset.value);
      applyFilters();
    }
    selected = {type: 'node', id}; selectedTab = 'body';
    renderNode(node); applyFocus();
    if (center && cy) {
      const target = cy.getElementById(id);
      const readableZoom = Math.max(cy.zoom(), 0.9);
      if (reducedMotion) { cy.zoom(readableZoom); cy.center(target); }
      else cy.animate({zoom: readableZoom, center: {eles: target}, duration: 220});
    }
  }
  function selectEdge(id) {
    if (!edges.has(id)) return;
    selected = {type: 'edge', id}; selectedTab = 'body'; renderEdge(edges.get(id)); applyFocus();
  }
  function prepareDetail() {
    $('detail-empty').hidden = true; $('detail-content').hidden = false; $('clear-selection').hidden = false;
    $('detail-header').replaceChildren(); $('detail-header').className = 'detail-header';
    for (const tab of ['body', 'links', 'metadata']) $('panel-' + tab).replaceChildren();
    setTab(selectedTab);
  }
  function setTab(tab) {
    selectedTab = tab;
    for (const name of ['body', 'links', 'metadata']) {
      $('tab-' + name).setAttribute('aria-selected', String(name === tab));
      $('tab-' + name).tabIndex = name === tab ? 0 : -1;
      $('panel-' + name).hidden = name !== tab;
    }
  }
  function appendMetadata(container, metadata) {
    for (const key of Object.keys(metadata || {}).sort()) {
      const field = element('div', 'metadata-field'); field.append(element('span', '', key));
      field.append(element('pre', 'metadata-code', typeof metadata[key] === 'string' ? metadata[key] : JSON.stringify(metadata[key], null, 2)));
      container.append(field);
    }
  }
  function addClaimSections(container, metadata) {
    if (Array.isArray(metadata.claims) && metadata.claims.length) {
      container.append(element('h3', '', 'Các claim đã ghi trong trang'));
      for (const claim of metadata.claims) {
        if (!claim || typeof claim !== 'object') continue;
        const card = element('div', 'claim-card');
        card.append(badge(Object.hasOwn(CLAIMS, claim.kind) ? CLAIMS[claim.kind] : String(claim.kind || 'Chưa rõ'), Object.hasOwn(CLAIMS, claim.kind) ? claim.kind : 'unknown'), element('p', '', claim.text || ''));
        if (Array.isArray(claim.applies_to)) card.append(element('p', 'claim-version', 'Áp dụng: ' + claim.applies_to.join(', ')));
        const refs = element('div', 'references');
        if (Array.isArray(claim.sources)) for (const source of claim.sources) if (typeof source === 'string') refs.append(reference(source));
        if (!refs.children.length) refs.append(message('Không có nguồn dẫn cho claim này.'));
        card.append(refs); container.append(card);
      }
    }
    if (Array.isArray(metadata.contradictions) && metadata.contradictions.length) {
      container.append(element('h3', '', 'Mâu thuẫn đã khai báo'));
      for (const conflict of metadata.contradictions) {
        if (!conflict || typeof conflict !== 'object') continue;
        const card = element('div', 'claim-card contradiction');
        card.append(badge(conflict.status === 'open' ? 'Còn mở' : conflict.status === 'resolved' ? 'Đã ghi cách giải quyết' : String(conflict.status), 'contradiction'), element('p', '', conflict.resolution || ''));
        const refs = element('div', 'references');
        if (Array.isArray(conflict.sources)) for (const source of conflict.sources) if (typeof source === 'string') refs.append(reference(source));
        card.append(refs); container.append(card);
      }
    }
  }
  function renderNode(node) {
    prepareDetail();
    const badges = element('div', 'badges'); badges.append(badge(kindInfo(node.kind).label, 'kind-' + node.kind));
    if (node.fixture) badges.append(badge('Fixture tổng hợp', 'fixture'));
    if (node.status) badges.append(badge(node.status));
    $('detail-header').append(badges, element('h2', '', title(node)), element('p', 'note-path', node.id));
    if (node.summary) $('detail-header').append(element('p', 'note-summary', node.summary));
    const metadata = node.metadata && typeof node.metadata === 'object' && !Array.isArray(node.metadata) ? node.metadata : {};
    if (node.fixture) $('panel-body').append(message('Dữ liệu thử nghiệm tổng hợp, không phải hướng dẫn production.'));
    if (metadata.origin) {
      const provenance = element('div', 'metadata-field'); provenance.append(element('span', '', 'Xuất xứ'), document.createElement('br'));
      const web = typeof metadata.origin === 'string' ? safeWebLink(metadata.origin) : null;
      provenance.append(web ? remoteLink(web, metadata.origin) : element('span', 'note-path', typeof metadata.origin === 'string' ? metadata.origin : JSON.stringify(metadata.origin)));
      $('panel-body').append(provenance);
    }
    $('panel-body').append(renderMarkdown(node.body || '', node.id));
    addClaimSections($('panel-body'), metadata);
    renderRelationships(node.id, $('panel-links'));
    const info = element('dl', 'meta-list');
    for (const [name, value] of [['Đường dẫn chuẩn', node.id], ['Phạm vi', node.scope || metadata.scope || 'không khai báo'], ['Phiên bản áp dụng', Array.isArray(node.applies_to) ? node.applies_to.join(', ') : 'không khai báo'], ['Tag', noteTags(node).filter(Boolean).join(', ') || 'không có'], ['Git HEAD (nội dung có thể chưa commit)', snapshot.snapshot?.revision || 'chưa có'], ['Index cập nhật', formattedDate(snapshot.snapshot?.index_updated_at)]]) {
      const group = element('div'); group.append(element('dt', '', name), element('dd', '', value)); info.append(group);
    }
    $('panel-metadata').append(info, element('h3', '', 'Metadata nguyên bản'));
    appendMetadata($('panel-metadata'), metadata);
  }
  function renderRelationships(id, container) {
    const outgoing = [...edges.values()].filter((edge) => edge.source === id);
    const incoming = [...edges.values()].filter((edge) => edge.target === id);
    container.append(message('Toàn bộ quan hệ tường minh trong snapshot, kể cả quan hệ đang ẩn bởi bộ lọc.'));
    for (const [heading, items, direction] of [['Đi ra', outgoing, 'target'], ['Đi vào / backlinks', incoming, 'source']]) {
      container.append(element('h3', '', heading + ' · ' + items.length));
      const list = element('ul', 'relation-list');
      for (const edge of items) {
        const row = element('li'); row.append(element('span', 'relation-label', RELATIONS[edge.kind] || edge.kind));
        const target = nodes.get(edge[direction]); row.append(reference(edge[direction], target ? title(target) : edge[direction]));
        const inspect = element('button', 'text-button', 'Xem quan hệ →'); inspect.type = 'button'; inspect.addEventListener('click', () => selectEdge(edge.id));
        row.append(inspect); list.append(row);
      }
      container.append(items.length ? list : message('Không có quan hệ theo chiều này.'));
    }
  }
  function renderEdge(edge) {
    prepareDetail();
    const badges = element('div', 'badges'); badges.append(badge('Quan hệ tường minh'));
    if (edge.kind === 'contradiction') badges.append(badge('Mâu thuẫn', 'contradiction'));
    $('detail-header').append(badges, element('h2', '', RELATIONS[edge.kind] || edge.kind), element('p', 'note-summary', 'Quan hệ được khai báo trong dữ liệu; không được suy ra từ vị trí hoặc màu trên đồ thị.'));
    const endpoints = element('div', 'edge-endpoints'); endpoints.append(reference(edge.source), element('span', '', '↓ ' + (RELATIONS[edge.kind] || edge.kind)), reference(edge.target));
    $('panel-body').append(endpoints);
    if (edge.claim_kind) $('panel-body').append(element('p', 'edge-description', 'Loại claim: ' + (CLAIMS[edge.claim_kind] || edge.claim_kind) + '. Đây là nhãn của claim, không phải mức tin cậy của cạnh.'));
    if (edge.status) $('panel-body').append(element('p', 'edge-description', 'Trạng thái khai báo: ' + edge.status));
    const provenance = edge.provenance;
    $('panel-body').append(element('h3', '', 'Vị trí khai báo'));
    if (provenance && typeof provenance === 'object') {
      if (typeof provenance.file === 'string') $('panel-body').append(reference(provenance.file, provenance.file));
      if (provenance.section) $('panel-body').append(element('p', 'note-summary', 'Phần: ' + provenance.section));
    } else $('panel-body').append(message('Snapshot không cung cấp vị trí khai báo chi tiết.'));
    $('panel-links').append(element('h3', '', 'Hai đầu quan hệ'), reference(edge.source), document.createElement('br'), reference(edge.target));
    appendMetadata($('panel-metadata'), edge);
  }

  function validateSnapshot(data) {
    if (!data || data.format !== 1 || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) throw new Error('Snapshot không đúng định dạng đồ thị được hỗ trợ.');
    const ids = new Set();
    for (const node of data.nodes) {
      if (!node || typeof node.id !== 'string' || !node.id || ids.has(node.id) || !Object.hasOwn(TYPES, node.kind)) throw new Error('Snapshot có ghi chú thiếu ID, trùng ID hoặc loại không hợp lệ.');
      ids.add(node.id);
    }
    const nodeIds = new Set(ids);
    for (const edge of data.edges) {
      if (!edge || typeof edge.id !== 'string' || !edge.id || ids.has(edge.id) || !nodeIds.has(edge.source) || !nodeIds.has(edge.target) || edge.explicit !== true || typeof edge.kind !== 'string') throw new Error('Snapshot có quan hệ không hợp lệ hoặc chưa được khai báo tường minh.');
      ids.add(edge.id);
    }
    return data;
  }
  async function refresh() {
    if (!cy) return;
    if (requestController) requestController.abort();
    requestController = new AbortController();
    const controller = requestController;
    const timer = window.setTimeout(() => controller.abort(), 20000);
    const previousSelection = selected;
    const allTagsSelected = [...nodes.values()].every((node) => noteTags(node).every((tag) => tagSelection.has(tag)));
    const allRelationsSelected = [...edges.values()].every((edge) => relationSelection.has(edge.kind));
    const previousTags = snapshot && !allTagsSelected ? new Set(tagSelection) : null;
    const previousRelations = snapshot && !allRelationsSelected ? new Set(relationSelection) : null;
    $('refresh').disabled = true; $('load-status').textContent = 'Đang tải lại…';
    setGraphState('loading', 'Đang đọc wiki…', 'Nạp snapshot mới; không sửa các file tri thức.');
    try {
      const response = await fetch('/api/graph', {signal: controller.signal, cache: 'no-store', credentials: 'omit', headers: {'Accept': 'application/json'}});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : typeof data.error?.message === 'string' ? data.error.message : 'Máy chủ từ chối snapshot (HTTP ' + response.status + ').');
      snapshot = validateSnapshot(data);
      nodes = new Map(snapshot.nodes.map((node) => [node.id, node]));
      edges = new Map(snapshot.edges.map((edge) => [edge.id, edge]));
      selected = null;
      cy.elements().remove();
      cy.add(snapshot.nodes.map((node) => ({group: 'nodes', data: {id: node.id, label: title(node), kind: node.kind, color: kindInfo(node.kind).color}})));
      cy.add(snapshot.edges.map((edge) => ({group: 'edges', data: {...edge, label: RELATIONS[edge.kind] || edge.kind}})));
      rebuildFilters(previousTags, previousRelations);
      $('warnings').replaceChildren();
      const warnings = Array.isArray(snapshot.warnings) ? snapshot.warnings : [];
      $('warnings').hidden = !warnings.length;
      if (warnings.length) { $('warnings').append(element('strong', '', 'Lưu ý từ kiểm tra nguồn')); const list = element('ul'); for (const warning of warnings) list.append(element('li', '', typeof warning === 'string' ? warning : JSON.stringify(warning))); $('warnings').append(list); }
      const fixtureCount = [...nodes.values()].filter((node) => node.fixture).length;
      $('fixture-notice').hidden = fixtureCount === 0;
      $('fixture-text').textContent = fixtureCount + ' / ' + nodes.size + ' ghi chú là fixture tổng hợp. Đồ thị phản ánh đúng dữ liệu hiện có, không bổ sung nút minh họa.';
      updateSnapshotLabels(); clearSelection(); applyFilters(); runLayout();
      if (!nodes.size) setGraphState('empty', 'Wiki chưa có ghi chú', 'Chỉ ghi chú và liên kết thực trong snapshot mới xuất hiện ở đây.');
      if (previousSelection?.type === 'node' && nodes.has(previousSelection.id) && nodeAllowed(nodes.get(previousSelection.id))) selectNode(previousSelection.id, false);
      else if (previousSelection?.type === 'edge' && edges.has(previousSelection.id) && !cy.getElementById(previousSelection.id).hasClass('filtered')) selectEdge(previousSelection.id);
    } catch (error) {
      snapshot = null; nodes.clear(); edges.clear(); cy.elements().remove(); clearSelection(); renderSearch(); renderNoteList();
      for (const id of ['detail-header', 'panel-body', 'panel-links', 'panel-metadata']) $(id).replaceChildren();
      for (const id of ['type-filters', 'tag-filters', 'relation-filters', 'warnings']) $(id).replaceChildren();
      typeSelection = new Set(Object.keys(TYPES)); tagSelection = new Set(); relationSelection = new Set();
      $('tag-count').textContent = '0'; $('relation-count').textContent = '0'; $('fixture-text').textContent = '';
      $('load-status').removeAttribute('title'); $('snapshot-label').removeAttribute('title');
      $('graph-stats').textContent = 'Chưa có snapshot hợp lệ'; $('total-count').textContent = '—';
      $('fixture-notice').hidden = true; $('warnings').hidden = true; $('load-status').textContent = 'Không tải được dữ liệu'; $('snapshot-label').textContent = 'Không hiển thị dữ liệu cũ';
      setGraphState('error', 'Không thể đọc đồ thị', error.name === 'AbortError' ? 'Đã hết thời gian chờ. Kiểm tra máy chủ local rồi chọn Tải lại dữ liệu.' : error.message);
    } finally { window.clearTimeout(timer); $('refresh').disabled = false; if (requestController === controller) requestController = null; }
  }

  $('search').addEventListener('input', () => { renderSearch(); applyFocus(); });
  $('search').addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { if (!searchMatches.length || !$('search').value.trim()) return; event.preventDefault(); activateResult(activeResult < 0 ? 0 : activeResult + (event.key === 'ArrowDown' ? 1 : -1)); }
    else if (event.key === 'Enter' && searchMatches.length && $('search').value.trim()) { event.preventDefault(); activateResult(activeResult < 0 ? 0 : activeResult); selectNode(searchMatches[activeResult].id, true); }
    else if (event.key === 'Escape') { $('search').value = ''; renderSearch(); applyFocus(); }
  });
  $('clear-search').addEventListener('click', () => { $('search').value = ''; renderSearch(); applyFocus(); $('search').focus(); });
  function selectAll(group, selection) { for (const input of $(group).querySelectorAll('input')) { input.checked = true; selection.add(input.dataset.value); } applyFilters(); }
  $('select-all-types').addEventListener('click', () => selectAll('type-filters', typeSelection));
  $('select-all-tags').addEventListener('click', () => selectAll('tag-filters', tagSelection));
  $('select-all-relations').addEventListener('click', () => selectAll('relation-filters', relationSelection));
  $('clear-selection').addEventListener('click', clearSelection);
  $('refresh').addEventListener('click', refresh); $('fit').addEventListener('click', fitGraph); $('relayout').addEventListener('click', runLayout);
  $('zoom-in').addEventListener('click', () => zoom(1.3)); $('zoom-out').addEventListener('click', () => zoom(1 / 1.3));
  $('reset-view').addEventListener('click', () => { $('search').value = ''; selectAll('type-filters', typeSelection); selectAll('tag-filters', tagSelection); selectAll('relation-filters', relationSelection); clearSelection(); fitGraph(); });
  const tabs = ['body', 'links', 'metadata'];
  tabs.forEach((tab, index) => {
    $('tab-' + tab).addEventListener('click', () => setTab(tab));
    $('tab-' + tab).addEventListener('keydown', (event) => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); setTab(tabs[next]); $('tab-' + tabs[next]).focus(); }
    });
  });
  if (!window.cytoscape || !markdown || !window.DOMPurify) {
    setGraphState('error', 'Thiếu thư viện giao diện local', 'Kiểm tra các file vendor trong repo rồi tải lại trang. Không có tài nguyên bên ngoài được tự tải.');
    $('load-status').textContent = 'Thiếu thư viện local'; $('refresh').disabled = true;
  } else { initGraph(); refresh(); }
})();

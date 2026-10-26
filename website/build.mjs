import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { marked } from 'marked';
import hljs from 'highlight.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const out = path.join(here, 'dist');
const config = JSON.parse(fs.readFileSync(path.join(here, 'config.json'), 'utf8'));
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const plain = value => String(value).replace(/<[^>]*>/g, '').replace(/[`*_]/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/&amp;/g, '&');
const slug = value => plain(value).toLowerCase().replace(/[^\w\- ]/g, '').replace(/\s/g, '-');
const relative = file => path.relative(root, file).split(path.sep).join('/');
const read = file => fs.readFileSync(file, 'utf8');
const write = (route, html) => { const file = path.join(out, route, 'index.html'); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, html); };

hljs.registerLanguage('clack', () => ({
  name: 'Clack',
  keywords: {
    keyword: 'fn type from import return if elif else while parallel requires ensures invariant decreases assert and or not',
    built_in: 'print len',
    literal: 'true false',
    type: 'int bool unit',
  },
  contains: [hljs.HASH_COMMENT_MODE, hljs.NUMBER_MODE, { scope: 'title.function', begin: /\b[a-zA-Z_]\w*(?=\()/ }],
}));

function highlight(source, language = 'clack') {
  const name = language.split(/\s/)[0];
  return hljs.getLanguage(name) ? hljs.highlight(source, { language: name, ignoreIllegals: true }).value : escape(source);
}
function codeBlock(source, language = 'clack', extraClass = '') {
  const label = ({ sh: 'Terminal', bash: 'Terminal', clack: 'Clack', text: 'Output', json: 'JSON', python: 'Python' })[language] || language || 'Code';
  return `<div class="code-block ${extraClass}"><div class="code-heading"><span>${escape(label)}</span><button class="copy-button" type="button" data-copy aria-label="Copy code">Copy</button></div><pre><code class="language-${escape(language)}">${highlight(source, language)}</code></pre></div>`;
}
function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? walk(path.join(directory, entry.name)) : entry.name.endsWith('.md') ? [path.join(directory, entry.name)] : []);
}
function routeFor(file) {
  const rel = relative(file).replace(/README\.md$/, '').replace(/\.md$/, '');
  return '/' + rel.replace(/\/$/, '') + '/';
}
const files = [...walk(path.join(root, 'docs')), path.join(root, 'benchmarks/README.md')];
const pages = files.map(file => ({ file, source: read(file), url: routeFor(file), title: (read(file).match(/^#\s+(.+)$/m) || [null, path.basename(file, '.md')])[1] }));
const byFile = new Map(pages.map(page => [path.resolve(page.file), page]));
const pageFor = rel => byFile.get(path.join(root, rel));
const navigation = [
  ['Start here', [['docs/README.md', 'Handbook'], ['docs/getting-started.md', 'Getting started'], ['docs/quick-reference.md', 'Quick reference']]],
  ['Learn Clack', [['docs/tutorials/README.md', 'Tutorial overview'], ...[
    ['01-first-program', '1. Your first program'], ['02-functions-contracts', '2. Functions & contracts'], ['03-records-arrays', '3. Records & arrays'], ['04-loops', '4. Loops'], ['05-parallel-work', '5. Parallel work'], ['06-fixing-errors', '6. Fixing errors'], ['07-project', '7. Inventory project'], ['08-libraries', '8. Libraries'],
  ].map(([file, label]) => [`docs/tutorials/${file}.md`, label])]],
  ['Reference', [['docs/reference/README.md', 'Language reference'], ['docs/reference/lexical-syntax.md', 'Syntax & operators'], ['docs/reference/types-values.md', 'Types & values'], ['docs/reference/functions-control-flow.md', 'Functions & control flow'], ['docs/reference/contracts-verification.md', 'Contracts & verification'], ['docs/reference/parallelism.md', 'Parallelism'], ['docs/reference/grammar.md', 'Grammar'], ['docs/libraries.md', 'Standard library']]],
  ['Go further', [['docs/cookbook.md', 'Cookbook'], ['docs/cli.md', 'Command line'], ['docs/errors.md', 'Common errors'], ['docs/faq.md', 'FAQ'], ['docs/verification.md', 'Verification model'], ['docs/internals.md', 'Compiler internals'], ['docs/contributing.md', 'Contributing'], ['benchmarks/README.md', 'Performance'], ['docs/design.md', 'Design direction']]],
];
const ordered = navigation.flatMap(([, entries]) => entries).map(([file]) => pageFor(file)).filter(Boolean);

function docNavigation(current) {
  return navigation.map(([title, entries]) => `<section class="nav-group"><h2>${escape(title)}</h2>${entries.map(([file, label]) => {
    const page = pageFor(file); return page ? `<a href="${page.url}"${page.url === current ? ' class="is-active" aria-current="page"' : ''}>${escape(label)}</a>` : '';
  }).join('')}</section>`).join('');
}
function rewriteLink(href, file) {
  if (!href || href.startsWith('#') || /^(?:https?:|mailto:|tel:|\/)/.test(href)) return href;
  const [pathname, hash] = href.split('#');
  const destination = path.resolve(path.dirname(file), decodeURIComponent(pathname));
  const known = byFile.get(destination);
  if (known) return known.url + (hash ? '#' + hash : '');
  if (fs.existsSync(destination) && fs.statSync(destination).isDirectory()) {
    const index = byFile.get(path.join(destination, 'README.md'));
    if (index) return index.url + (hash ? '#' + hash : '');
  }
  const repoPath = relative(destination);
  const kind = fs.existsSync(destination) && fs.statSync(destination).isDirectory() ? 'tree' : 'blob';
  return `${config.githubUrl}/${kind}/${config.branch}/${repoPath}` + (hash ? '#' + hash : '');
}
function renderMarkdown(page) {
  const headings = [];
  const counts = new Map();
  const renderer = new marked.Renderer();
  renderer.heading = function(token) {
    const text = this.parser.parseInline(token.tokens);
    const base = slug(token.text);
    const occurrence = counts.get(base) || 0;
    counts.set(base, occurrence + 1);
    const id = base + (occurrence ? `-${occurrence}` : '');
    if (token.depth > 1 && token.depth < 4) headings.push({ id, title: plain(token.text), depth: token.depth });
    return `<h${token.depth} id="${escape(id)}">${text}${token.depth > 1 ? `<a class="heading-anchor" href="#${escape(id)}" aria-label="Link to ${escape(plain(token.text))}">#</a>` : ''}</h${token.depth}>\n`;
  };
  renderer.code = token => codeBlock(token.text, (token.lang || 'text').split(/\s/)[0]);
  renderer.link = function(token) {
    const href = rewriteLink(token.href, page.file);
    const title = token.title ? ` title="${escape(token.title)}"` : '';
    return `<a href="${escape(href)}"${title}>${this.parser.parseInline(token.tokens)}</a>`;
  };
  renderer.table = function(token) {
    const header = token.header.map(cell => `<th>${this.parser.parseInline(cell.tokens)}</th>`).join('');
    const body = token.rows.map(row => `<tr>${row.map(cell => `<td>${this.parser.parseInline(cell.tokens)}</td>`).join('')}</tr>`).join('');
    return `<div class="table-scroll" tabindex="0" aria-label="Scrollable table"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
  };
  return { html: marked.parse(page.source, { renderer, gfm: true }), headings };
}

const githubIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .8a11.2 11.2 0 0 0-3.54 21.82c.56.1.76-.24.76-.54v-2.1c-3.12.68-3.78-1.32-3.78-1.32-.51-1.3-1.25-1.64-1.25-1.64-1.02-.7.08-.68.08-.68 1.13.08 1.73 1.16 1.73 1.16 1 1.72 2.62 1.22 3.26.93.1-.73.4-1.22.71-1.5-2.49-.29-5.11-1.25-5.11-5.54 0-1.22.43-2.22 1.15-3-.12-.28-.5-1.42.11-2.96 0 0 .94-.3 3.08 1.15A10.7 10.7 0 0 1 12 6.2c.95 0 1.9.13 2.79.38 2.14-1.45 3.07-1.15 3.07-1.15.62 1.54.24 2.68.12 2.96.72.78 1.15 1.78 1.15 3.01 0 4.3-2.63 5.25-5.13 5.53.4.35.76 1.03.76 2.08v3.07c0 .3.2.65.77.54A11.2 11.2 0 0 0 12 .8Z"/></svg>';
const mark = '<svg class="brand-mark" viewBox="0 0 28 28" aria-hidden="true"><path d="M11 5H5v18h6m6-18h6v18h-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><circle cx="14" cy="14" r="1.8" fill="currentColor"/></svg>';
function header(isDocs = false, current = '') {
  return `<header class="site-header"><div class="header-inner"><a class="brand" href="/" aria-label="Clack home">${mark}<span>clack</span></a><div class="header-divider"></div><span class="version">v${escape(config.version)}</span><nav class="desktop-header-nav" aria-label="Main"><a href="/docs/getting-started/"${isDocs ? ' aria-current="page"' : ''}>Documentation</a><a href="/docs/tutorials/">Learn</a><a href="${escape(config.githubUrl)}" class="github-link">${githubIcon}<span>GitHub</span></a></nav><div class="header-actions"><button class="search-trigger" type="button" data-search-open><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.2"/><path d="m12.5 12.5 4 4"/></svg><span>Search docs</span><kbd>⌘ K</kbd></button><button class="menu-toggle" data-menu-toggle aria-controls="mobile-navigation" aria-expanded="false" aria-label="Open navigation"><span></span><span></span></button></div></div></header><nav id="mobile-navigation" class="mobile-navigation" aria-label="Mobile navigation" hidden><a href="/docs/getting-started/">Get started</a><a href="${escape(config.githubUrl)}">GitHub ↗</a>${isDocs ? docNavigation(current) : '<a href="/docs/tutorials/">Tutorials</a><a href="/docs/reference/">Language reference</a><a href="/docs/libraries/">Standard library</a>'}</nav>`;
}
function searchDialog() {
  return `<dialog id="search-dialog" class="search-dialog" aria-label="Search Clack documentation"><div class="search-input-row"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.2"/><path d="m12.5 12.5 4 4"/></svg><input id="search-input" type="search" placeholder="Search the handbook…" aria-label="Search the handbook" autocomplete="off"><button type="button" data-search-close aria-label="Close search">Esc</button></div><div id="search-results" aria-live="polite"><p class="search-empty">Search the handbook</p></div><div class="search-footer">Documentation, tutorials, and language reference.</div></dialog>`;
}
function footer() {
  return `<footer class="site-footer"><a class="brand" href="/">${mark}<span>clack</span></a><p>A small language. An open beginning.</p><div><a href="/docs/">Handbook</a><a href="${escape(config.githubUrl)}">GitHub ↗</a><a href="${escape(config.githubUrl)}/blob/${escape(config.branch)}/LICENSE">MIT license</a></div></footer>`;
}
function shell({ title, description, url = '/', body, docs = false }) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escape(title)}${title === 'Clack' ? ' — Small syntax. Serious possibilities.' : ' — Clack'}</title><meta name="description" content="${escape(description)}"><meta name="theme-color" content="#fafaf8"><link rel="canonical" href="${escape(new URL(url, config.siteUrl).href)}"><meta property="og:type" content="website"><meta property="og:title" content="${escape(title)}"><meta property="og:description" content="${escape(description)}"><meta property="og:url" content="${escape(new URL(url, config.siteUrl).href)}"><meta name="twitter:card" content="summary"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/styles.css"><script type="module" src="/site.js"></script></head><body${docs ? ' class="docs-body"' : ''}><a class="skip-link" href="#main">Skip to content</a>${header(docs, url)}${body}${searchDialog()}</body></html>`;
}

const examples = [
  { id: 'parallel', label: 'Parallel work', file: 'parallel.clack', source: `from std.array import sum4\n\nfn main():\n    parallel:\n        left = sum4([10, 20, 30, 40])\n        right = sum4([1, 2, 3, 4])\n    print(left + right)`, output: '110', note: 'Independent calls. Native threads. One block.' },
  { id: 'contracts', label: 'Checked promises', file: 'contracts.clack', source: `fn double(x: int) -> int:\n    requires 0 <= x <= 1000000\n    ensures result == x * 2\n    return x + x\n\nfn main():\n    print(double(21))`, output: '42', note: 'State a promise. Check every return before running.' },
  { id: 'data', label: 'Simple data', file: 'data.clack', source: `type Point:\n    x: int\n    y: int\n\nfn main():\n    point = Point(3, 4)\n    values = [10, 20, 30]\n    values[0] = point.x\n    print(values[0])`, output: '3', note: 'Named fields, inferred locals, predictable values.' },
];

function home() {
  const install = `git clone ${config.githubUrl}.git\ncd clack\npython3 -m venv .venv\n.venv/bin/pip install -e .\n.venv/bin/python -m clack run examples/hello.clack`;
  const sourceDownload = `${config.githubUrl}/archive/refs/heads/${config.branch}.zip`;
  return shell({ title: 'Clack', description: 'A small native language with plain syntax, checked contracts, and easy parallel work. Explore Clack and learn from its complete handbook.', body: `<main id="main"><section class="hero page-width"><div class="hero-copy"><a href="/docs/design/" class="status-pill"><span class="status-dot"></span>v${escape(config.version)} <span class="pill-separator">/</span> A working prototype <span aria-hidden="true">↗</span></a><h1>Small syntax.<br><span>Serious possibilities.</span></h1><p class="hero-description">A native language for clear code,<br class="desktop-break"> checked promises, and parallel work.</p><div class="hero-actions"><a class="button button-primary" href="/docs/getting-started/">Start with Clack <span aria-hidden="true">↗</span></a><a class="button button-secondary" href="${escape(config.githubUrl)}">${githubIcon} Explore the source</a></div><p class="hero-footnote">Open source. MIT licensed. Built from first principles.</p></div><div class="example-window"><div class="example-tabs" role="tablist" aria-label="Explore Clack examples">${examples.map((example, index) => `<button role="tab" id="tab-${example.id}" type="button" data-code-tab="${example.id}" aria-controls="example-${example.id}" aria-selected="${index === 0}" tabindex="${index === 0 ? 0 : -1}">${example.label}</button>`).join('')}</div>${examples.map((example, index) => `<div id="example-${example.id}" role="tabpanel" aria-labelledby="tab-${example.id}" data-code-panel="${example.id}"${index ? ' hidden' : ''}><div class="example-filename"><span class="file-dot"></span>${example.file}<span class="example-language">Clack</span></div>${codeBlock(example.source, 'clack', 'hero-code')}<div class="example-output"><span class="output-label"><span class="check-circle">✓</span> Output</span><code>${example.output}</code><span class="native-label">native executable</span></div><p class="example-caption">${example.note}</p></div>`).join('')}</div></section><section class="principles page-width" aria-label="Clack at a glance"><div><span class="principle-number">01</span><h2>Keep the language small.</h2><p>Functions, records, arrays, and inferred locals. Familiar ideas with room to build.</p></div><div><span class="principle-number">02</span><h2>Check before you run.</h2><p>Contracts, bounds, overflow, and loop termination are checked at compile time.</p></div><div><span class="principle-number">03</span><h2>Make work independent.</h2><p>Put calls in a <code>parallel:</code> block. Give each job its own values and collect the results.</p></div></section><section class="journey-section"><div class="page-width journey-grid"><div><p class="eyebrow">A SHORT PATH TO NATIVE CODE</p><h2>Write it plainly.<br>Make the promise precise.</h2><p class="section-intro">Clack keeps the everyday code familiar and puts its reasoning in the compiler.</p><a class="text-link" href="/docs/verification/">Understand the verification model <span aria-hidden="true">↗</span></a></div><div class="journey-steps"><div><span>1</span><section><h3>Write a small, typed program.</h3><p>Local types are inferred. Function boundaries make inputs and outputs clear.</p></section></div><div><span>2</span><section><h3>Check what it promises.</h3><p>The verifier checks every loaded function. An unproved claim stops the build.</p></section></div><div><span>3</span><section><h3>Run a native executable.</h3><p>Optimized C11 output becomes machine code. No Python interpreter or solver runs with your program.</p></section></div></div></div></section><section class="get-started page-width"><div><p class="eyebrow">YOUR FIRST PROGRAM IS CLOSE</p><h2>Start small.<br>Build your understanding.</h2><p>Install the compiler, run an example, and follow eight hands-on lessons through data, proofs, parallelism, and libraries.</p><div class="get-started-links"><a class="text-link" href="/docs/tutorials/">Read the tutorials ↗</a><a class="quiet-link" href="${escape(sourceDownload)}">Download the source ↓</a></div></div>${codeBlock(install, 'sh', 'install-code')}</section><aside class="prototype-note page-width"><span class="status-dot"></span><p><strong>An open beginning, with clear limits.</strong> Clack currently supports fixed arrays and value records. Strings, dynamic collections, and generics are still ahead. Verification trusts the compiler and Z3.</p><a href="/docs/faq/">Where things stand ↗</a></aside></main>${footer()}` });
}

function documentation(page) {
  const rendered = renderMarkdown(page);
  const index = ordered.indexOf(page);
  const previous = ordered[index - 1];
  const next = ordered[index + 1];
  const toc = rendered.headings.length ? `<aside class="toc" aria-label="On this page"><p>On this page</p>${rendered.headings.map(heading => `<a href="#${escape(heading.id)}"${heading.depth === 3 ? ' class="toc-nested"' : ''}>${escape(heading.title)}</a>`).join('')}</aside>` : '';
  const pager = `<nav class="doc-pager" aria-label="Previous and next page">${previous ? `<a href="${previous.url}"><span>← Previous</span><strong>${escape(previous.title)}</strong></a>` : '<span></span>'}${next ? `<a href="${next.url}" class="pager-next"><span>Next →</span><strong>${escape(next.title)}</strong></a>` : ''}</nav>`;
  return shell({ title: plain(page.title), description: `Clack handbook: ${plain(page.title)}. Learn the implemented language with precise explanations and working examples.`, url: page.url, docs: true, body: `<div class="docs-layout"><aside class="docs-sidebar" aria-label="Documentation navigation">${docNavigation(page.url)}<a class="sidebar-source" href="${escape(config.githubUrl)}">${githubIcon} Contribute on GitHub ↗</a></aside><main id="main" class="doc-main"><div class="doc-breadcrumb"><a href="/docs/">Handbook</a><span>/</span><span>${escape(plain(page.title))}</span></div><article class="prose">${rendered.html}</article>${pager}<div class="doc-bottom"><a href="${escape(config.githubUrl)}/blob/${escape(config.branch)}/${relative(page.file)}">View this page on GitHub ↗</a><span>Clack ${escape(config.version)}</span></div></main>${toc}</div>` });
}

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
fs.cpSync(path.join(here, 'public'), out, { recursive: true });
write('', home());
const search = [];
for (const page of pages) {
  write(page.url, documentation(page));
  const cleanText = source => plain(source.replace(/<!--.*?-->/gs, '').replace(/^```[^\n]*$/gm, '')).replace(/\s+/g, ' ').trim();
  const text = cleanText(page.source);
  search.push({ title: plain(page.title), url: page.url, text });
  const rendered = renderMarkdown(page);
  const sections = page.source.split(/^#{2,3}\s+/m).slice(1);
  for (const [index, heading] of rendered.headings.entries()) search.push({ title: heading.title, section: plain(page.title), url: page.url + '#' + heading.id, text: cleanText(sections[index] || heading.title) });
}
const notFound = shell({ title: 'Page not found', description: 'Find your way back to the Clack handbook.', url: '/404.html', body: `<main id="main" class="not-found page-width"><p class="eyebrow">404 / PAGE NOT FOUND</p><h1>A small detour.</h1><p>That page is not here. The handbook is a good place to start.</p><a class="button button-primary" href="/docs/">Open the handbook ↗</a></main>${footer()}` });
fs.writeFileSync(path.join(out, '404.html'), notFound);
fs.writeFileSync(path.join(out, 'search-index.json'), JSON.stringify(search));
fs.writeFileSync(path.join(out, 'robots.txt'), `User-agent: *\nAllow: /\nSitemap: ${config.siteUrl}/sitemap.xml\n`);
fs.writeFileSync(path.join(out, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${['/', ...pages.map(page => page.url)].map(url => `<url><loc>${escape(new URL(url, config.siteUrl).href)}</loc></url>`).join('')}</urlset>`);
const archive = path.join(root, 'build/clack-0.1.0-source.zip');
if (fs.existsSync(archive)) { fs.mkdirSync(path.join(out, 'downloads'), { recursive: true }); fs.copyFileSync(archive, path.join(out, 'downloads/clack-source.zip')); }
console.log(`Built Clack website: ${pages.length + 1} pages and ${search.length} searchable sections → website/dist`);

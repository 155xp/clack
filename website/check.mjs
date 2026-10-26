import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const out = path.join(here, 'dist');
const config = JSON.parse(fs.readFileSync(path.join(here, 'config.json'), 'utf8'));
const staticOnly = process.argv.includes('--static-only');
const examples = process.argv.includes('--examples');
const problems = [];
const seenReferences = new Set();
const decode = text => text.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const list = directory => fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? list(path.join(directory, entry.name)) : [path.join(directory, entry.name)]);
const note = (condition, message) => { if (!condition) problems.push(message); };

if (!fs.existsSync(path.join(out, 'index.html'))) {
  console.error('Build the website first: npm run build');
  process.exit(1);
}

const htmlFiles = list(out).filter(file => file.endsWith('.html'));
const documents = new Map(htmlFiles.map(file => {
  const html = fs.readFileSync(file, 'utf8');
  const ids = [...html.matchAll(/\bid="([^"]*)"/g)].map(match => decode(match[1]));
  note(ids.length === new Set(ids).size, `${path.relative(out, file)}: duplicate element IDs`);
  return [file, { html, ids: new Set(ids) }];
}));

function resolveReference(reference, owner) {
  let url;
  try {
    const ownerPath = '/' + path.relative(out, owner).split(path.sep).join('/');
    url = new URL(decode(reference), new URL(ownerPath, config.siteUrl));
  } catch {
    problems.push(`${path.relative(out, owner)}: invalid URL ${reference}`);
    return;
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== new URL(config.siteUrl).origin) return;
  const key = `${owner}:${url.pathname}${url.hash}`;
  if (seenReferences.has(key)) return;
  seenReferences.add(key);
  let pathname;
  try { pathname = decodeURIComponent(url.pathname); }
  catch { problems.push(`Invalid encoded path ${url.pathname}`); return; }
  let destination = path.join(out, pathname);
  if (fs.existsSync(destination) && fs.statSync(destination).isDirectory()) destination = path.join(destination, 'index.html');
  else if (!fs.existsSync(destination) && !path.extname(destination) && fs.existsSync(destination + '.html')) destination += '.html';
  note(fs.existsSync(destination), `${path.relative(out, owner)}: missing local target ${reference}`);
  if (url.hash && documents.has(destination)) {
    const anchor = decodeURIComponent(url.hash.slice(1));
    note(documents.get(destination).ids.has(anchor), `${path.relative(out, owner)}: missing anchor ${reference}`);
  }
  note(!/\.md$/.test(url.pathname), `${path.relative(out, owner)}: Markdown link was not rewritten: ${reference}`);
}

for (const [file, { html }] of documents) {
  const label = path.relative(out, file);
  note(/<html\s[^>]*lang="en"/.test(html), `${label}: missing document language`);
  note((html.match(/<main\b/g) || []).length === 1, `${label}: expected one main landmark`);
  note((html.match(/<h1\b/g) || []).length === 1, `${label}: expected one page heading`);
  note(/<title>[^<]+<\/title>/.test(html), `${label}: missing title`);
  note(/<meta\s+name="description"\s+content="[^"]+"/.test(html), `${label}: missing description`);
  note(html.includes('<link rel="canonical" href="' + config.siteUrl), `${label}: missing canonical URL`);
  note(!html.includes('/workspace/') && !html.includes('href="undefined"') && !html.includes('src="undefined"'), `${label}: leaked build path or placeholder`);
  for (const match of html.matchAll(/\b(?:href|src)="([^"]+)"/g)) resolveReference(match[1], file);
}

const sourcePages = [...list(path.join(root, 'docs')).filter(file => file.endsWith('.md')), path.join(root, 'benchmarks/README.md')];
const routes = sourcePages.map(file => '/' + path.relative(root, file).split(path.sep).join('/').replace(/README\.md$/, '').replace(/\.md$/, '').replace(/\/$/, '') + '/');
for (const route of routes) note(fs.existsSync(path.join(out, route, 'index.html')), `Missing documentation route: ${route}`);
const index = JSON.parse(fs.readFileSync(path.join(out, 'search-index.json'), 'utf8'));
note(Array.isArray(index) && index.length >= routes.length, 'Search index is missing or incomplete');
for (const route of routes) note(index.some(entry => entry.url === route), `Search index omits ${route}`);
for (const entry of index) {
  note(typeof entry.title === 'string' && entry.title.length > 0 && typeof entry.text === 'string', 'Invalid search entry');
  resolveReference(entry.url, path.join(out, 'index.html'));
}
const sitemap = fs.readFileSync(path.join(out, 'sitemap.xml'), 'utf8');
for (const route of ['/', ...routes]) note(sitemap.includes(new URL(route, config.siteUrl).href), `Sitemap omits ${route}`);
note(fs.readFileSync(path.join(out, 'robots.txt'), 'utf8').includes(`${config.siteUrl}/sitemap.xml`), 'Robots file omits sitemap');
note(fs.readFileSync(path.join(out, 'index.html'), 'utf8').includes(config.githubUrl), 'Homepage omits verified GitHub link');

let interactionCount = 0;
if (!staticOnly) {
  const { parseHTML } = await import('linkedom');
  const { window } = parseHTML(fs.readFileSync(path.join(out, 'index.html'), 'utf8'));
  const { document } = window;
  let activeElement = document.body;
  Object.defineProperty(document, 'activeElement', { get: () => activeElement });
  window.HTMLElement.prototype.focus = function() { activeElement = this; };
  const dialog = document.querySelector('#search-dialog');
  dialog.open = false;
  dialog.showModal = () => { dialog.open = true; dialog.setAttribute('open', ''); };
  dialog.close = () => { dialog.open = false; dialog.removeAttribute('open'); dialog.dispatchEvent(new window.Event('close')); };
  dialog.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1000, bottom: 1000 });
  window.isSecureContext = true;
  let clipboard = '';
  let fetches = 0;
  const context = vm.createContext({
    window, document, Element: window.Element,
    navigator: { clipboard: { writeText: async value => { clipboard = value; } } },
    fetch: async url => { assert.equal(url, '/search-index.json'); fetches++; return { ok: true, json: async () => index }; },
    setTimeout: (callback, ms) => { const timer = setTimeout(callback, ms); timer.unref(); return timer; },
    clearTimeout, console,
  });
  vm.runInContext(fs.readFileSync(path.join(out, 'site.js'), 'utf8'), context, { filename: 'site.js' });
  const click = element => element.dispatchEvent(new window.Event('click', { bubbles: true, cancelable: true }));
  const key = (element, value, props = {}) => {
    const event = new window.Event('keydown', { bubbles: true, cancelable: true });
    Object.assign(event, { key: value, ...props });
    element.dispatchEvent(event);
  };
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const tabs = [...document.querySelectorAll('[data-code-tab]')];
  assert.equal(tabs.length, 3, 'Homepage should contain the three live code tabs');
  click(tabs[1]);
  assert.equal(tabs[1].getAttribute('aria-selected'), 'true');
  assert.equal(document.querySelector('#example-contracts').hidden, false);
  assert.equal(document.querySelector('#example-parallel').hidden, true);
  key(tabs[1], 'ArrowRight');
  assert.equal(tabs[2].getAttribute('aria-selected'), 'true');
  assert.equal(document.activeElement, tabs[2]);
  key(tabs[2], 'Home');
  assert.equal(tabs[0].getAttribute('aria-selected'), 'true');
  interactionCount += 3;

  const menu = document.querySelector('[data-menu-toggle]');
  click(menu);
  assert.equal(menu.getAttribute('aria-expanded'), 'true');
  assert.equal(document.querySelector('#mobile-navigation').hidden, false);
  key(document.body, 'Escape');
  assert.equal(menu.getAttribute('aria-expanded'), 'false');
  assert.equal(document.querySelector('#mobile-navigation').hidden, true);
  interactionCount += 2;

  const trigger = document.querySelector('[data-search-open]');
  trigger.focus();
  click(trigger);
  await flush();
  assert.equal(dialog.open, true);
  const input = document.querySelector('#search-input');
  assert.equal(document.activeElement, input);
  input.value = 'sum4';
  input.dispatchEvent(new window.Event('input'));
  const results = document.querySelector('#search-results');
  assert(results.querySelector('a'), 'Searching for an available helper should return documentation');
  key(input, 'ArrowDown');
  assert.equal(document.activeElement, results.querySelector('a'));
  input.value = 'clack-nonexistent-topic-847398';
  input.dispatchEvent(new window.Event('input'));
  assert.match(results.textContent, /No pages found/);
  click(document.querySelector('[data-search-close]'));
  assert.equal(dialog.open, false);
  assert.equal(document.activeElement, trigger);
  key(document.body, 'k', { ctrlKey: true });
  await flush();
  assert.equal(dialog.open, true);
  assert.equal(fetches, 1, 'Repeated search should reuse the fetched index');
  dialog.close();
  interactionCount += 5;

  const copy = document.querySelector('#example-parallel [data-copy]');
  click(copy);
  await flush();
  assert.match(clipboard, /from std\.array import sum4/);
  assert.equal(copy.textContent, 'Copied');
  interactionCount++;

  if (examples) {
    const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'clack-site-examples-'));
    try {
      const python = fs.existsSync(path.join(root, '.venv/bin/python')) ? path.join(root, '.venv/bin/python') : 'python3';
      for (const panel of document.querySelectorAll('[data-code-panel]')) {
        const file = path.join(temporary, panel.id + '.clack');
        fs.writeFileSync(file, panel.querySelector('.code-block code').textContent + '\n');
        const result = spawnSync(python, ['-m', 'clack', 'run', file], { cwd: root, encoding: 'utf8', timeout: 30000 });
        assert.equal(result.status, 0, `${panel.id}: ${result.error || result.stderr}`);
        assert.equal(result.stdout.trim(), panel.querySelector('.example-output code').textContent.trim(), `${panel.id}: displayed output differs from native execution`);
      }
    } finally { fs.rmSync(temporary, { recursive: true, force: true }); }
  }
}

if (problems.length) {
  for (const problem of problems) console.error(problem);
  process.exit(1);
}
console.log(`Site checked: ${htmlFiles.length} HTML pages, ${seenReferences.size} internal references, ${index.length} search entries, ${interactionCount} client interaction checks${examples ? ', 3 native code examples' : ''}.`);
console.log('DOM checks use an emulated document; visual layout and real browser rendering are not covered.');

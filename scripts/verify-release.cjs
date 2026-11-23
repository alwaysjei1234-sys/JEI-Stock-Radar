#!/usr/bin/env node
// Dependency-free JEI release sanity checks. Never prints private holdings or credentials.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function read(rel) { return fs.readFileSync(path.join(root, rel), 'utf8'); }
function check(name, fn) {
  try { fn(); console.log('PASS', name); }
  catch (e) { console.error('FAIL', name, '-', e.message); process.exitCode = 1; }
}
check('remote UI exists and is HTML', () => {
  const html = read('remote/index.html');
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /<html\b/i);
  assert.match(html, /<\/html>/i);
});
check('system feed is valid JSON', () => {
  const feed = JSON.parse(read('remote/system.json'));
  assert.ok(feed && typeof feed === 'object' && !Array.isArray(feed));
});
check('update manifest is valid JSON', () => {
  const manifest = JSON.parse(read('remote/update.json'));
  assert.ok(manifest && typeof manifest === 'object' && !Array.isArray(manifest));
});
check('UI has no unresolved merge markers', () => {
  assert.doesNotMatch(read('remote/index.html'), /^(<<<<<<< |=======\s*$|>>>>>>> )/m);
});

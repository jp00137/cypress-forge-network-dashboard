import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';

// Core colours live only in the cf-tokens block at the top of style.css (docs/THEME-SEAM.md),
// so an add-on can recolour the dashboard by overriding --cf-* variables.
const LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(/g;
const stripComments = css => css.replace(/\/\*[\s\S]*?\*\//g, '');

test('stylesheets use colour tokens outside the token block', () => {
  for (const file of ['style.css', 'workspace.css', 'firewall.css']) {
    let css = readFileSync(`src/${file}`, 'utf8');
    if (file === 'style.css') {
      const start = css.indexOf('/* cf-tokens'), end = css.indexOf('/* end cf-tokens */');
      assert.ok(start === 0 && end > start, 'style.css must start with the cf-tokens block');
      css = css.slice(end);
    }
    assert.deepEqual(stripComments(css).match(LITERAL) ?? [], [], `${file} has literal colours`);
  }
});

test('token block defines the documented contract names', () => {
  const css = readFileSync('src/style.css', 'utf8');
  const block = css.slice(0, css.indexOf('/* end cf-tokens */'));
  for (const name of ['bg', 'panel', 'panel-2', 'line', 'line-2', 'text', 'muted', 'accent', 'accent-2',
    'accent-soft', 'on-accent', 'ok', 'warn', 'bad', 'shadow'])
    assert.match(block, new RegExp(`--cf-${name}:`), `missing --cf-${name}`);
});

test('components carry no literal colours', () => {
  for (const file of readdirSync('src').filter(f => f.endsWith('.tsx')))
    assert.deepEqual(readFileSync(`src/${file}`, 'utf8').match(/#[0-9a-fA-F]{6}\b/g) ?? [], [], `${file} has literal colours`);
});

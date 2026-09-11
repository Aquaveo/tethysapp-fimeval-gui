// reactapp/scripts/sync-docs.mjs
//
// FE55 — refresh the bundled in-app docs from the upstream FIMeval repo, so the
// /docs page (FE49) doesn't drift from sdmlua/fimeval. Replaces the one-time
// manual copy: pulls README.md + every Images/* into the exact locations the app
// already renders from, keeping the docs bundled (so /docs still works offline
// from the last sync — this script is what refreshes "the last sync").
//
// Run:  npm run sync-docs           (from reactapp/)
// Env:  FIMEVAL_DOCS_REF   upstream branch/tag/sha to pull (default: main)
//       GITHUB_TOKEN       optional; raises the API rate limit in CI
//
// Writes:
//   reactapp/src/docs/fimeval.md                          (the ?raw import)
//   tethysapp/fimeval_gui/public/images/docs/<image>      (served as static)
//
// Exits non-zero on any fetch/write failure so a CI job can tell it went stale.

import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = 'sdmlua/fimeval';
const REF = process.env.FIMEVAL_DOCS_REF || 'main';

// Paths are resolved from this script's location so it runs the same from any CWD.
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(SCRIPT_DIR, '..', '..'); // reactapp/scripts -> repo root
const DOC_MD_PATH = join(REPO_ROOT, 'reactapp/src/docs/fimeval.md');
const IMAGES_DIR = join(REPO_ROOT, 'tethysapp/fimeval_gui/public/images/docs');

const RAW_BASE = `https://raw.githubusercontent.com/${REPO}/${REF}`;
const CONTENTS_API = `https://api.github.com/repos/${REPO}/contents`;

function ghHeaders(accept) {
  const headers = { 'User-Agent': 'fimeval-docs-sync', Accept: accept };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return headers;
}

async function fetchText(url) {
  const res = await fetch(url, { headers: ghHeaders('text/plain') });
  if (!res.ok) throw new Error(`GET ${url} -> HTTP ${res.status}`);
  return res.text();
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: ghHeaders('application/vnd.github+json') });
  if (!res.ok) throw new Error(`GET ${url} -> HTTP ${res.status}`);
  return res.json();
}

async function fetchBinary(url) {
  const res = await fetch(url, { headers: ghHeaders('application/octet-stream') });
  if (!res.ok) throw new Error(`GET ${url} -> HTTP ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

function kb(bytes) {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

// Sections of the upstream README that describe the git repo / package install
// rather than the web app — stripped from the synced doc so /docs stays
// web-app-focused. Each spec removes lines from a heading whose text contains
// `from` up to (but not including) the next heading whose text contains `to`
// (case-insensitive); `to: null` strips to end-of-doc. Matched on heading text
// so it survives line-number drift; if `from` isn't found the section is simply
// left in (logged), and if `to` isn't found the section is kept (to avoid
// over-stripping). The static web-app sections (Contact, FAQs) live separately
// in reactapp/src/docs/webapp.md and are never synced.
const STRIP_SECTIONS = [
  { from: 'repository structure', to: 'framework installation' },
  { from: 'main directory structure', to: 'permanent water' },
  { from: 'installation instructions', to: 'desktop application' },
  { from: 'for more information', to: null },
];

function headingText(line) {
  const m = /^#{1,6}\s+(.*)$/.exec(line);
  return m ? m[1].replace(/[*`#]/g, '').trim().toLowerCase() : null;
}

function stripSections(md) {
  const lines = md.split('\n');
  // Index the real (non-code-fenced) headings once.
  const headings = [];
  let fenced = false;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*```/.test(lines[i])) { fenced = !fenced; continue; }
    if (fenced) continue;
    const text = headingText(lines[i]);
    if (text !== null) headings.push({ index: i, text });
  }
  const remove = new Set();
  for (const spec of STRIP_SECTIONS) {
    const start = headings.find((h) => h.text.includes(spec.from));
    if (!start) {
      console.warn(`  ! strip: heading containing "${spec.from}" not found — left in`);
      continue;
    }
    let end;
    if (spec.to === null) {
      end = lines.length;
    } else {
      const stop = headings.find((h) => h.index > start.index && h.text.includes(spec.to));
      if (!stop) {
        console.warn(`  ! strip: end "${spec.to}" not found after "${spec.from}" — section kept`);
        continue;
      }
      end = stop.index;
    }
    for (let i = start.index; i < end; i++) remove.add(i);
    console.log(`  stripped section "${spec.from}" (${end - start.index} lines)`);
  }
  // Drop removed lines and collapse the blank-line runs left behind.
  return lines.filter((_, i) => !remove.has(i)).join('\n').replace(/\n{3,}/g, '\n\n');
}

async function main() {
  console.log(`Syncing docs from ${REPO}@${REF}`);

  // 1) README.md -> the bundled markdown the docs page imports. Repo-specific
  //    sections are stripped so /docs stays web-app-focused (the kept sections
  //    still track upstream).
  const readme = await fetchText(`${RAW_BASE}/README.md`);
  const curated = stripSections(readme);
  await mkdir(dirname(DOC_MD_PATH), { recursive: true });
  await writeFile(DOC_MD_PATH, curated, 'utf8');
  console.log(
    `  README.md        ${kb(Buffer.byteLength(curated))} (from ${kb(Buffer.byteLength(readme))} upstream)  -> ${DOC_MD_PATH}`,
  );

  // 2) Images/* -> the static docs image dir Docs.tsx rewrites paths to. The
  //    listing gives one entry per file with a raw download_url; only files are
  //    pulled (no recursion — the repo keeps its doc images flat under Images/).
  const entries = await fetchJson(`${CONTENTS_API}/Images?ref=${REF}`);
  const images = entries.filter((e) => e.type === 'file' && e.download_url);
  if (images.length === 0) throw new Error('No images found under Images/ — refusing to continue');
  await mkdir(IMAGES_DIR, { recursive: true });
  for (const img of images) {
    const bytes = await fetchBinary(img.download_url);
    const dest = join(IMAGES_DIR, img.name);
    await writeFile(dest, bytes);
    console.log(`  Images/${img.name.padEnd(28)} ${kb(bytes.length)}  -> ${dest}`);
  }

  console.log(`Done: README + ${images.length} image(s) synced.`);
}

main().catch((err) => {
  console.error(`sync-docs failed: ${err.message}`);
  process.exit(1);
});

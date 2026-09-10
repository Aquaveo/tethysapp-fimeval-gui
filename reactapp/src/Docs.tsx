// reactapp/src/Docs.tsx
// In-app FIMeval documentation (FE49). Renders the FIMeval README (synced from
// the sdmlua/fimeval OG repo, with repo-only sections stripped at sync time)
// followed by the web-app-specific sections (Contact & Attribution, FAQs), with
// a generated "Contents" sidebar. Local image references are rewritten to the
// Tethys static path. Content is bundled, so /docs works offline.
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSlug from 'rehype-slug';
import rawDoc from './docs/fimeval.md?raw';
import rawWebapp from './docs/webapp.md?raw';
import './Docs.css';

// Where the repo's local Images/ were copied (served by Tethys like the chrome).
const IMG_BASE = '/static/fimeval_gui/images/docs/';

// Heading slug matching rehype-slug (github-slugger): lowercase, drop anything
// that isn't a word char / space / hyphen, then one hyphen per whitespace char
// (NOT collapsed — so "A & B" -> "a--b", same as the rendered heading's id).
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s/g, '-');
}

type TocEntry = { text: string; slug: string };
type TocItem = TocEntry & { children: TocEntry[] };

// Two-level "Contents" tree from the markdown headings (skipping code fences).
// The shallowest heading level present is the top level; the next deeper level
// nests under it — matching the README's loose ###/#### hierarchy.
function buildToc(md: string): TocItem[] {
  const flat: { level: number; text: string; slug: string }[] = [];
  let fenced = false;
  for (const line of md.split('\n')) {
    if (/^\s*```/.test(line)) { fenced = !fenced; continue; }
    if (fenced) continue;
    const m = /^(#{2,4})\s+(.+)$/.exec(line.trim());
    if (!m) continue;
    const text = m[2].replace(/[*`#]/g, '').trim();
    if (text) flat.push({ level: m[1].length, text, slug: slugify(text) });
  }
  if (flat.length === 0) return [];
  const top = Math.min(...flat.map((h) => h.level));
  const items: TocItem[] = [];
  let current: TocItem | null = null;
  for (const h of flat) {
    if (h.level === top) {
      current = { text: h.text, slug: h.slug, children: [] };
      items.push(current);
    } else if (h.level === top + 1 && current) {
      current.children.push({ text: h.text, slug: h.slug });
    }
  }
  return items;
}

export default function Docs() {
  // Synced doc + static web-app sections, with repo image paths rewritten to the
  // bundled static location.
  const md = `${rawDoc}\n\n${rawWebapp}`.replace(/(?:\.\/)?Images\//g, IMG_BASE);
  const toc = buildToc(md);

  return (
    <div className="docs">
      {toc.length > 0 && (
        <aside className="docs-toc" aria-label="Contents">
          <p className="docs-toc-title">Contents</p>
          <nav aria-label="Table of contents">
            <ol className="docs-toc-list">
              {toc.map((t, i) => (
                <li key={i} className="docs-toc-item">
                  <a href={`#${t.slug}`} className="docs-toc-link">{t.text}</a>
                  {t.children.length > 0 && (
                    <ol className="docs-toc-sublist">
                      {t.children.map((c, j) => (
                        <li key={j}>
                          <a href={`#${c.slug}`} className="docs-toc-link">{c.text}</a>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      )}
      <article className="docs-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, rehypeSlug]}
        >
          {md}
        </ReactMarkdown>
      </article>
    </div>
  );
}

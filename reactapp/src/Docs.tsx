// reactapp/src/Docs.tsx
// In-app FIMeval documentation (FE49). Renders the FIMeval README (bundled from
// the sdmlua/fimeval OG repo) as markdown, with a generated table-of-contents
// sidebar. Local image references are rewritten to the Tethys static path where
// the repo's diagrams were copied. Content is bundled, so /docs works offline.
import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSlug from 'rehype-slug';
import rawDoc from './docs/fimeval.md?raw';
import './Docs.css';

// Where the repo's local Images/ were copied (served by Tethys like the chrome).
const IMG_BASE = '/static/fimeval_gui/images/docs/';

// GitHub-style heading slug, matching rehype-slug's output so TOC anchors resolve.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-');
}

type TocItem = { level: number; text: string; slug: string };

export default function Docs() {
  // Rewrite the repo's relative image paths (./Images/… or Images/…) to the
  // bundled static location.
  const md = useMemo(() => rawDoc.replace(/(?:\.\/)?Images\//g, IMG_BASE), []);

  // Build the TOC from the h2/h3 headings.
  const toc = useMemo<TocItem[]>(() => {
    const items: TocItem[] = [];
    for (const line of md.split('\n')) {
      const m = /^(#{2,3})\s+(.+)$/.exec(line.trim());
      if (!m) continue;
      const text = m[2].replace(/[*`#]/g, '').trim();
      if (text) items.push({ level: m[1].length, text, slug: slugify(text) });
    }
    return items;
  }, [md]);

  return (
    <div className="docs">
      {toc.length > 0 && (
        <aside className="docs-toc" aria-label="On this page">
          <h2 className="docs-toc-title">On this page</h2>
          <nav>
            {toc.map((t, i) => (
              <a key={i} href={`#${t.slug}`} className={`docs-toc-link lvl-${t.level}`}>
                {t.text}
              </a>
            ))}
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

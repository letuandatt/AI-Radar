import Markdown from 'react-markdown';
import { Link } from 'react-router-dom';
import type { DigestView } from '../../api/generated';
import { editionLabel } from '../../hooks/useDigest';
import { safeUrl, storyUrl } from '../shared/Reading';

/** No raw HTML, embedded media, relative URLs, or automatic third-party requests. */
export function DigestMarkdown({ content }: { content: string }) {
  return (
    <div className="digest-markdown">
      <Markdown
        skipHtml
        allowedElements={[
          'p',
          'strong',
          'em',
          'a',
          'ul',
          'ol',
          'li',
          'blockquote',
          'code',
          'pre',
          'hr',
          'br',
          'h1',
          'h2',
          'h3',
          'h4',
          'h5',
          'h6',
        ]}
        urlTransform={url => safeUrl(url) ?? ''}
        components={{
          a: ({ href, children }) =>
            href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
          h1: ({ children }) => <h3>{children}</h3>,
          h2: ({ children }) => <h3>{children}</h3>,
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}

export function DigestViewer({ digest }: { digest: DigestView }) {
  return (
    <article className="digest-content" aria-label="Saved digest">
      <header className="edition-stamp">
        <span className="tiny-label">SAVED EDITION · UTC</span>
        <h2>{editionLabel(digest.digest_date)}</h2>

        <p>
          {digest.total_items} curated stories · Generated{' '}
          <time dateTime={digest.generated_at}>
            {new Date(digest.generated_at).toLocaleString()}
          </time>
        </p>
      </header>

      {digest.intelligence.sections.map(section => (
        <section
          className="digest-section"
          key={section.section_id}
        >
          <h2>{section.title}</h2>
          <DigestMarkdown content={section.content} />
        </section>
      ))}

      {digest.sections.map(section => (
        <section
          className="digest-section"
          key={section.section_id}
        >
          <h2>{section.section_title}</h2>

          {!section.items?.length && (
            <p className="muted">No stories in this section.</p>
          )}

          {(section.items ?? []).map(item => (
            <div
              className="digest-item"
              key={item.knowledge_id}
            >
              <Link to={storyUrl(item.knowledge_id)}>
                {item.title} ↗
              </Link>

              <p>{item.summary}</p>

              <span className="tiny-label">
                {item.source_name}
              </span>
            </div>
          ))}
        </section>
      ))}
    </article>
  );
}
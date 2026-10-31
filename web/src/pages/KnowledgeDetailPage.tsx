import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight } from 'lucide-react';

import { useGetKnowledge, useGetRelated } from '../api/generated';
import { allowedFields, useSchema } from '../hooks/useSchema';
import {
  Relevance,
  SourceIcon,
} from '../components/knowledge/KnowledgeResults';
import {
  Cover,
  Loading,
  Message,
  dateLabel,
  errorText,
  safeUrl,
  storyUrl,
} from '../components/shared/Reading';

import './knowledge.css';

function RelatedItems({ id, backTo }: { id: string; backTo: string }) {
  const query = useGetRelated(encodeURIComponent(id), { top_k: 3 });
  const seen = new Set<string>([id]);

  const items = (query.data?.results ?? []).filter(item => {
    if (seen.has(item.knowledge_id)) return false;

    seen.add(item.knowledge_id);
    return true;
  }).slice(0, 3);

  return (
    <section className="related-section" aria-label="Related stories">
      <div className="section-heading">
        <div>
          <span className="tiny-label">KEEP EXPLORING</span>
          <h2>More like this</h2>
        </div>
      </div>

      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <Message
          title="Related stories couldn't load."
          retry={() => void query.refetch()}
        >
          You can keep reading this article while we reconnect.
        </Message>
      ) : !items.length ? (
        <p className="muted">No related stories yet.</p>
      ) : (
        <div className="related-grid">
          {items.map((item, index) => (
            <article key={item.knowledge_id}>
              <Cover variant={index} />

              <div className="source-label">
                <SourceIcon type={item.source_type ?? ''} />
                {item.source_name}
              </div>

              <h3>
                <Link
                  to={storyUrl(item.knowledge_id)}
                  state={{ backTo }}
                >
                  {item.title}
                </Link>
              </h3>

              <p className="search-snippet">{item.content_snippet}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function KnowledgeDetailPage() {
  const { id = '' } = useParams();
  const location = useLocation();

  const previous = (
    location.state as { backTo?: unknown } | null
  )?.backTo;

  const backTo = typeof previous === 'string' &&
    /^\/knowledge(?:\?|$)/.test(previous)
    ? previous
    : '/knowledge';

  const query = useGetKnowledge(encodeURIComponent(id));
  const schema = useSchema('detail');

  const back = (
    <Link to={backTo} className="text-link">
      <ArrowLeft size={16} />
      Back to stories
    </Link>
  );

  if (query.isPending || schema.isPending) {
    return (
      <section className="reading-page">
        {back}
        <Loading detail />
      </section>
    );
  }

  if (
    query.isError ||
    schema.isError ||
    !query.data ||
    !schema.data
  ) {
    const error = query.error ?? schema.error;
    const missing = (
      error as { status?: number } | null
    )?.status === 404;

    return (
      <section className="reading-page">
        {back}

        <Message
          title={missing ? 'Story not found.' : "This story isn't available."}
          retry={missing ? undefined : () => {
            void query.refetch();
            void schema.refetch();
          }}
        >
          {errorText(error)}
        </Message>
      </section>
    );
  }

  const item = query.data;
  const original = safeUrl(item.source_url);
  const values: Record<string, unknown> = { ...item, ...item.metadata };

  const fields = allowedFields(schema.data, {
    title: 'text',
    source_name: 'text',
    published_at: 'date',
    fetched_at: 'date',
    summary: 'text',
    topics: 'tags',
    entities: 'tags',
    relevance_score: 'score',
    content_text: 'text',
  });

  return (
    <article className="reading-page knowledge-detail">
      {back}

      <div className="eyebrow article-source">
        <SourceIcon type={item.source_type} />
        {item.source_type}
      </div>

      {fields.some(field => field.key === 'title') && (
        <h1>{item.title}</h1>
      )}

      <div className="article-byline">
        {fields
          .filter(field =>
            ['source_name', 'published_at', 'fetched_at'].includes(field.key))
          .map(field => (
            <span key={field.key}>
              {field.label}: {field.renderer === 'date'
                ? dateLabel(values[field.key] as string | null)
                : String(values[field.key] ?? '')}
            </span>
          ))}

        {original && (
          <a
            href={original}
            target="_blank"
            rel="noopener noreferrer"
            className="text-link"
          >
            Original source
            <ArrowUpRight size={16} />
          </a>
        )}
      </div>

      <Cover large variant={1} />

      {fields
        .filter(field =>
          !['title', 'source_name', 'published_at', 'fetched_at'].includes(field.key))
        .map(field => {
          const value = values[field.key];

          if (field.renderer === 'score') {
            return (
              <div className="detail-score" key={field.key}>
                <Relevance value={Number(value)} />
              </div>
            );
          }

          if (field.renderer === 'tags') {
            return (
              <section className="metadata-section" key={field.key}>
                <h2 className="tiny-label">{field.label}</h2>

                <div className="topic-tags">
                  {Array.isArray(value) && value.length
                    ? value.map((entry, index) => (
                      <span key={index}>{String(entry)}</span>
                    ))
                    : <span>Not available</span>}
                </div>
              </section>
            );
          }

          if (field.key === 'summary') {
            return value ? (
              <p className="article-summary" key={field.key}>
                {String(value)}
              </p>
            ) : null;
          }

          return (
            <div className="article-content" key={field.key}>
              {String(value || 'No article text available.')}
            </div>
          );
        })}

      <RelatedItems key={id} id={id} backTo={backTo} />
    </article>
  );
}
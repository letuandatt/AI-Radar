import { Link } from 'react-router-dom';
import { GitBranch, Rss, Boxes, Newspaper } from 'lucide-react';

import type { UISchema } from '../../api/generated';
import { allowedFields } from '../../hooks/useSchema';
import type { ReadingItem } from '../../hooks/useKnowledge';
import { Cover, dateLabel, storyUrl } from '../shared/Reading';

export const listBindings = {
  title: 'text',
  source_type: 'text',
  published_at: 'date',
  topics: 'tags',
  relevance_score: 'score',
};

export function SourceIcon({ type }: { type: string }) {
  const Icon = type === 'github'
    ? GitBranch
    : type === 'rss'
      ? Rss
      : ['hf', 'huggingface'].includes(type)
        ? Boxes
        : Newspaper;

  return <Icon size={14} aria-hidden="true" />;
}

export function Relevance({ value }: { value?: number }) {
  if (
    value == null ||
    !Number.isFinite(value) ||
    value < 0 ||
    value > 1
  ) {
    return null;
  }

  return (
    <span
      className={`relevance ${
        value >= .8 ? 'high' : value >= .5 ? 'medium' : 'low'
      }`}
      title="AI/tech relevance from metadata extraction, not search ranking"
    >
      AI relevance {Math.round(value * 100)}%
    </span>
  );
}

export function KnowledgeResults({
  items,
  schema,
  backTo,
  ranked = false,
}: {
  items: ReadingItem[];
  schema: UISchema;
  backTo: string;
  ranked?: boolean;
}) {
  const fields = allowedFields(schema, listBindings);

  return (
    <div className="story-grid knowledge-grid">
      {items.map((item, index) => (
        <article className="story-card" key={item.id}>
          <Link
            className="cover-link"
            to={storyUrl(item.id)}
            state={{ backTo }}
            tabIndex={-1}
            aria-hidden="true"
          >
            <Cover variant={index + 1} />
          </Link>

          <div className="knowledge-card-fields">
            {fields.map(field => {
              if (field.key === 'title') {
                return (
                  <h3 key={field.key}>
                    <Link to={storyUrl(item.id)} state={{ backTo }}>
                      {item.title}
                    </Link>
                  </h3>
                );
              }

              if (field.key === 'source_type') {
                return (
                  <div className="source-label" key={field.key}>
                    <SourceIcon type={item.source_type} />
                    {item.source_name || item.source_type}
                    <span className="muted">{item.source_type}</span>
                  </div>
                );
              }

              if (field.key === 'published_at') {
                return (
                  <time
                    key={field.key}
                    dateTime={item.published_at || undefined}
                    className="muted"
                  >
                    {dateLabel(item.published_at)}
                  </time>
                );
              }

              if (field.key === 'topics') {
                return (
                  <div key={field.key} className="topic-tags">
                    {(item.topics ?? []).slice(0, 3).map(topic => (
                      <span key={topic}>{topic}</span>
                    ))}
                  </div>
                );
              }

              return (
                <Relevance
                  key={field.key}
                  value={item.relevance_score}
                />
              );
            })}

            {ranked && (
              <p className="search-snippet">{item.snippet}</p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export function Pagination({
  page,
  total,
  busy,
  onPage,
}: {
  page: number;
  total: number;
  busy: boolean;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.min(5001, Math.ceil(total / 20)));

  const numbers = [...new Set([1, page - 1, page, page + 1, pages])]
    .filter(x => x > 0 && x <= pages)
    .sort((a, b) => a - b);

  if (pages === 1 && page === 1) return null;

  return (
    <nav
      className="pagination knowledge-pagination"
      aria-label="Result pages"
    >
      <button
        className="pill-button"
        disabled={page <= 1 || busy}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>

      {numbers.map((number, index) => (
        <span key={number}>
          {index > 0 && number - numbers[index - 1] > 1 && (
            <span aria-hidden="true">… </span>
          )}

          <button
            className="page-number"
            aria-label={`Page ${number}`}
            aria-current={page === number ? 'page' : undefined}
            disabled={busy}
            onClick={() => onPage(number)}
          >
            {number}
          </button>
        </span>
      ))}

      <button
        className="pill-button"
        disabled={page >= pages || busy}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}
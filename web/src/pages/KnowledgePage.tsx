import { useGetSourceHealth } from '../api/generated';
import { KnowledgeFilters } from '../components/knowledge/KnowledgeFilters';
import {
  KnowledgeResults,
  Pagination,
  listBindings,
} from '../components/knowledge/KnowledgeResults';
import {
  Loading,
  Message,
  errorText,
} from '../components/shared/Reading';
import { emptyState, useKnowledge } from '../hooks/useKnowledge';
import { allowedFields, useSchema } from '../hooks/useSchema';

import './knowledge.css';

export function KnowledgePage() {
  const {
    state,
    params,
    query,
    items,
    searching,
    validation,
    apply,
  } = useKnowledge();

  const table = useSchema('table');
  const filters = useSchema('filter');
  const sources = useGetSourceHealth();

  const backTo = `/knowledge${params.size ? `?${params}` : ''}`;

  const sortFields = table.data
    ? allowedFields(table.data, listBindings).filter(field =>
      field.sortable &&
      ['source_type', 'published_at'].includes(field.key))
    : [];

  return (
    <>
      <section className="edition-heading">
        <div className="eyebrow">
          <span className="signal-dot" />
          THE KNOWLEDGE COLLECTION
        </div>

        <div className="edition-title">
          <h1>
            Follow your<br /><em>curiosity.</em>
          </h1>

          <div className="edition-note">
            <p>
              Find the ideas worth a closer look.
              <br />
              Read, connect, explore.
            </p>
          </div>
        </div>
      </section>

      {filters.isPending || table.isPending ? (
        <Loading />
      ) : filters.isError || table.isError ? (
        <Message
          title="The collection controls couldn't load."
          retry={() => {
            void filters.refetch();
            void table.refetch();
          }}
        >
          Please try again.
        </Message>
      ) : filters.data && table.data && (
        <section
          className="knowledge-section"
          aria-label="Knowledge collection"
        >
          <KnowledgeFilters
            key={params.toString()}
            schema={filters.data}
            initial={state}
            sources={sources.data ?? []}
            onApply={apply}
          />

          {sources.isError && (
            <p role="status" className="muted">
              Source suggestions are unavailable.
              <button
                className="text-link"
                onClick={() => void sources.refetch()}
              >
                Retry sources
              </button>
            </p>
          )}

          <div
            className="channel-tabs"
            role="group"
            aria-label="Story categories"
          >
            {[
              ['All stories'],
              ['News & ideas', 'rss', 'hackernews'],
              ['Open source', 'github'],
              ['Models', 'hf', 'huggingface'],
            ].map(([label, ...types]) => (
              <button
                key={label}
                aria-pressed={
                  JSON.stringify(state.source_types) === JSON.stringify(types)
                }
                onClick={() => apply({
                  ...state,
                  source_types: types,
                  page: 1,
                })}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="section-heading">
            <div>
              <span className="tiny-label">THE READING LIST</span>

              <h2>
                {searching
                  ? 'Results for your curiosity'
                  : 'Explore the collection'}
              </h2>

              {query.data && (
                <p className="muted" role="status">
                  {query.data.total} {searching
                    ? 'ranked matches returned · best matches first · up to 50'
                    : 'stories in this view'}
                </p>
              )}
            </div>

            {!searching && (
              <label className="sort-control">
                Sort by
                <select
                  aria-label="Sort stories"
                  value={`${state.sort}:${state.direction}`}
                  onChange={event => {
                    const [sort, direction] = event.target.value.split(':');

                    apply({
                      ...state,
                      sort: sort as typeof state.sort,
                      direction: direction as typeof state.direction,
                      page: 1,
                    });
                  }}
                >
                  {sortFields.flatMap(field =>
                    ['desc', 'asc'].map(direction => (
                      <option
                        key={`${field.key}:${direction}`}
                        value={`${field.key}:${direction}`}
                      >
                        {field.label} · {
                          direction === 'desc' ? 'descending' : 'ascending'
                        }
                      </option>
                    )))}
                </select>
              </label>
            )}
          </div>

          {validation ? (
            <Message title="Check your filters">
              {validation}
            </Message>
          ) : query.isPending ? (
            <Loading />
          ) : query.isError ? (
            <Message
              title="Your stories couldn't load."
              retry={() => void query.refetch()}
            >
              {errorText(query.error)}
            </Message>
          ) : !items.length ? (
            <div>
              <Message
                title={state.page > 1
                  ? 'This page is empty.'
                  : 'A little quiet on this frequency.'}
              >
                {state.page > 1
                  ? 'The collection may have changed. Return to the first page.'
                  : 'No saved stories match this view. Clear filters or try another search.'}
              </Message>

              <div className="filter-actions">
                <button
                  className="pill-button"
                  onClick={() => apply({ ...emptyState })}
                >
                  Clear filters and search
                </button>

                {state.page > 1 && (
                  <button
                    className="pill-button"
                    onClick={() => apply({ ...state, page: 1 })}
                  >
                    First page
                  </button>
                )}
              </div>
            </div>
          ) : (
            <KnowledgeResults
              items={items}
              schema={table.data}
              backTo={backTo}
              ranked={searching}
            />
          )}

          {!validation && query.data && (
            <Pagination
              page={state.page}
              total={query.data.total}
              busy={query.isFetching}
              onPage={page => apply({ ...state, page })}
            />
          )}
        </section>
      )}
    </>
  );
}
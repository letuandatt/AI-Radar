import { useState, type FormEvent } from 'react';

import type { SourceHealth, UISchema } from '../../api/generated';
import { allowedFields } from '../../hooks/useSchema';
import {
  emptyState,
  validate,
  type FilterState,
} from '../../hooks/useKnowledge';

export function KnowledgeFilters({
  schema,
  initial,
  sources,
  onApply,
}: {
  schema: UISchema;
  initial: FilterState;
  sources: SourceHealth[];
  onApply: (value: FilterState) => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [error, setError] = useState('');
  const [topicsText, setTopicsText] = useState(initial.topics.join(', '));

  const fields = allowedFields(schema, {
    source_types: 'multiselect',
    source_names: 'multiselect',
    topics: 'multiselect',
    published_at: 'date-range',
  });

  const update = <K extends keyof FilterState>(
    key: K,
    value: FilterState[K],
  ) => setDraft(current => ({ ...current, [key]: value }));

  function submit(event: FormEvent) {
    event.preventDefault();

    const value = {
      ...draft,
      q: draft.q.trim(),
      page: 1,
      topics: [
        ...new Set(
          topicsText.split(',').map(x => x.trim()).filter(Boolean),
        ),
      ],
    };

    const invalid = validate(value);
    setError(invalid ?? '');

    if (!invalid) onApply(value);
  }

  return (
    <form
      className="knowledge-filters"
      onSubmit={submit}
      aria-label="Find stories"
    >
      <div className="search-line">
        <label htmlFor="knowledge-search" className="sr-only">
          Search stories
        </label>

        <input
          id="knowledge-search"
          type="search"
          value={draft.q}
          placeholder="What are you curious about?"
          maxLength={1000}
          onChange={event => update('q', event.target.value)}
        />

        <button className="pill-button primary-button" type="submit">
          Search
        </button>
      </div>

      <details
        open={Boolean(
          initial.source_types.length ||
          initial.source_names.length ||
          initial.topics.length ||
          initial.from ||
          initial.to
        )}
      >
        <summary>Refine your reading</summary>

        <div className="filter-grid">
          {fields.map(field => {
            if (field.key === 'published_at') {
              return (
                <fieldset key={field.key}>
                  <legend>{field.label}</legend>

                  <label>
                    From
                    <input
                      type="date"
                      value={draft.from}
                      onChange={e => update('from', e.target.value)}
                    />
                  </label>

                  <label>
                    Through
                    <input
                      type="date"
                      value={draft.to}
                      onChange={e => update('to', e.target.value)}
                    />
                  </label>
                </fieldset>
              );
            }

            if (field.key === 'topics') {
              return (
                <label key={field.key}>
                  {field.label}
                  <input
                    value={topicsText}
                    placeholder="agents, retrieval"
                    onChange={e => setTopicsText(e.target.value)}
                  />

                  <small>Separate topics with commas.</small>

                  <span className="topic-tags">
                    {[
                      ...new Set(
                        topicsText.split(',')
                          .map(x => x.trim())
                          .filter(Boolean),
                      ),
                    ].map(x => <span key={x}>{x}</span>)}
                  </span>
                </label>
              );
            }

            const key = field.key as 'source_types' | 'source_names';

            const options = [
              ...new Set([
                ...draft[key],
                ...sources.map(source =>
                  key === 'source_types'
                    ? source.source_type
                    : source.source_name),
              ]),
            ].sort();

            return (
              <fieldset key={key}>
                <legend>{field.label}</legend>

                <div className="filter-options">
                  {options.map(option => (
                    <label key={option} className="check-option">
                      <input
                        type="checkbox"
                        checked={draft[key].includes(option)}
                        onChange={e => update(
                          key,
                          e.target.checked
                            ? [...draft[key], option]
                            : draft[key].filter(x => x !== option),
                        )}
                      />
                      {option}
                    </label>
                  ))}

                  {!options.length && (
                    <small>No saved sources yet.</small>
                  )}
                </div>
              </fieldset>
            );
          })}
        </div>

        <p className="muted">
          Dates use {Intl.DateTimeFormat().resolvedOptions().timeZone}.
          Selected values within a filter match any; different filters
          match together.
        </p>
      </details>

      {error && (
        <p role="alert" className="form-error">{error}</p>
      )}

      <div className="filter-actions">
        <button className="pill-button" type="submit">
          Apply filters
        </button>

        <button
          className="text-link"
          type="button"
          onClick={() => onApply({ ...emptyState })}
        >
          Clear filters
        </button>

        <span className="muted">
          Search ranks up to 50 matches across your collection.
        </span>
      </div>
    </form>
  );
}
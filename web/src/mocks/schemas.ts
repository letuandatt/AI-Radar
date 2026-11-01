import type { UISchema } from '../api/generated';

/** Stable fixtures matching the public schema endpoints. */
export const schemas: Record<'table' | 'filter' | 'detail', UISchema> = {
  table: {
    version: 1,
    fields: [
      { key: 'title', label: 'Title', renderer: 'text', sortable: false },
      { key: 'source_type', label: 'Source', renderer: 'text', sortable: true },
      { key: 'published_at', label: 'Published', renderer: 'date', sortable: true },
      { key: 'topics', label: 'Topics', renderer: 'tags', sortable: false },
      { key: 'relevance_score', label: 'Relevance', renderer: 'score', sortable: false },
    ],
  },
  filter: {
    version: 1,
    fields: [
      { key: 'source_types', label: 'Sources', renderer: 'multiselect', sortable: false },
      { key: 'source_names', label: 'Source names', renderer: 'multiselect', sortable: false },
      { key: 'topics', label: 'Topics', renderer: 'multiselect', sortable: false },
      { key: 'published_at', label: 'Publication dates', renderer: 'date-range', sortable: false },
    ],
  },
  detail: {
    version: 1,
    fields: [
      { key: 'title', label: 'Title', renderer: 'text', sortable: false },
      { key: 'source_name', label: 'Source', renderer: 'text', sortable: false },
      { key: 'published_at', label: 'Published', renderer: 'date', sortable: false },
      { key: 'fetched_at', label: 'Collected', renderer: 'date', sortable: false },
      { key: 'summary', label: 'Summary', renderer: 'text', sortable: false },
      { key: 'topics', label: 'Topics', renderer: 'tags', sortable: false },
      { key: 'entities', label: 'Entities', renderer: 'tags', sortable: false },
      { key: 'relevance_score', label: 'AI relevance', renderer: 'score', sortable: false },
      { key: 'content_text', label: 'Content', renderer: 'text', sortable: false },
    ],
  },
};
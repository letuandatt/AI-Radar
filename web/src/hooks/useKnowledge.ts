import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';

import {
  filterKnowledge,
  searchKnowledge,
  type BrowseQuery,
} from '../api/generated';

export const PAGE_SIZE = 20;

export type FilterState = {
  q: string;
  source_types: string[];
  source_names: string[];
  topics: string[];
  from: string;
  to: string;
  sort: 'published_at' | 'source_type';
  direction: 'asc' | 'desc';
  page: number;
};

export const emptyState: FilterState = {
  q: '',
  source_types: [],
  source_names: [],
  topics: [],
  from: '',
  to: '',
  sort: 'published_at',
  direction: 'desc',
  page: 1,
};

export type ReadingItem = {
  id: string;
  title: string;
  source_type: string;
  source_name: string;
  published_at?: string | null;
  topics?: string[];
  relevance_score?: number;
  snippet?: string;
};

/** Calendar days follow the browser timezone, including daylight-saving changes. */
export function dateBound(value: string, end = false): string | undefined {
  if (!value) return undefined;

  const [y, m, d] = value.split('-').map(Number);
  const date = new Date(0);

  date.setFullYear(y, m - 1, d);
  date.setHours(0, 0, 0, 0);

  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    y < 1 ||
    y > 9998 ||
    date.getFullYear() !== y ||
    date.getMonth() !== m - 1 ||
    date.getDate() !== d
  ) {
    throw new Error('Choose valid calendar dates.');
  }

  if (end) {
    date.setDate(date.getDate() + 1);
    date.setMilliseconds(-1);
  }

  return end
    ? date.toISOString().replace('.999Z', '.999999Z')
    : date.toISOString();
}

export function validate(state: FilterState): string | undefined {
  if (state.q.trim().length > 1000) {
    return 'Search must be 1,000 characters or fewer.';
  }

  for (const key of ['source_types', 'source_names', 'topics'] as const) {
    if (
      state[key].length > (key === 'source_types' ? 20 : 50) ||
      state[key].some(x => !x.trim() || x.trim().length > 200)
    ) {
      return 'Too many filter values, or a value exceeds 200 characters.';
    }
  }

  try {
    dateBound(state.from);
    dateBound(state.to, true);
  } catch {
    return 'Choose valid calendar dates.';
  }

  if (state.from && state.to && state.from > state.to) {
    return 'Start date must be before end date.';
  }
}

export function readState(params: URLSearchParams): FilterState {
  const page = Number(params.get('page') || 1);

  return {
    q: params.get('q') || '',
    from: params.get('from') || '',
    to: params.get('to') || '',
    source_types: [...new Set(params.getAll('source_types'))],
    source_names: [...new Set(params.getAll('source_names'))],
    topics: [...new Set(params.getAll('topics'))],
    sort: params.get('sort') === 'source_type' ? 'source_type' : 'published_at',
    direction: params.get('direction') === 'asc' ? 'asc' : 'desc',
    page: Number.isInteger(page) && page >= 1 ? Math.min(page, 5001) : 1,
  };
}

export function writeState(state: FilterState): URLSearchParams {
  const params = new URLSearchParams();

  if (state.q.trim()) params.set('q', state.q.trim());

  for (const key of ['source_types', 'source_names', 'topics'] as const) {
    [...new Set(state[key].map(x => x.trim()).filter(Boolean))]
      .forEach(x => params.append(key, x));
  }

  if (state.from) params.set('from', state.from);
  if (state.to) params.set('to', state.to);
  if (state.sort !== emptyState.sort) params.set('sort', state.sort);
  if (state.direction !== emptyState.direction) {
    params.set('direction', state.direction);
  }
  if (state.page > 1) params.set('page', String(state.page));

  return params;
}

/** Cache server data by applied filters. Paging ranked results does not repeat retrieval. */
export function useKnowledge() {
  const [params, setParams] = useSearchParams();
  const state = readState(params);
  const validation = validate(state);

  const filters: BrowseQuery = validation ? {} : {
    source_types: state.source_types,
    source_names: state.source_names,
    topics: state.topics,
    published_after: dateBound(state.from),
    published_before: dateBound(state.to, true),
  };

  const searching = Boolean(state.q.trim());

  const query = useQuery({
    queryKey: [
      'knowledge-browser',
      state.q.trim(),
      filters,
      searching ? null : [state.sort, state.direction, state.page],
    ],
    enabled: !validation,
    retry: false,

    queryFn: async ({ signal }): Promise<{
      items: ReadingItem[];
      total: number;
    }> => {
      if (searching) {
        const result = await searchKnowledge({
          query: state.q.trim(),
          method: 'hybrid',
          top_k: 50,
          filters,
        }, { signal });

        return {
          items: (result.results ?? []).map(item => ({
            id: item.knowledge_id,
            title: item.title,
            source_type: item.source_type ?? '',
            source_name: item.source_name ?? '',
            published_at: item.published_at,
            topics: item.topics,
            snippet: item.content_snippet,
            // Retrieval scores are not editorial relevance percentages.
          })),
          total: result.results?.length ?? 0,
        };
      }

      const result = await filterKnowledge({
        ...filters,
        sort_field: state.sort,
        sort_direction: state.direction,
        limit: PAGE_SIZE,
        offset: (state.page - 1) * PAGE_SIZE,
      }, { signal });

      return {
        items: result.items ?? [],
        total: result.total,
      };
    },
  });

  const items = searching
    ? query.data?.items.slice(
      (state.page - 1) * PAGE_SIZE,
      state.page * PAGE_SIZE,
    )
    : query.data?.items;

  return {
    state,
    params,
    query,
    items: items ?? [],
    searching,
    validation,
    apply: (next: FilterState) => setParams(writeState(next)),
  };
}
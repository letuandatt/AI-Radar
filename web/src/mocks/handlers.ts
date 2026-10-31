import { http, HttpResponse } from 'msw';

import {
  getGetHealthMockHandler,
  getGetReadinessMockHandler,
  getGetStatisticsMockHandler,
  getListKnowledgeMockHandler,
  getFilterKnowledgeMockHandler,
  getGetDigestHistoryMockHandler,
  getGetSourceHealthMockHandler,
} from '../api/generated.msw';

import type { BrowsePage } from '../api/generated';
import { schemas } from './schemas';

const empty: BrowsePage = {
  items: [],
  total: 0,
  page_info: {
    total: 0,
    has_next: false,
    has_prev: false,
  },
};

export const handlers = [
  getGetHealthMockHandler({ status: 'ok' }),
  getGetReadinessMockHandler({ status: 'ready' }),

  getGetStatisticsMockHandler({
    total_items: 0,
    by_source: {},
    by_date_range: {},
    last_updated: null,
  }),

  getListKnowledgeMockHandler(empty),
  getFilterKnowledgeMockHandler(empty),
  getGetDigestHistoryMockHandler([]),
  getGetSourceHealthMockHandler([]),

  http.get('*/api/v1/schema/:kind', ({ params }) => {
    const schema = schemas[String(params.kind) as keyof typeof schemas];

    return schema
      ? HttpResponse.json(schema)
      : HttpResponse.json({ detail: 'Not found' }, { status: 404 });
  }),

  http.post('*/api/v1/retrieval/search', () => HttpResponse.json({
    query: '',
    results: [],
    total_matches: 0,
    method: 'hybrid',
    retrieval_time_ms: 0,
  })),

  http.all('*/api/v1/*', () =>
    HttpResponse.json(
      { detail: 'No mock fixture for this resource' },
      { status: 404 },
    ),
  ),
];
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

const empty: BrowsePage = {
  items: [],
  total: 0,
  page_info: {
    total: 0,
    has_next: false,
    has_prev: false,
  },
};

// Generated handlers plus deliberate stable fixtures.
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
  http.all('*/api/v1/*', () =>
    HttpResponse.json(
      { detail: 'No mock fixture for this resource' },
      { status: 404 },
    ),
  ),
];
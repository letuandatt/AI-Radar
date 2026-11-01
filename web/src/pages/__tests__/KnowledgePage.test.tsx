import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { delay, http, HttpResponse } from 'msw';

import { App } from '../../App';
import { handlers } from '../../mocks/handlers';
import { schemas } from '../../mocks/schemas';
import {
  dateBound,
  emptyState,
  readState,
  validate,
  writeState,
} from '../../hooks/useKnowledge';

const server = setupServer(...handlers);
const clients: QueryClient[] = [];

const item = {
  id: 'one',
  title: 'A useful research story',
  source_type: 'rss',
  source_name: 'Research lab',
  published_at: '2026-01-01T00:00:00Z',
  topics: ['AI'],
  relevance_score: .85,
};

const detail = {
  ...item,
  source_url: 'https://example.org/story',
  fetched_at: item.published_at,
  content_text: '<img src=x onerror=alert(1)>',
  metadata: {
    summary: 'A clear summary',
    topics: ['AI'],
    entities: ['Example lab'],
    relevance_score: .85,
  },
};

const page = (items = [item], total = items.length) => ({
  items,
  total,
  page_info: {
    total,
    has_next: total > items.length,
    has_prev: false,
  },
});

function Location() {
  const location = useLocation();

  return (
    <output aria-label="Current URL">
      {location.pathname}{location.search}
    </output>
  );
}

function open(path = '/knowledge') {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });

  clients.push(client);

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  clients.splice(0).forEach(client => client.clear());
});

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn());

  server.use(
    http.post('*/api/v1/knowledge/search', () =>
      HttpResponse.json(page())),

    http.get('*/api/v1/knowledge/one', () =>
      HttpResponse.json(detail)),

    http.get('*/api/v1/knowledge/one/related', () =>
      HttpResponse.json({ results: [] })),

    http.get('*/api/v1/source-health', () => HttpResponse.json([
      {
        source_type: 'rss',
        source_name: 'Research lab',
        total_items: 1,
      },
      {
        source_type: 'github',
        source_name: 'Open lab',
        total_items: 1,
      },
    ])),
  );
});

describe('Knowledge reading flows', () => {
  it('applies filters, sends dates, and resets pagination', async () => {
    const requests: Record<string, unknown>[] = [];

    server.use(
      http.post('*/api/v1/knowledge/search', async ({ request }) => {
        requests.push(await request.json() as Record<string, unknown>);
        return HttpResponse.json(page());
      }),
    );

    open('/knowledge?page=3');

    await screen.findByText(item.title);
    await userEvent.click(screen.getByText('Refine your reading'));
    await userEvent.click(await screen.findByLabelText('github'));
    await userEvent.click(screen.getByLabelText('Open lab'));
    await userEvent.type(screen.getByLabelText(/Topics/), 'agents, retrieval');
    await userEvent.type(screen.getByLabelText('From'), '2026-01-01');
    await userEvent.type(screen.getByLabelText('Through'), '2026-01-02');

    await userEvent.click(
      screen.getByRole('button', { name: 'Apply filters' }),
    );

    await waitFor(() => expect(requests.at(-1)).toMatchObject({
      source_types: ['github'],
      source_names: ['Open lab'],
      topics: ['agents', 'retrieval'],
      limit: 20,
      offset: 0,
      published_after: dateBound('2026-01-01'),
      published_before: dateBound('2026-01-02', true),
    }));

    expect(screen.getByLabelText('Current URL'))
      .not.toHaveTextContent('page=3');
  });

  it('rejects reversed dates before requesting new data', async () => {
    open();
    await screen.findByText(item.title);

    await userEvent.click(screen.getByText('Refine your reading'));
    await userEvent.type(screen.getByLabelText('From'), '2026-02-01');
    await userEvent.type(screen.getByLabelText('Through'), '2026-01-01');

    await userEvent.click(
      screen.getByRole('button', { name: 'Apply filters' }),
    );

    expect(await screen.findByRole('alert'))
      .toHaveTextContent('Start date must be before end date');

    expect(screen.getByLabelText('Current URL'))
      .toHaveTextContent(/^\/knowledge$/);
  });

  it('renders fields and sortable options from the supported schema', async () => {
    server.use(
      http.get('*/api/v1/schema/table', () => HttpResponse.json({
        version: 1,
        fields: [
          {
            key: 'title',
            label: 'Headline',
            renderer: 'text',
          },
          {
            key: 'source_type',
            label: 'Source kind',
            renderer: 'text',
            sortable: true,
          },
          {
            key: 'content_text',
            label: '<script>',
            renderer: 'html',
          },
        ],
      })),
    );

    open();
    await screen.findByText(item.title);

    expect(screen.queryByText('AI relevance 85%'))
      .not.toBeInTheDocument();

    expect(screen.getByRole('option', {
      name: 'Source kind · ascending',
    })).toBeInTheDocument();

    expect(screen.queryByRole('option', { name: /Published/ }))
      .not.toBeInTheDocument();

    expect(screen.queryByText('<script>')).not.toBeInTheDocument();
  });

  it('sorts and pages through exact browse totals', async () => {
    const bodies: Record<string, unknown>[] = [];

    server.use(
      http.post('*/api/v1/knowledge/search', async ({ request }) => {
        bodies.push(await request.json() as Record<string, unknown>);
        return HttpResponse.json(page([item], 41));
      }),
    );

    open();
    await screen.findByText('41 stories in this view');

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => expect(bodies.at(-1)?.offset).toBe(20));

    await userEvent.selectOptions(
      screen.getByLabelText('Sort stories'),
      'source_type:asc',
    );

    await waitFor(() => expect(bodies.at(-1)).toMatchObject({
      offset: 0,
      sort_field: 'source_type',
      sort_direction: 'asc',
    }));
  });

  it('searches with filters and pages the ranked set without re-querying', async () => {
    const calls: unknown[] = [];

    server.use(
      http.post('*/api/v1/retrieval/search', async ({ request }) => {
        calls.push(await request.json());

        return HttpResponse.json({
          results: Array.from({ length: 25 }, (_, i) => ({
            knowledge_id: String(i),
            title: `Match ${i}`,
            source_type: 'rss',
            source_name: 'Research lab',
            relevance_score: 12.4,
            topics: ['AI'],
          })),
          total_matches: 25,
          method: 'hybrid',
        });
      }),
    );

    open('/knowledge?source_types=rss');
    await screen.findByText(item.title);

    await userEvent.type(
      screen.getByRole('searchbox'),
      'agents{Enter}',
    );

    await screen.findByText('Match 0');

    expect(calls[0]).toMatchObject({
      query: 'agents',
      top_k: 50,
      method: 'hybrid',
      filters: { source_types: ['rss'] },
    });

    expect(screen.getByText(/25 ranked matches returned/))
      .toBeInTheDocument();

    expect(screen.queryByLabelText('Sort stories'))
      .not.toBeInTheDocument();

    expect(screen.queryByText(/AI relevance/))
      .not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await screen.findByText('Match 20');

    expect(screen.queryByText('Match 0')).not.toBeInTheDocument();
    expect(calls).toHaveLength(1);
  });

  it('preserves list URL after opening and returning from an article', async () => {
    open('/knowledge?topics=AI&page=2');

    await userEvent.click(
      await screen.findByRole('link', { name: item.title }),
    );

    await screen.findByText('A clear summary');

    expect(screen.getByRole('link', { name: 'Back to stories' }))
      .toHaveAttribute('href', '/knowledge?topics=AI&page=2');

    await userEvent.click(
      screen.getByRole('link', { name: 'Back to stories' }),
    );

    expect(screen.getByLabelText('Current URL'))
      .toHaveTextContent('/knowledge?topics=AI&page=2');
  });

  it('shows honest empty results with a clear action', async () => {
    server.use(
      http.post('*/api/v1/knowledge/search', () =>
        HttpResponse.json(page([], 0))),
    );

    open('/knowledge?topics=missing');

    await screen.findByText('A little quiet on this frequency.');

    await userEvent.click(
      screen.getByRole('button', { name: 'Clear filters and search' }),
    );

    expect(screen.getByLabelText('Current URL'))
      .toHaveTextContent(/^\/knowledge$/);
  });

  it('shows skeletons while a response is pending', async () => {
    server.use(
      http.post('*/api/v1/knowledge/search', async () => {
        await delay(150);
        return HttpResponse.json(page());
      }),
    );

    open();

    expect(await screen.findByLabelText('Loading stories'))
      .toBeInTheDocument();

    await screen.findByText(item.title);

    expect(screen.queryByLabelText('Loading stories'))
      .not.toBeInTheDocument();
  });

  it('retries an unavailable browse endpoint', async () => {
    server.use(
      http.post('*/api/v1/knowledge/search', () =>
        HttpResponse.json({}, { status: 503 })),
    );

    open();
    await screen.findByText(/temporarily unavailable/);

    server.use(
      http.post('*/api/v1/knowledge/search', () =>
        HttpResponse.json(page())),
    );

    await userEvent.click(
      screen.getByRole('button', { name: 'Try again' }),
    );

    await screen.findByText(item.title);
  });

  it('renders detail metadata as text and rejects hostile source URLs', async () => {
    server.use(
      http.get('*/api/v1/knowledge/one', () => HttpResponse.json({
        ...detail,
        source_url: 'javascript:alert(1)',
        metadata: {
          ...detail.metadata,
          summary: '<script>alert(1)</script>',
        },
      })),
    );

    open('/knowledge/one');

    expect(await screen.findByText('<script>alert(1)</script>'))
      .toBeVisible();

    expect(screen.getByText('<img src=x onerror=alert(1)>'))
      .toBeVisible();

    expect(document.querySelector('img[onerror], script')).toBeNull();

    expect(screen.queryByRole('link', { name: /Original source/ }))
      .not.toBeInTheDocument();

    expect(screen.getByText('Example lab')).toBeVisible();
    expect(screen.getByText('AI relevance 85%')).toBeVisible();
  });

  it('shows missing articles separately and keeps a back link', async () => {
    server.use(
      http.get('*/api/v1/knowledge/one', () =>
        HttpResponse.json({}, { status: 404 })),
    );

    open('/knowledge/one');
    await screen.findByText('Story not found.');

    expect(screen.getByRole('link', { name: 'Back to stories' }))
      .toHaveAttribute('href', '/knowledge');

    expect(screen.queryByRole('button', { name: 'Try again' }))
      .not.toBeInTheDocument();
  });

  it('limits related cards, removes self/duplicates, and does not show rank as relevance', async () => {
    server.use(
      http.get('*/api/v1/knowledge/one/related', () =>
        HttpResponse.json({
          results: ['one', 'two', 'two', 'three', 'four', 'five']
            .map(id => ({
              knowledge_id: id,
              title: `Related ${id}`,
              relevance_score: .99,
            })),
        })),
    );

    open('/knowledge/one');
    await screen.findByText('Related two');

    const related = within(
      screen.getByRole('region', { name: 'Related stories' }),
    );

    expect(related.getAllByRole('link')).toHaveLength(3);
    expect(related.queryByText('Related one')).not.toBeInTheDocument();
    expect(related.queryByText(/AI relevance/)).not.toBeInTheDocument();
  });

  it('keeps article content when related retrieval fails', async () => {
    server.use(
      http.get('*/api/v1/knowledge/one/related', () =>
        HttpResponse.json({}, { status: 503 })),
    );

    open('/knowledge/one');
    await screen.findByText("Related stories couldn't load.");

    expect(screen.getByText('A clear summary')).toBeVisible();

    expect(screen.getByRole('link', { name: /Original source/ }))
      .toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not request data for an invalid query in the URL', async () => {
    let calls = 0;

    server.use(
      http.post('*/api/v1/retrieval/search', () => {
        calls++;
        return HttpResponse.json({ results: [] });
      }),
    );

    open(`/knowledge?q=${'a'.repeat(1001)}`);

    await screen.findByText('Search must be 1,000 characters or fewer.');
    expect(calls).toBe(0);
  });
});

it('round-trips repeated filters and preserves exact end-of-day precision', () => {
  const state = {
    ...emptyState,
    topics: ['AI', 'agents'],
    page: 3,
    from: '2026-01-01',
    to: '2026-01-01',
  };

  expect(readState(writeState(state))).toEqual(state);
  expect(dateBound(state.to, true)).toMatch(/\.999999Z$/);
  expect(() => dateBound('2026-02-30')).toThrow();
  expect(validate({ ...state, q: 'x'.repeat(1001) })).toBeTruthy();
  expect(schemas.filter.fields).toHaveLength(4);
});
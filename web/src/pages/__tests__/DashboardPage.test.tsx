import {
  afterAll,
  afterEach,
  beforeAll,
  expect,
  it,
  vi,
} from 'vitest';
import {
  act,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

import { DashboardPage } from '../DashboardPage';
import { handlers } from '../../mocks/handlers';
import { dateBound } from '../../hooks/useKnowledge';
import { localDay } from '../../hooks/useStatistics';
import { savedDigest } from './readingFixtures';

const server = setupServer(...handlers);
const clients: QueryClient[] = [];

beforeAll(() =>
  server.listen({ onUnhandledFrame: 'error' }),
);

afterAll(() => server.close());

afterEach(() => {
  vi.useRealTimers();
  server.resetHandlers();
  clients.splice(0).forEach(client => client.clear());
});

function open() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  clients.push(client);

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const stats = {
  total_items: 12,
  by_source: {},
  by_date_range: {},
  last_updated: '2026-10-30T12:00:00Z',
};

const page = {
  items: [
    {
      id: 'one',
      title: 'A saved story',
      source_name: 'Lab',
      source_type: 'rss',
    },
  ],
  total: 12,
  page_info: {
    has_next: true,
    has_prev: false,
  },
};

it('shows honest counts, grouped sources, date filters and the saved digest link', async () => {
  const requests: URL[] = [];

  server.use(
    http.get('*/api/v1/statistics', () =>
      HttpResponse.json(stats),
    ),

    http.get('*/api/v1/source-health', () =>
      HttpResponse.json([
        {
          source_type: 'rss',
          source_name: 'A',
          total_items: 4,
        },
        {
          source_type: 'rss',
          source_name: 'B',
          total_items: 3,
        },
        {
          source_type: 'github',
          source_name: 'C',
          total_items: 5,
        },
      ]),
    ),

    http.get('*/api/v1/knowledge', ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);

      return HttpResponse.json(
        url.searchParams.has('published_after')
          ? { ...page, total: 2 }
          : page,
      );
    }),

    http.get('*/api/v1/digest/latest', () =>
      HttpResponse.json(savedDigest()),
    ),
  );

  open();

  expect(
    await screen.findByRole('link', {
      name: /Read this edition/,
    }),
  ).toHaveAttribute('href', '/digest?date=2026-10-30');

  expect(
    await screen.findByRole('link', {
      name: /Saved stories.*12/,
    }),
  ).toHaveAttribute('href', '/knowledge');

  const today = await screen.findByRole('link', {
    name: /Published today.*2/,
  });

  expect(today).toHaveAttribute(
    'href',
    `/knowledge?from=${localDay()}&to=${localDay()}`,
  );

  expect(
    screen.getByRole('link', {
      name: /Sources in collection.*3/,
    }),
  ).toBeVisible();

  expect(screen.getByText('Unavailable')).toBeVisible();

  expect(
    within(
      screen.getByRole('list', {
        name: 'Stories by source type',
      }),
    ).getByRole('link', { name: /rss.*7/ }),
  ).toHaveAttribute('href', '/knowledge?source_types=rss');

  const daily = requests.find(url =>
    url.searchParams.has('published_after'),
  )!;

  expect(
    daily.searchParams.get('published_after'),
  ).toBe(dateBound(localDay()));

  expect(
    daily.searchParams.get('published_before'),
  ).toBe(dateBound(localDay(), true));

  expect(screen.getByText(/Stats checked/)).toBeVisible();
});

it('requests ten recent stories, pages, and resets the page when changing channel', async () => {
  const urls: URL[] = [];

  server.use(
    http.get('*/api/v1/knowledge', ({ request }) => {
      const url = new URL(request.url);

      if (!url.searchParams.has('published_after')) {
        urls.push(url);
      }

      return HttpResponse.json(page);
    }),
  );

  open();

  await screen.findByRole('link', {
    name: 'A saved story',
  });

  expect(urls[0].searchParams.get('limit')).toBe('10');
  expect(urls[0].searchParams.get('sort_field')).toBe(
    'published_at',
  );

  await userEvent.click(
    screen.getByRole('button', { name: /Next/ }),
  );

  await waitFor(() =>
    expect(urls.at(-1)?.searchParams.get('offset')).toBe('10'),
  );

  await userEvent.click(
    screen.getByRole('button', { name: 'Open source' }),
  );

  await waitFor(() =>
    expect(
      urls.at(-1)?.searchParams.getAll('source_types'),
    ).toEqual(['github']),
  );

  expect(urls.at(-1)?.searchParams.get('offset')).toBe('0');
});

it('keeps stories readable during a stats failure and retries the failed widget', async () => {
  let fail = true;

  server.use(
    http.get('*/api/v1/statistics', () =>
      fail
        ? HttpResponse.json({}, { status: 503 })
        : HttpResponse.json(stats),
    ),

    http.get('*/api/v1/knowledge', () =>
      HttpResponse.json(page),
    ),
  );

  open();

  await screen.findByText(
    "Some collection stats couldn't refresh.",
  );

  expect(
    screen.getByRole('link', { name: 'A saved story' }),
  ).toBeVisible();

  fail = false;

  await userEvent.click(
    screen.getByRole('button', { name: 'Try again' }),
  );

  expect(
    await screen.findByRole('link', {
      name: /Saved stories.*12/,
    }),
  ).toBeVisible();
});

it('distinguishes an empty latest digest from an unavailable service', async () => {
  server.use(
    http.get('*/api/v1/digest/latest', () =>
      HttpResponse.json({}, { status: 503 }),
    ),
  );

  open();

  expect(
    await screen.findByText(
      "The latest digest couldn't load.",
    ),
  ).toBeVisible();

  expect(
    screen.queryByText(/Your first edition is still ahead/),
  ).not.toBeInTheDocument();

  server.use(
    http.get('*/api/v1/digest/latest', () =>
      HttpResponse.json({}, { status: 404 }),
    ),
  );

  await userEvent.click(
    screen.getByRole('button', { name: 'Try again' }),
  );

  expect(
    await screen.findByText(
      /Your first edition is still ahead/,
    ),
  ).toBeVisible();
});

it('polls statistics after sixty seconds while mounted', async () => {
  let calls = 0;

  server.use(
    http.get('*/api/v1/statistics', () => {
      calls++;
      return HttpResponse.json(stats);
    }),
  );

  vi.useFakeTimers();
  open();

  await act(async () => {
    await vi.waitFor(() => expect(calls).toBe(1));
  });

  const initial = calls;

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_100);
  });

  await act(async () => {
    await vi.waitFor(() =>
      expect(calls).toBeGreaterThan(initial),
    );
  });
});
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
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

import { App } from '../../App';
import { handlers } from '../../mocks/handlers';
import { useTheme } from '../../theme';

const server = setupServer(...handlers);
const clients: QueryClient[] = [];

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  clients.splice(0).forEach(client => client.clear());
});

function open(path = '/') {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  clients.push(client);

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Editorial reading experience', () => {
  beforeEach(() => {
    vi.stubGlobal('scrollTo', vi.fn());
    localStorage.clear();
    document.documentElement.classList.add('dark');
    useTheme.setState({ theme: 'dark' });
  });

  it('navigates the reading pages and shows an honest empty archive', async () => {
    open();

    expect(
      screen.getByRole('heading', { name: /Technology moves/ }),
    ).toBeVisible();

    await userEvent.click(
      screen.getByRole('link', { name: 'Explore' }),
    );

    expect(
      screen.getByRole('heading', { name: /Follow your/ }),
    ).toBeVisible();

    await userEvent.click(
      screen.getByRole('link', { name: 'Daily digest' }),
    );

    expect(
      await screen.findByText('Your first edition is still ahead.'),
    ).toBeVisible();

    await userEvent.click(
      screen.getByRole('link', { name: /Your space/ }),
    );

    expect(
      screen.getByRole('heading', { name: /Your space/ }),
    ).toBeVisible();
  });

  it('preserves keyboard theme switching', async () => {
    open('/settings');

    screen.getByRole('button', {
      name: 'Switch to light theme',
    }).focus();

    await userEvent.keyboard('{Enter}');

    expect(document.documentElement).not.toHaveClass('dark');
    expect(localStorage.getItem('ai-radar-theme')).toBe('light');
  });

  it('uses actual API stories and sends source filters', async () => {
    const sources: string[][] = [];

    server.use(
      http.get('*/api/v1/knowledge', ({ request }) => {
        sources.push(
          new URL(request.url).searchParams.getAll('source_types'),
        );

        return HttpResponse.json({
          items: [
            {
              id: 'one',
              title: 'A saved story',
              source_type: 'github',
              source_name: 'Example',
              topics: [],
              content_hash: 'hash',
              relevance_score: 0.8,
            },
          ],
          total: 1,
          page_info: {
            has_next: false,
            has_prev: false,
          },
        });
      }),
    );

    open('/knowledge');

    expect(
      await screen.findByRole('link', { name: 'A saved story' }),
    ).toHaveAttribute('href', '/knowledge/one');

    await userEvent.click(
      screen.getByRole('button', { name: 'Open source' }),
    );

    await screen.findByRole('link', { name: 'A saved story' });

    await waitFor(() =>
      expect(sources).toContainEqual(['github']),
    );
  });

  it('renders external content as text and rejects unsafe source links', async () => {
    server.use(
      http.get('*/api/v1/knowledge/one', () =>
        HttpResponse.json({
          id: 'one',
          title: 'A saved story',
          source_type: 'rss',
          source_name: 'Example',
          source_url: 'javascript:alert(1)',
          content_text: '<img src=x onerror=alert(1)>',
          fetched_at: '2026-01-01T00:00:00Z',
          published_at: null,
          metadata: {
            summary: 'Summary',
            topics: [],
            entities: [],
            relevance_score: 0.8,
          },
        }),
      ),
    );

    open('/knowledge/one');

    expect(
      await screen.findByText('<img src=x onerror=alert(1)>'),
    ).toBeVisible();

    expect(screen.queryByRole('img')).not.toBeInTheDocument();

    expect(
      screen.queryByRole('link', { name: /Original source/ }),
    ).not.toBeInTheDocument();
  });

  it('handles unknown routes', () => {
    open('/missing');

    expect(
      screen.getByRole('heading', {
        name: 'This page is off the radar.',
      }),
    ).toBeVisible();
  });
});
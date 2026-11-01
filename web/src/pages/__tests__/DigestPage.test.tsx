import {
  afterAll,
  afterEach,
  beforeAll,
  expect,
  it,
} from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  MemoryRouter,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { delay, http, HttpResponse } from 'msw';

import { DigestPage } from '../DigestPage';
import { handlers } from '../../mocks/handlers';
import { savedDigest } from './readingFixtures';
import {
  editionLabel,
  validEdition,
} from '../../hooks/useDigest';

const server = setupServer(...handlers);
const clients: QueryClient[] = [];

beforeAll(() =>
  server.listen({ onUnhandledFrame: 'error' }),
);

afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  clients.splice(0).forEach(client => client.clear());
});

function Location() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <>
      <output aria-label="Current URL">
        {location.search}
      </output>

      <button onClick={() => navigate(-1)}>
        Browser back
      </button>
    </>
  );
}

function open(path = '/digest') {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  clients.push(client);

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <DigestPage />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function archive() {
  server.use(
    http.get('*/api/v1/digest/history', () =>
      HttpResponse.json([
        '2026-10-28',
        '2026-10-30',
        '2026-10-28',
      ]),
    ),

    http.get('*/api/v1/digest', ({ request }) =>
      HttpResponse.json(
        savedDigest(
          new URL(request.url).searchParams.get('date')!,
        ),
      ),
    ),
  );
}

it('opens the newest saved edition and navigates saved dates, skipping gaps', async () => {
  archive();
  open();

  expect(
    await screen.findByRole('heading', {
      name: 'October 30, 2026',
    }),
  ).toBeVisible();

  expect(
    screen.getByRole('button', { name: /Newer edition/ }),
  ).toBeDisabled();

  await userEvent.click(
    screen.getByRole('button', { name: /Older edition/ }),
  );

  expect(
    await screen.findByRole('heading', {
      name: 'October 28, 2026',
    }),
  ).toBeVisible();

  expect(screen.getByLabelText('Current URL')).toHaveTextContent(
    '?date=2026-10-28',
  );

  expect(
    screen.getByRole('button', { name: /Older edition/ }),
  ).toBeDisabled();

  await userEvent.click(
    screen.getByRole('button', { name: 'Browser back' }),
  );

  expect(
    await screen.findByRole('heading', {
      name: 'October 30, 2026',
    }),
  ).toBeVisible();
});

it('can load a direct date outside the history window and gives a clear missing-date state', async () => {
  archive();

  server.use(
    http.get('*/api/v1/digest', () =>
      HttpResponse.json({}, { status: 404 }),
    ),
  );

  open('/digest?date=2025-01-01');

  expect(
    await screen.findByText(
      'No saved edition for this date.',
    ),
  ).toBeVisible();

  expect(
    screen.getByLabelText('Edition date (UTC)'),
  ).toHaveValue('2025-01-01');

  fireEvent.change(
    screen.getByLabelText('Edition date (UTC)'),
    { target: { value: '2026-10-29' } },
  );

  await waitFor(() =>
    expect(
      screen.getByLabelText('Current URL'),
    ).toHaveTextContent('date=2026-10-29'),
  );
});

it('rejects impossible URL dates before querying the digest', async () => {
  let calls = 0;

  server.use(
    http.get('*/api/v1/digest', () => {
      calls++;
      return HttpResponse.json(savedDigest());
    }),
  );

  open('/digest?date=2026-02-30');

  expect(
    await screen.findByText(
      'Choose a valid edition date.',
    ),
  ).toBeVisible();

  expect(calls).toBe(0);
  expect(validEdition('2024-02-29')).toBe(true);
  expect(validEdition('0000-01-01')).toBe(false);
  expect(editionLabel('2026-10-30')).toBe('October 30, 2026');
});

it('handles an empty archive and a failed history request separately', async () => {
  open();

  expect(
    await screen.findByText(
      'Your first edition is still ahead.',
    ),
  ).toBeVisible();
});

it('still reads a directly selected digest if its history request fails', async () => {
  archive();

  server.use(
    http.get('*/api/v1/digest/history', () =>
      HttpResponse.json({}, { status: 503 }),
    ),
  );

  open('/digest?date=2026-10-30');

  expect(
    await screen.findByText("The archive couldn't load."),
  ).toBeVisible();

  expect(
    await screen.findByRole('heading', {
      name: 'October 30, 2026',
    }),
  ).toBeVisible();
});

it('shows loading and retries a digest service failure', async () => {
  archive();

  let fail = true;

  server.use(
    http.get('*/api/v1/digest', async () => {
      await delay(80);

      return fail
        ? HttpResponse.json({}, { status: 503 })
        : HttpResponse.json(savedDigest());
    }),
  );

  open('/digest?date=2026-10-30');

  expect(
    screen.getByRole('status', { name: 'Loading digest' }),
  ).toBeVisible();

  expect(
    await screen.findByText("This edition couldn't load."),
  ).toBeVisible();

  fail = false;

  await userEvent.click(
    screen.getByRole('button', { name: 'Try again' }),
  );

  expect(
    await screen.findByRole('article', {
      name: 'Saved digest',
    }),
  ).toBeVisible();
});

it('renders Markdown while blocking HTML, media and unsafe URLs', async () => {
  const content =
    '**Strong text**\n\n- Useful item\n\n' +
    '<script>alert(1)</script>\n\n' +
    '<img src=x onerror=alert(1)>\n\n' +
    '![tracker](https://evil.example/pixel)\n\n' +
    '[Unsafe](javascript:alert%281%29) ' +
    '[Private](http://user:pass@example.com) ' +
    '[Relative](/api/v1/digest) ' +
    '[Good](https://example.org/report)';

  server.use(
    http.get('*/api/v1/digest', () =>
      HttpResponse.json(
        savedDigest('2026-10-30', content),
      ),
    ),
  );

  open('/digest?date=2026-10-30');

  expect(
    await screen.findByText('Strong text'),
  ).toHaveProperty('tagName', 'STRONG');

  expect(
    screen.getByText('Useful item'),
  ).toHaveProperty('tagName', 'LI');

  expect(
    document.querySelector('script, img, iframe'),
  ).toBeNull();

  for (const name of ['Unsafe', 'Private', 'Relative']) {
    expect(
      screen.queryByRole('link', { name }),
    ).toBeNull();
  }

  expect(
    screen.getByRole('link', { name: 'Good' }),
  ).toHaveAttribute('rel', 'noopener noreferrer');

  expect(
    screen.getByRole('link', {
      name: /An interesting discovery/,
    }),
  ).toHaveAttribute('href', '/knowledge/story-one');
});

it('does not let a slow previous edition replace the newly selected date', async () => {
  archive();

  server.use(
    http.get('*/api/v1/digest', async ({ request }) => {
      const day = new URL(request.url).searchParams.get('date')!;

      if (day === '2026-10-30') {
        await delay(180);
      }

      return HttpResponse.json(savedDigest(day));
    }),
  );

  open('/digest?date=2026-10-30');

  fireEvent.change(
    screen.getByLabelText('Edition date (UTC)'),
    { target: { value: '2026-10-28' } },
  );

  await screen.findByRole('heading', {
    name: 'October 28, 2026',
  });

  await new Promise(resolve => setTimeout(resolve, 220));

  expect(
    screen.queryByRole('heading', {
      name: 'October 30, 2026',
    }),
  ).toBeNull();
});
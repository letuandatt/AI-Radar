import { afterAll, afterEach, beforeAll, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { delay, http, HttpResponse } from 'msw';
import { FeedbackButtons } from '../knowledge/FeedbackButtons';

const server = setupServer();
const clients: QueryClient[] = [];
const neutral = { knowledge_id: 'one', rating: null, updated_at: null, base_score: .5, adjusted_score: .5 };
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterAll(() => server.close());
afterEach(() => { server.resetHandlers(); clients.splice(0).forEach(client => client.clear()); });

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><FeedbackButtons knowledgeId="one" /></QueryClientProvider>);
}

it('loads persisted feedback without issuing a write', async () => {
  server.use(http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json({ ...neutral, rating: 'useful', adjusted_score: .6 })));
  open();
  await waitFor(() => expect(screen.getByRole('button', { name: /^Useful$/ })).toHaveAttribute('aria-pressed', 'true'));
  expect(screen.getByRole('status')).toHaveTextContent('0.60 / 1.00');
});

it('sets, replaces and clears an absolute choice', async () => {
  const requests: unknown[] = [];
  server.use(
    http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json(neutral)),
    http.put('*/api/v1/knowledge/one/feedback', async ({ request }) => {
      const body = await request.json() as { rating: string | null }; requests.push(body);
      return HttpResponse.json({ ...neutral, rating: body.rating });
    }),
  );
  open();
  const useful = screen.getByRole('button', { name: /^Useful$/ });
  await waitFor(() => expect(useful).toBeEnabled());
  await userEvent.click(useful);
  await waitFor(() => expect(useful).toHaveAttribute('aria-pressed', 'true'));
  await userEvent.click(screen.getByRole('button', { name: 'Not useful' }));
  await waitFor(() => expect(useful).toHaveAttribute('aria-pressed', 'false'));
  await userEvent.click(screen.getByRole('button', { name: 'Clear choice' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Clear choice' })).toBeNull());
  expect(requests).toEqual([{ rating: 'useful' }, { rating: 'not_useful' }, { rating: null }]);
});

it('disables duplicate writes while saving', async () => {
  let calls = 0;
  server.use(
    http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json(neutral)),
    http.put('*/api/v1/knowledge/one/feedback', async () => {
      calls++; await delay(100); return HttpResponse.json({ ...neutral, rating: 'useful' });
    }),
  );
  open();
  const button = screen.getByRole('button', { name: /^Useful$/ });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.dblClick(button);
  expect(screen.getByRole('button', { name: 'Not useful' })).toBeDisabled();
  await waitFor(() => expect(button).toBeEnabled());
  expect(calls).toBe(1);
});

it('preserves confirmed choice on failure, hides upstream errors and allows a read retry', async () => {
  let calls = 0;
  server.use(
    http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json({ ...neutral, rating: 'useful' })),
    http.put('*/api/v1/knowledge/one/feedback', () => { calls++; return HttpResponse.json({ detail: 'private token' }, { status: 503 }); }),
  );
  open();
  const useful = screen.getByRole('button', { name: /^Useful$/ });
  await waitFor(() => expect(useful).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: 'Not useful' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed');
  expect(useful).toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByText(/private token/)).toBeNull();
  expect(calls).toBe(1);
  await userEvent.click(screen.getByRole('button', { name: 'Reload choice' }));
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

it('blocks writes when the initial read fails', async () => {
  server.use(http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json({}, { status: 401 })));
  open();
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign in');
  expect(screen.getByRole('button', { name: /^Useful$/ })).toBeDisabled();
});

it('explains an unscored article without inventing a score', async () => {
  server.use(http.get('*/api/v1/knowledge/one/feedback', () => HttpResponse.json({ ...neutral, base_score: null, adjusted_score: null })));
  open();
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('when this article is scored'));
  expect(screen.queryByText(/Importance:/)).toBeNull();
});
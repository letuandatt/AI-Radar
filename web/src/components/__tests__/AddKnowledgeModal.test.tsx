import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import { delay, http, HttpResponse } from 'msw';
import { AddKnowledgeModal } from '../knowledge/AddKnowledgeModal';
import { KnowledgePage } from '../../pages/KnowledgePage';
import { handlers } from '../../mocks/handlers';

const server = setupServer(...handlers);
const clients: QueryClient[] = [];
const saved = { knowledge_id: 'saved-id', status: 'created', indexing: 'ready', analysis: 'ready', importance: 'ready', content_truncated: false };
beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterAll(() => server.close());
afterEach(() => { server.resetHandlers(); clients.splice(0).forEach(client => client.clear()); });
function open(page = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  const onClose = vi.fn();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><MemoryRouter>
    {page ? <KnowledgePage /> : <AddKnowledgeModal onClose={onClose} />}
  </MemoryRouter></QueryClientProvider>);
  return { onClose, invalidate };
}
async function fill() {
  await userEvent.type(screen.getByLabelText('Article URL'), 'https://example.org/article');
}

it('opens from Explore and restores focus when cancelled', async () => {
  open(true);
  const button = screen.getByRole('button', { name: 'Add a story +' });
  await userEvent.click(button);
  expect(screen.getByRole('dialog')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(button).toHaveFocus();
});

it('submits once, reports a saved ID and invalidates collection caches', async () => {
  const bodies: unknown[] = [];
  server.use(http.post('*/api/v1/knowledge', async ({ request }) => {
    bodies.push(await request.json()); await delay(80); return HttpResponse.json(saved);
  }));
  const { invalidate } = open(); await fill();
  await userEvent.type(screen.getByLabelText(/Title/), 'A useful article');
  await userEvent.dblClick(screen.getByRole('button', { name: 'Save and analyze' }));
  expect(await screen.findByText('Saved to your collection.')).toBeVisible();
  expect(bodies).toEqual([{ url: 'https://example.org/article', title: 'A useful article' }]);
  expect(screen.getByRole('link', { name: /Read saved story/ })).toHaveAttribute('href', '/knowledge/saved-id');
  expect(invalidate).toHaveBeenCalledOnce();
});

it('blocks unsafe URLs before calling the backend', async () => {
  let calls = 0;
  server.use(http.post('*/api/v1/knowledge', () => { calls++; return HttpResponse.json(saved); }));
  open();
  fireEvent.change(screen.getByLabelText('Article URL'), { target: { value: 'https://user:pass@example.org' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save and analyze' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('without embedded credentials');
  expect(calls).toBe(0);
});

it('keeps input after an error and never retries the write automatically', async () => {
  let calls = 0;
  server.use(http.post('*/api/v1/knowledge', () => { calls++; return HttpResponse.json({ detail: 'private upstream secret' }, { status: 503 }); }));
  open(); await fill();
  await userEvent.click(screen.getByRole('button', { name: 'Save and analyze' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('providers are unavailable');
  expect(screen.getByLabelText('Article URL')).toHaveValue('https://example.org/article');
  expect(screen.queryByText(/private upstream secret/)).toBeNull();
  expect(calls).toBe(1);
});

it('shows partial outcomes without treating the saved article as a failed write', async () => {
  server.use(http.post('*/api/v1/knowledge', () => HttpResponse.json({ ...saved, indexing: 'partial', analysis: 'failed', importance: 'skipped', content_truncated: true })));
  open(); await fill();
  await userEvent.click(screen.getByRole('button', { name: 'Save and analyze' }));
  expect(await screen.findByText('Saved to your collection.')).toBeVisible();
  expect(screen.getByText(/Search indexes are incomplete/)).toBeVisible();
  expect(screen.getByText(/first 10,000/)).toBeVisible();
  expect(screen.getByText(/waiting for content analysis/)).toBeVisible();
});

it('explains existing records and keeps the dialog open while work is pending', async () => {
  server.use(http.post('*/api/v1/knowledge', async () => {
    await delay(100); return HttpResponse.json({ ...saved, status: 'existing', indexing: 'unchanged', analysis: 'unchanged', importance: 'unchanged' });
  }));
  const { onClose } = open(); await fill();
  await userEvent.click(screen.getByRole('button', { name: 'Save and analyze' }));
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: true, cancelable: true }));
  expect(onClose).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByText('Already in your collection.')).toBeVisible());
});

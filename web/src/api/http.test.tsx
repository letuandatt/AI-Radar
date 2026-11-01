import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  it,
  expect,
} from 'vitest';

import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { apiFetch } from './http';
import { useGetStatistics } from './generated';
import { handlers } from '../mocks/handlers';

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Generated client boundary', () => {
  it('loads a stable fixture through the real generated hook', async () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        {children}
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useGetStatistics(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_items).toBe(0);

    client.clear();
  });

  it('rejects external URLs before fetching', async () => {
    await expect(
      apiFetch('https://example.org/secret'),
    ).rejects.toThrow('Unsupported API path');
  });

  it('does not propagate error response contents', async () => {
    server.use(
      http.get('*/api/v1/statistics', () =>
        HttpResponse.json(
          { secret: 'sentinel' },
          { status: 500 },
        ),
      ),
    );

    await expect(
      apiFetch('/api/v1/statistics'),
    ).rejects.toThrow('Request failed (500)');
  });
});
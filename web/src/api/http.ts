export class ApiError extends Error {
  constructor(public status: number) {
    super(`Request failed (${status})`);
  }
}

/** Same-origin only. No provider keys, tokens or backend configuration. */
export async function apiFetch<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  if (!url.startsWith('/api/v1/')) {
    throw new Error('Unsupported API path');
  }

  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...options?.headers,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status);
  }

  return await response.json() as T;
}
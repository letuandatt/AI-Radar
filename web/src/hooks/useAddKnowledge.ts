import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addKnowledge, type ManualAddRequest } from '../api/generated';

/** A write is never retried automatically: a lost response may follow a committed save. */
export function useAddKnowledge() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ManualAddRequest) => addKnowledge(body),
    retry: false,
    onSuccess: () => { void client.invalidateQueries(); },
  });
}

export function addErrorText(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 401) return 'Sign in through the local API, then try again.';
  if (status === 403) return 'This browser origin is not allowed to add stories.';
  if (status === 409) return 'Another add may be running, or this URL belongs to an item in trash. Check your collection before retrying.';
  if (status === 413) return 'The request is too large.';
  if (status === 422) return 'Use a public HTML or text URL. Private addresses, unsupported pages and oversized responses are blocked.';
  if (status === 503) return 'Manual add or its providers are unavailable. Check the API terminal and your collection before retrying.';
  return 'The result could not be confirmed. Check your collection before trying again; the article may already be saved.';
}
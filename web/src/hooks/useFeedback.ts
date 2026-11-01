import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getGetFeedbackQueryKey,
  getGetFeedbackPreferencesQueryKey,
  setFeedback,
  useGetFeedback,
  type FeedbackRequest,
} from '../api/generated';

export function useFeedback(knowledgeId: string) {
  const id = encodeURIComponent(knowledgeId);
  const client = useQueryClient();
  const key = getGetFeedbackQueryKey(id);
  const query = useGetFeedback(id, { query: { retry: false } });
  const mutation = useMutation({
    mutationFn: (rating: FeedbackRequest['rating']) => setFeedback(id, { rating }),
    retry: false,
    onMutate: () => client.cancelQueries({ queryKey: key }),
    onSuccess: data => {
      client.setQueryData(key, data);
      void client.invalidateQueries({ queryKey: getGetFeedbackPreferencesQueryKey() });
    },
  });
  return { query, mutation };
}

export function feedbackError(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 401) return 'Sign in through the local API to save your feedback.';
  if (status === 403) return 'This browser origin is not allowed to save feedback.';
  if (status === 404) return 'This article is no longer available.';
  return 'Feedback could not be confirmed. Reload your choice before trying again.';
}
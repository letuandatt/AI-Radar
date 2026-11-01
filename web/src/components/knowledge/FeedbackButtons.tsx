import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { feedbackError, useFeedback } from '../../hooks/useFeedback';
import './feedback.css';

export function FeedbackButtons({ knowledgeId }: { knowledgeId: string }) {
  const { query, mutation } = useFeedback(knowledgeId);
  const data = query.data;
  const disabled = mutation.isPending || query.isPending || query.isError || !data;

  return <section className="story-feedback" aria-label="Article feedback" aria-busy={mutation.isPending}>
    <span className="tiny-label">YOUR READING SIGNAL</span>
    <h2>Was this worth your time?</h2>
    <p className="muted">Your choice adjusts this story’s importance. It does not change saved editions.</p>
    <div className="feedback-actions" role="group" aria-label="Rate this story">
      <button type="button" className="pill-button" disabled={disabled}
        aria-pressed={data?.rating === 'useful'} onClick={() => mutation.mutate('useful')}>
        <ThumbsUp size={16} aria-hidden="true" /> Useful
      </button>
      <button type="button" className="pill-button" disabled={disabled}
        aria-pressed={data?.rating === 'not_useful'} onClick={() => mutation.mutate('not_useful')}>
        <ThumbsDown size={16} aria-hidden="true" /> Not useful
      </button>
      {data?.rating && <button type="button" className="text-link" disabled={disabled}
        onClick={() => mutation.mutate(null)}>Clear choice</button>}
    </div>
    {query.isPending ? <p role="status">Loading your choice…</p>
      : mutation.isPending ? <p role="status">Saving your choice…</p>
      : data && <p role="status" className="muted">
        {data.rating === 'useful' ? 'Marked useful.' : data.rating === 'not_useful' ? 'Marked not useful.' : 'No feedback yet.'}
        {data.adjusted_score != null
          ? ` Importance: ${data.adjusted_score.toFixed(2)} / 1.00.`
          : ' Your choice will apply when this article is scored.'}
      </p>}
    {(query.isError || mutation.isError) && <div className="feedback-error" role="alert">
      <p>{feedbackError(mutation.error ?? query.error)}</p>
      <button type="button" className="text-link" disabled={query.isFetching || mutation.isPending}
        onClick={() => { mutation.reset(); void query.refetch(); }}>Reload choice</button>
    </div>}
  </section>;
}
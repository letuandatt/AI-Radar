import type { ReactNode } from 'react';
import { Orbit, RefreshCw } from 'lucide-react';

export const dateLabel = (value?: string | null) => {
  if (!value || Number.isNaN(Date.parse(value))) {
    return 'Undated';
  }

  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value));
};

export const storyUrl = (id: string) =>
  `/knowledge/${encodeURIComponent(id)}`;

export function safeUrl(value?: string | null) {
  try {
    const url = new URL(value ?? '');

    return (
      ['https:', 'http:'].includes(url.protocol) &&
      !url.username &&
      !url.password
    ) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function Cover({
  variant = 0,
  large = false,
}: {
  variant?: number;
  large?: boolean;
}) {
  return (
    <div
      className={`story-cover cover-${variant % 3} ${
        large ? 'cover-large' : ''
      }`}
      aria-hidden="true"
    >
      <div className="cover-grid" />
      <div className="orbital orbital-one" />
      <div className="orbital orbital-two" />
      <div className="orbital orbital-three" />

      <div className="cover-core">
        <Orbit size={large ? 92 : 58} strokeWidth={0.7} />
      </div>

      <span className="cover-word">
        {[
          'INTELLIGENCE',
          'OPEN SYSTEMS',
          'NEXT HORIZON',
        ][variant % 3]}
      </span>

      <span className="cover-index">
        RADAR / 0{variant % 3 + 1}
      </span>
    </div>
  );
}

export function Message({
  title,
  children,
  retry,
}: {
  title: string;
  children: ReactNode;
  retry?: () => void;
}) {
  return (
    <section
      className="empty-state"
      role={retry ? 'alert' : 'status'}
    >
      <Orbit size={36} />
      <h2>{title}</h2>
      <p>{children}</p>

      {retry && (
        <button className="pill-button" onClick={retry}>
          <RefreshCw size={16} />
          Try again
        </button>
      )}
    </section>
  );
}

export function Loading({ detail = false }: { detail?: boolean }) {
  return (
    <div
      className={detail ? 'detail-skeleton' : 'skeleton-grid'}
      role="status"
      aria-label={detail ? 'Loading article' : 'Loading stories'}
    >
      {Array.from({ length: detail ? 3 : 5 }, (_, i) => (
        <div key={i} className="skeleton-card" aria-hidden="true" />
      ))}
    </div>
  );
}

export function errorText(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;

  if (status === 401) {
    return 'Please sign in through the local API, then try again.';
  }
  if (status === 404) {
    return 'This story may have been removed or the link is incorrect.';
  }
  if (status === 400 || status === 422) {
    return 'Please check your search and filter values.';
  }
  if (status === 503) {
    return 'The reading service is temporarily unavailable. Please try again.';
  }

  return 'We could not reach the reading service. Check your connection and try again.';
}
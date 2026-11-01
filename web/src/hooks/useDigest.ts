import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  getDigest,
  getDigestHistory,
  getLatestDigest,
} from '../api/generated';

export const statusOf = (error: unknown) =>
  (error as { status?: number } | null)?.status;

/** Digest dates are UTC edition labels, not timestamps in the browser timezone. */
export function validEdition(value: string): boolean {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    value.startsWith('0000')
  ) {
    return false;
  }

  const date = new Date(`${value}T00:00:00Z`);

  return (
    !Number.isNaN(date.getTime()) &&
    date.toISOString().slice(0, 10) === value
  );
}

export function editionLabel(value: string): string {
  return validEdition(value)
    ? new Intl.DateTimeFormat('en', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(new Date(`${value}T00:00:00Z`))
    : value;
}

export function useLatestDigest() {
  return useQuery({
    queryKey: ['reading-latest-digest'],
    retry: false,
    staleTime: 60_000,
    refetchInterval: 60_000,
    queryFn: ({ signal }) => getLatestDigest({ signal }),
  });
}

/** Read saved editions only. Direct links may address dates outside the latest 30. */
export function useDigest() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('date') ?? '';

  const history = useQuery({
    queryKey: ['reading-digest-history'],
    retry: false,
    staleTime: 60_000,
    queryFn: ({ signal }) =>
      getDigestHistory({ limit: 30 }, { signal }),
  });

  const dates = [...new Set(history.data ?? [])]
    .filter(validEdition)
    .sort()
    .reverse();

  const date = requested || dates[0] || '';
  const invalid = Boolean(requested && !validEdition(requested));

  const digest = useQuery({
    queryKey: ['reading-digest', date],
    retry: false,
    enabled: Boolean(date) && !invalid,
    staleTime: 60_000,
    queryFn: ({ signal }) => getDigest({ date }, { signal }),
  });

  const select = (value: string) =>
    setParams(current => {
      const next = new URLSearchParams(current);

      if (value) {
        next.set('date', value);
      } else {
        next.delete('date');
      }

      return next;
    });

  return {
    history,
    digest,
    dates,
    date,
    invalid,
    select,
    older: dates.find(day => day < date),
    newer: dates.filter(day => day > date).at(-1),
  };
}
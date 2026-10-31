import { useQuery } from '@tanstack/react-query';
import {
  getSourceHealth,
  getStatistics,
  listKnowledge,
} from '../api/generated';
import { dateBound } from './useKnowledge';

export const REFRESH_MS = 60_000;

/** Matches the calendar-day filters used by Explore, including DST boundaries. */
export function localDay(now = new Date()): string {
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('-');
}

/** Read-only repository counts; source presence does not imply pipeline health. */
export function useStatistics() {
  const options = {
    retry: false,
    refetchInterval: REFRESH_MS,
    staleTime: REFRESH_MS,
  };

  const statistics = useQuery({
    ...options,
    queryKey: ['reading-statistics'],
    queryFn: ({ signal }) => getStatistics({ signal }),
  });

  const sources = useQuery({
    ...options,
    queryKey: ['reading-sources'],
    queryFn: ({ signal }) => getSourceHealth({ signal }),
  });

  const today = useQuery({
    ...options,
    queryKey: ['reading-today'],
    queryFn: async ({ signal }) => {
      const day = localDay();

      const page = await listKnowledge(
        {
          limit: 1,
          published_after: dateBound(day),
          published_before: dateBound(day, true),
        },
        { signal },
      );

      return { day, total: page.total };
    },
  });

  return { statistics, sources, today };
}
import { Link } from 'react-router-dom';
import { useStatistics } from '../../hooks/useStatistics';
import {
  useLatestDigest,
  editionLabel,
  statusOf,
} from '../../hooks/useDigest';
import { Message, errorText } from '../shared/Reading';
import { DigestMarkdown } from '../digest/DigestViewer';

export function ReadingOverview() {
  const { statistics, sources, today } = useStatistics();

  const counts = new Map<string, number>();

  for (const source of sources.data ?? []) {
    counts.set(
      source.source_type,
      (counts.get(source.source_type) ?? 0) + source.total_items,
    );
  }

  const groups = [...counts].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );

  const max = Math.max(1, ...counts.values());

  const errors = [statistics, sources, today].filter(
    query => query.isError,
  );

  const refreshed = statistics.dataUpdatedAt;

  return (
    <section
      className="reading-overview"
      aria-label="Collection overview"
    >
      <div className="overview-heading">
        <span className="tiny-label">
          YOUR COLLECTION, AT A GLANCE
        </span>

        <span className="muted">
          {refreshed ? (
            <>
              Stats checked{' '}
              <time dateTime={new Date(refreshed).toISOString()}>
                {new Date(refreshed).toLocaleTimeString()}
              </time>
            </>
          ) : statistics.isError ? (
            'Stats unavailable'
          ) : (
            'Checking collection…'
          )}
        </span>
      </div>

      <div className="reading-stats">
        <Link className="reading-stat" to="/knowledge">
          <span>Saved stories</span>
          <strong>
            {statistics.data?.total_items.toLocaleString() ?? '—'}
          </strong>
          <small>Browse the full collection ↗</small>
        </Link>

        <Link
          className="reading-stat"
          to={
            today.data
              ? `/knowledge?from=${today.data.day}&to=${today.data.day}`
              : '/knowledge'
          }
        >
          <span>Published today</span>
          <strong>
            {today.data?.total.toLocaleString() ?? '—'}
          </strong>
          <small>Saved stories · your local date ↗</small>
        </Link>

        <a
          className="reading-stat"
          href="#source-distribution"
        >
          <span>Sources in collection</span>
          <strong>
            {sources.data?.length.toLocaleString() ?? '—'}
          </strong>
          <small>Sources with saved stories ↓</small>
        </a>

        <div className="reading-stat">
          <span>Failed items</span>
          <strong className="unavailable-count">
            Unavailable
          </strong>
          <small>Processing metrics are not connected.</small>
        </div>
      </div>

      {errors.length > 0 && (
        <Message
          title="Some collection stats couldn't refresh."
          retry={() => {
            errors.forEach(query => void query.refetch());
          }}
        >
          Previously loaded values may be out of date.{' '}
          {errorText(errors[0].error)}
        </Message>
      )}

      <div
        className="source-distribution"
        id="source-distribution"
      >
        <div>
          <h2>Where the stories come from</h2>
          <p className="muted">
            Saved stories by source type. Counts do not indicate
            source uptime.
          </p>

          {statistics.data?.last_updated && (
            <p className="muted">
              Last story update:{' '}
              <time dateTime={statistics.data.last_updated}>
                {new Date(
                  statistics.data.last_updated,
                ).toLocaleString()}
              </time>
            </p>
          )}
        </div>

        {sources.isPending ? (
          <p role="status">Loading source counts…</p>
        ) : groups.length ? (
          <ul
            className="source-bars"
            aria-label="Stories by source type"
          >
            {groups.map(([type, count]) => (
              <li key={type}>
                <Link
                  to={`/knowledge?source_types=${encodeURIComponent(type)}`}
                >
                  <span>{type}</span>
                  <strong>{count.toLocaleString()}</strong>

                  <span
                    className="source-track"
                    aria-hidden="true"
                  >
                    <span
                      style={{ width: `${count / max * 100}%` }}
                    />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          !sources.isError && (
            <p className="muted">No saved sources yet.</p>
          )
        )}
      </div>
    </section>
  );
}

export function LatestDigestCard() {
  const digest = useLatestDigest();

  if (digest.isPending) {
    return (
      <section className="digest-banner" role="status">
        <p>Finding your latest edition…</p>
      </section>
    );
  }

  if (digest.isError && statusOf(digest.error) !== 404) {
    return (
      <Message
        title="The latest digest couldn't load."
        retry={() => void digest.refetch()}
      >
        {errorText(digest.error)}
      </Message>
    );
  }

  const saved = digest.isError ? undefined : digest.data;

  return (
    <section
      className="digest-banner"
      aria-label="Latest digest"
    >
      <div>
        <span className="eyebrow">
          {saved
            ? `THE DAILY EDITION · ${editionLabel(saved.digest_date)}`
            : 'THE DAILY EDITION'}
        </span>

        <h2>
          Less scrolling.
          <br />
          <em>More understanding.</em>
        </h2>

        {saved ? (
          <div className="digest-preview">
            <DigestMarkdown
              content={
                saved.intelligence.sections.find(
                  section =>
                    section.section_type === 'executive_summary',
                )?.content ||
                `${saved.total_items} curated stories in your latest saved briefing.`
              }
            />
          </div>
        ) : (
          <p>
            Your first edition is still ahead. Saved briefings
            will appear here.
          </p>
        )}

        {saved && <p>{saved.total_items} curated stories</p>}

        <Link
          className="pill-button primary-button"
          to={
            saved
              ? `/digest?date=${saved.digest_date}`
              : '/digest'
          }
        >
          {saved ? 'Read this edition' : 'Open the archive'} →
        </Link>
      </div>

      <div className="digest-mark" aria-hidden="true">
        R<span>↗</span>
      </div>
    </section>
  );
}

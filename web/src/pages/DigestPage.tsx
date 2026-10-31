import { useDigest, statusOf } from '../hooks/useDigest';
import { DigestViewer } from '../components/digest/DigestViewer';
import { Message, errorText } from '../components/shared/Reading';

import './digest.css';

export function DigestPage() {
  const {
    history,
    digest,
    dates,
    date,
    invalid,
    select,
    older,
    newer,
  } = useDigest();

  return (
    <section className="reading-page digest-page">
      <span className="eyebrow">
        A MOMENT TO SEE THE BIGGER PICTURE
      </span>

      <h1>
        The daily
        <br />
        <em>perspective.</em>
      </h1>

      <p className="intro-copy">
        Your saved intelligence briefings. Read at your own pace.
      </p>

      <div className="archive-controls">
        <label className="date-picker">
          Edition date (UTC)
          <input
            type="date"
            value={invalid ? '' : date}
            onChange={event => select(event.target.value)}
          />
        </label>

        <button
          className="pill-button"
          onClick={() => select('')}
        >
          Latest edition
        </button>
      </div>

      {history.isError && (
        <Message
          title="The archive couldn't load."
          retry={() => void history.refetch()}
        >
          {errorText(history.error)}
        </Message>
      )}

      {dates.length > 0 && (
        <nav
          className="archive-navigation"
          aria-label="Digest editions"
        >
          <button
            className="pill-button"
            disabled={!older || invalid}
            onClick={() => older && select(older)}
          >
            ← Older edition
          </button>

          <span className="muted">
            Browsing the latest {dates.length} saved editions
          </span>

          <button
            className="pill-button"
            disabled={!newer || invalid}
            onClick={() => newer && select(newer)}
          >
            Newer edition →
          </button>
        </nav>
      )}

      {invalid ? (
        <Message title="Choose a valid edition date.">
          Use YYYY-MM-DD or return to the latest edition.
        </Message>
      ) : !date ? (
        history.isPending ? (
          <ArchiveLoading />
        ) : history.isError ? null : (
          <Message title="Your first edition is still ahead.">
            Saved daily digests will appear here once generated.
          </Message>
        )
      ) : digest.isPending ? (
        <ArchiveLoading />
      ) : digest.isError ? (
        statusOf(digest.error) === 404 ? (
          <Message title="No saved edition for this date.">
            Choose another day or use the edition navigation.
            Reading never generates a digest.
          </Message>
        ) : (
          <Message
            title="This edition couldn't load."
            retry={() => void digest.refetch()}
          >
            {errorText(digest.error)}
          </Message>
        )
      ) : digest.data ? (
        <DigestViewer digest={digest.data} />
      ) : null}
    </section>
  );
}

function ArchiveLoading() {
  return (
    <div
      role="status"
      aria-label="Loading digest"
      className="archive-loading"
    >
      <div className="skeleton-card" />
      <p>Opening your saved edition…</p>
    </div>
  );
}
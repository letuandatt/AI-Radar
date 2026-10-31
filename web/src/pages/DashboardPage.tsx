import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Sparkles } from 'lucide-react';

import { useListKnowledge } from '../api/generated';
import {
  Cover,
  Message,
  Loading,
  dateLabel,
  storyUrl,
  errorText,
} from '../components/shared/Reading';
import {
  ReadingOverview,
  LatestDigestCard,
} from '../components/dashboard/ReadingOverview';

import './digest.css';

const channels = [
  { label: 'All stories', sources: [] },
  { label: 'News & ideas', sources: ['rss', 'hackernews'] },
  { label: 'Open source', sources: ['github'] },
  { label: 'Models', sources: ['hf', 'huggingface'] },
];

/** Landing page: the latest ten publications, presented as an editorial reading list. */
export function DashboardPage() {
  const [channel, setChannel] = useState(0);
  const [offset, setOffset] = useState(0);

  const feed = useListKnowledge(
    {
      limit: 10,
      offset,
      sort_field: 'published_at',
      source_types: channels[channel].sources,
    },
    { query: { retry: false } },
  );

  const items = feed.data?.items ?? [];

  const featured =
    !feed.isError && offset === 0 && channel === 0
      ? items[0]
      : undefined;

  const cards = featured ? items.slice(1) : items;

  return (
    <>
      <section className="edition-heading">
        <div className="eyebrow">
          <span className="signal-dot" />
          INDEPENDENT CURIOSITY. DAILY PERSPECTIVE.
        </div>

        <div className="edition-title">
          <h1>
            Technology moves.
            <br />
            <em>Stay curious.</em>
          </h1>

          <div className="edition-note">
            <span className="tiny-label">
              YOUR READING ROOM
            </span>

            <p>
              Ideas, research and open source.
              <br />
              A clearer view of what comes next.
            </p>

            <Link to="/digest" className="text-link">
              Read the daily digest
              <ArrowUpRight size={17} />
            </Link>
          </div>
        </div>
      </section>

      <section className="lead-story">
        <div className="lead-copy">
          <span className="eyebrow">
            <Sparkles size={14} />
            {featured
              ? 'LATEST ON YOUR RADAR'
              : 'A WIDER PERSPECTIVE'}
          </span>

          <h2>
            {featured ? (
              <Link to={storyUrl(featured.id)}>
                {featured.title}
              </Link>
            ) : (
              <>
                Big ideas.
                <br />
                A clearer signal.
              </>
            )}
          </h2>

          <p>
            {featured
              ? `${featured.source_name} · ${dateLabel(featured.published_at)}`
              : 'A place to discover the work, people and possibilities shaping technology.'}
          </p>

          <Link
            className="pill-button primary-button"
            to={featured ? storyUrl(featured.id) : '/knowledge'}
          >
            {featured
              ? 'Read the story'
              : 'Explore your collection'}
            <ArrowUpRight size={18} />
          </Link>
        </div>

        <Cover variant={0} large />
      </section>

      <ReadingOverview />

      <section className="feed-section" aria-label="Stories">
        <div className="section-heading">
          <div>
            <span className="tiny-label">
              THE READING LIST
            </span>
            <h2>Fresh perspectives</h2>
          </div>

          <span className="muted">
            {feed.data
              ? `${feed.data.total} stories in this view`
              : 'Your next good read'}
          </span>
        </div>

        <div
          className="channel-tabs"
          role="group"
          aria-label="Story categories"
        >
          {channels.map((entry, index) => (
            <button
              key={entry.label}
              aria-pressed={channel === index}
              onClick={() => {
                setChannel(index);
                setOffset(0);
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {feed.isPending ? (
          <Loading />
        ) : feed.isError ? (
          <Message
            title="Your stories couldn't load."
            retry={() => void feed.refetch()}
          >
            {errorText(feed.error)}
          </Message>
        ) : !items.length ? (
          <Message title="A little quiet on this frequency.">
            No saved stories match this view yet. Try another
            category or come back after your next collection run.
          </Message>
        ) : (
          <div className="story-grid">
            {cards.map((item, index) => (
              <article className="story-card" key={item.id}>
                <Link
                  to={storyUrl(item.id)}
                  className="cover-link"
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  <Cover variant={index + 1} />
                </Link>

                <div className="story-meta">
                  <span>{item.source_name}</span>
                  <time>{dateLabel(item.published_at)}</time>
                </div>

                <h3>
                  <Link to={storyUrl(item.id)}>
                    {item.title}
                  </Link>
                </h3>

                <div className="story-bottom">
                  <span>
                    {(item.topics ?? []).slice(0, 2).join(' / ') ||
                      item.source_type}
                  </span>
                  <ArrowUpRight size={18} aria-hidden="true" />
                </div>
              </article>
            ))}
          </div>
        )}

        {feed.data &&
          (offset > 0 || feed.data.page_info.has_next) && (
            <div className="pagination">
              <button
                className="pill-button"
                disabled={!offset || feed.isFetching}
                onClick={() =>
                  setOffset(Math.max(0, offset - 10))
                }
              >
                ← Previous
              </button>

              <span>Page {Math.floor(offset / 10) + 1}</span>

              <button
                className="pill-button"
                disabled={
                  !feed.data.page_info.has_next ||
                  feed.isFetching ||
                  offset >= 100000
                }
                onClick={() => setOffset(offset + 10)}
              >
                Next →
              </button>
            </div>
          )}
      </section>

      <LatestDigestCard />
    </>
  );
}
import { Component, useState, type ReactNode } from 'react';
import { Link, Route, Routes, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Orbit,
  RefreshCw,
  Sparkles,
} from 'lucide-react';

import { AppLayout } from './components/layout/AppLayout';
import {
  useGetDigest,
  useGetDigestHistory,
  useGetKnowledge,
  useListKnowledge,
  type BrowseItem,
} from './api/generated';
import { useTheme } from './theme';

const channels = [
  { label: 'All stories', sources: [] },
  { label: 'News & ideas', sources: ['rss', 'hackernews'] },
  { label: 'Open source', sources: ['github'] },
  { label: 'Models', sources: ['hf', 'huggingface'] },
];

const dateLabel = (value?: string | null) => {
  if (!value || Number.isNaN(Date.parse(value))) {
    return 'Undated';
  }

  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value));
};

const storyUrl = (id: string) =>
  `/knowledge/${encodeURIComponent(id)}`;

function safeUrl(value?: string | null) {
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

export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <section className="empty-state" role="alert">
          <h1>Something interrupted your reading.</h1>
          <p>Please reload this page to try again.</p>
        </section>
      );
    }

    return this.props.children;
  }
}

function Cover({
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

function Message({
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

function StoryCard({
  item,
  index,
}: {
  item: BrowseItem;
  index: number;
}) {
  return (
    <article className="story-card">
      <Link
        to={storyUrl(item.id)}
        className="cover-link"
        tabIndex={-1}
        aria-hidden="true"
      >
        <Cover variant={index} />
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
  );
}

function NewsPage({ explore = false }: { explore?: boolean }) {
  const [channel, setChannel] = useState(0);
  const [offset, setOffset] = useState(0);

  const feed = useListKnowledge({
    limit: 12,
    offset,
    sort_field: 'published_at',
    source_types: channels[channel].sources,
  });

  const items = feed.data?.items ?? [];
  const featured = !explore && offset === 0 && channel === 0
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
            {explore ? (
              <>Follow your<br /><em>curiosity.</em></>
            ) : (
              <>Technology moves.<br /><em>Stay curious.</em></>
            )}
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

      {!explore && (
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
                <>Big ideas.<br />A clearer signal.</>
              )}
            </h2>

            <p>
              {featured
                ? `${featured.source_name} · ${
                    dateLabel(featured.published_at)
                  }`
                : 'A place to discover the work, people and possibilities shaping technology.'}
            </p>

            <Link
              className="pill-button primary-button"
              to={featured ? storyUrl(featured.id) : '/knowledge'}
            >
              {featured ? 'Read the story' : 'Explore your collection'}
              <ArrowUpRight size={18} />
            </Link>
          </div>

          <Cover variant={0} large />
        </section>
      )}

      <section className="feed-section" aria-label="Stories">
        <div className="section-heading">
          <div>
            <span className="tiny-label">THE READING LIST</span>
            <h2>
              {explore
                ? 'Explore the collection'
                : 'Fresh perspectives'}
            </h2>
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
          <div
            className="skeleton-grid"
            role="status"
            aria-label="Loading stories"
          >
            {[0, 1, 2].map(index => (
              <div key={index} className="skeleton-card" />
            ))}
          </div>
        ) : feed.isError ? (
          <Message
            title="Your stories couldn't load."
            retry={() => void feed.refetch()}
          >
            Please check that the local API is running,
            then try again.
          </Message>
        ) : !items.length ? (
          <Message title="A little quiet on this frequency.">
            No saved stories match this view yet. Try another category
            or come back after your next collection run.
          </Message>
        ) : (
          <div className="story-grid">
            {cards.map((item, index) => (
              <StoryCard
                key={item.id}
                item={item}
                index={index + 1}
              />
            ))}
          </div>
        )}

        {feed.data && (
          offset > 0 || feed.data.page_info.has_next
        ) && (
          <div className="pagination">
            <button
              className="pill-button"
              disabled={!offset || feed.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 12))}
            >
              <ArrowLeft size={16} />
              Previous
            </button>

            <span>Page {Math.floor(offset / 12) + 1}</span>

            <button
              className="pill-button"
              disabled={
                !feed.data.page_info.has_next || feed.isFetching
              }
              onClick={() => setOffset(offset + 12)}
            >
              Next
              <ArrowRight size={16} />
            </button>
          </div>
        )}
      </section>

      <section className="digest-banner">
        <div>
          <span className="eyebrow">THE DAILY EDITION</span>
          <h2>
            Less scrolling.
            <br />
            <em>More understanding.</em>
          </h2>
          <p>Revisit your saved briefing, one day at a time.</p>

          <Link
            to="/digest"
            className="pill-button primary-button"
          >
            Open the digest
            <ArrowRight size={17} />
          </Link>
        </div>

        <div className="digest-mark" aria-hidden="true">
          R<span>↗</span>
        </div>
      </section>
    </>
  );
}

function ArticlePage() {
  const { id = '' } = useParams();
  const article = useGetKnowledge(encodeURIComponent(id));

  if (article.isPending) {
    return (
      <Message title="Opening your story…">
        Just a moment.
      </Message>
    );
  }

  if (article.isError || !article.data) {
    return (
      <Message
        title="This story isn't available."
        retry={() => void article.refetch()}
      >
        It may have been removed, or the connection was interrupted.
      </Message>
    );
  }

  const item = article.data;
  const original = safeUrl(item.source_url);

  return (
    <article className="reading-page">
      <Link to="/knowledge" className="text-link">
        <ArrowLeft size={16} />
        Back to stories
      </Link>

      <div className="eyebrow article-source">
        {item.source_name} / {item.source_type}
      </div>

      <h1>{item.title}</h1>

      <div className="article-byline">
        <time>{dateLabel(item.published_at)}</time>
        <span>Collected {dateLabel(item.fetched_at)}</span>

        {original && (
          <a
            href={original}
            target="_blank"
            rel="noopener noreferrer"
            className="text-link"
          >
            Original source
            <ArrowUpRight size={16} />
          </a>
        )}
      </div>

      <Cover large variant={1} />

      {item.metadata.summary && (
        <p className="article-summary">
          {item.metadata.summary}
        </p>
      )}

      <div className="topic-tags">
        {item.metadata.topics.map(topic => (
          <span key={topic}>{topic}</span>
        ))}
      </div>

      <div className="article-content">
        {item.content_text}
      </div>
    </article>
  );
}

function DigestPage() {
  const history = useGetDigestHistory({ limit: 30 });
  const [selected, setSelected] = useState('');
  const date = selected || history.data?.[0] || '';

  const digest = useGetDigest(
    { date },
    { query: { enabled: Boolean(date) } },
  );

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

      {history.isPending ? (
        <Message title="Finding your editions…">
          Just a moment.
        </Message>
      ) : history.isError ? (
        <Message
          title="The archive couldn't load."
          retry={() => void history.refetch()}
        >
          Please try again.
        </Message>
      ) : !history.data?.length ? (
        <Message title="Your first edition is still ahead.">
          Saved daily digests will appear here once generated.
        </Message>
      ) : (
        <>
          <label className="date-picker">
            Choose an edition
            <select
              value={date}
              onChange={event => setSelected(event.target.value)}
            >
              {history.data.map(day => (
                <option key={day} value={day}>
                  {day}
                </option>
              ))}
            </select>
          </label>

          {digest.isPending ? (
            <Message title="Opening this edition…">
              Just a moment.
            </Message>
          ) : digest.isError || !digest.data ? (
            <Message
              title="This edition couldn't load."
              retry={() => void digest.refetch()}
            >
              Please try again.
            </Message>
          ) : (
            <div className="digest-content">
              {digest.data.intelligence.sections.map(section => (
                <section
                  key={section.section_id}
                  className="digest-section"
                >
                  <h2>{section.title}</h2>
                  <div className="article-content">
                    {section.content}
                  </div>
                </section>
              ))}

              {digest.data.sections.map(section => (
                <section
                  key={section.section_id}
                  className="digest-section"
                >
                  <h2>{section.section_title}</h2>

                  {(section.items ?? []).map(item => (
                    <div
                      key={item.knowledge_id}
                      className="digest-item"
                    >
                      <Link to={storyUrl(item.knowledge_id)}>
                        {item.title}
                        {' '}
                        <ArrowUpRight size={17} />
                      </Link>
                      <p>{item.summary}</p>
                    </div>
                  ))}
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function SettingsPage() {
  const { theme, toggle } = useTheme();

  return (
    <section className="reading-page">
      <span className="eyebrow">
        MAKE YOURSELF AT HOME
      </span>
      <h1>
        Your space.
        <br />
        <em>Your pace.</em>
      </h1>
      <p className="intro-copy">
        A comfortable place to keep up with what interests you.
      </p>

      <div className="preference-card">
        <div>
          <h2>Set the mood</h2>
          <p>
            Currently reading in {theme} mode.
            Your preference stays in this browser.
          </p>
        </div>

        <button className="pill-button" onClick={toggle}>
          Switch to {theme === 'dark' ? 'light' : 'dark'}
        </button>
      </div>
    </section>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<NewsPage />} />
          <Route
            path="knowledge"
            element={<NewsPage explore />}
          />
          <Route
            path="knowledge/:id"
            element={<ArticlePage />}
          />
          <Route
            path="digest"
            element={<DigestPage />}
          />
          <Route
            path="settings"
            element={<SettingsPage />}
          />
          <Route
            path="*"
            element={
              <Message title="This page is off the radar.">
                <Link to="/">Return to the feed</Link>
              </Message>
            }
          />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
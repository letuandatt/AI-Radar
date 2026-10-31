import { Component, useState, type ReactNode } from 'react';
import { Link, Route, Routes } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Sparkles,
} from 'lucide-react';

import { AppLayout } from './components/layout/AppLayout';
import {
  useGetDigest,
  useGetDigestHistory,
  useListKnowledge,
  type BrowseItem,
} from './api/generated';
import { useTheme } from './theme';
import {
  Cover,
  Message,
  dateLabel,
  storyUrl,
} from './components/shared/Reading';
import { KnowledgePage } from './pages/KnowledgePage';
import { KnowledgeDetailPage } from './pages/KnowledgeDetailPage';

const channels = [
  { label: 'All stories', sources: [] },
  { label: 'News & ideas', sources: ['rss', 'hackernews'] },
  { label: 'Open source', sources: ['github'] },
  { label: 'Models', sources: ['hf', 'huggingface'] },
];

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
            element={<KnowledgePage />}
          />

          <Route
            path="knowledge/:id"
            element={<KnowledgeDetailPage />}
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
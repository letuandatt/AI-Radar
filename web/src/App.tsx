import { Component, type ReactNode } from 'react';
import { Link, Route, Routes } from 'react-router-dom';

import { AppLayout } from './components/layout/AppLayout';
import { Message } from './components/shared/Reading';
import { useTheme } from './theme';
import { KnowledgePage } from './pages/KnowledgePage';
import { KnowledgeDetailPage } from './pages/KnowledgeDetailPage';
import { DashboardPage } from './pages/DashboardPage';
import { DigestPage } from './pages/DigestPage';

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
          <Route index element={<DashboardPage />} />

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
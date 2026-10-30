import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { Moon, Radio, SlidersHorizontal, Sun } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { useTheme } from '../../theme';

export function Header() {
  const { theme, toggle } = useTheme();

  return (
    <header className="site-header">
      <Link to="/" className="brand" aria-label="AI-Radar home">
        <Radio size={26} />
        <span>
          ai<span className="brand-dot">.</span>radar
        </span>
      </Link>

      <nav aria-label="Main navigation">
        <NavLink to="/" end>The feed</NavLink>
        <NavLink to="/knowledge">Explore</NavLink>
        <NavLink to="/digest">Daily digest</NavLink>
      </nav>

      <div className="header-actions">
        <button
          className="icon-button"
          onClick={toggle}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
        </button>

        <Link
          to="/settings"
          className="text-link space-link"
          aria-label="Your space"
        >
          <span className="preferences">Your space</span>
          <SlidersHorizontal size={17} />
        </Link>
      </div>
    </header>
  );
}

export function AppLayout() {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
    main.current?.focus({ preventScroll: true });
  }, [pathname]);

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <div className="site-shell">
        <Header />

        {import.meta.env.MODE === 'mock' && (
          <div className="demo-notice">
            DESIGN PREVIEW · Sample articles, not live news
          </div>
        )}

        <main id="main-content" ref={main} tabIndex={-1}>
          <Outlet />
        </main>

        <footer className="site-footer">
          <Link to="/" className="brand">
            <Radio size={20} />
            <span>ai.radar</span>
          </Link>
          <p>A little less noise. A lot more perspective.</p>
          <span>Made for the curious.</span>
        </footer>
      </div>
    </>
  );
}
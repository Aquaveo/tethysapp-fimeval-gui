// reactapp/src/AppShell.tsx
// The workspace shell: branded header + footer, a slim left nav, a persistent
// Runs list, and a detail pane (<Outlet/>) that renders the active route
// (New Evaluation wizard / run detail / docs).
import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import Header from './Header';
import Footer from './Footer';
import RunsList from './RunsList';
import WelcomeModal from './WelcomeModal';
import './AppShell.css';

// Show the welcome/guidelines modal (FE40) on every page load/refresh, unless
// the user has ticked "Don't show this on startup" (remembered in localStorage).
// It can always be reopened from the nav's "Guidelines" link.
const HIDE_WELCOME_KEY = 'fimeval.hideWelcome';

function hideWelcomePref(): boolean {
  try {
    return localStorage.getItem(HIDE_WELCOME_KEY) === '1';
  } catch {
    return false;
  }
}

export default function AppShell() {
  // Open on load unless the user opted out.
  const [welcomeOpen, setWelcomeOpen] = useState(() => !hideWelcomePref());
  const [dontShow, setDontShow] = useState(hideWelcomePref);

  const closeWelcome = () => setWelcomeOpen(false);

  // The checkbox directly controls the persistent "hide on startup" preference.
  const changeDontShow = (v: boolean) => {
    setDontShow(v);
    try {
      if (v) localStorage.setItem(HIDE_WELCOME_KEY, '1');
      else localStorage.removeItem(HIDE_WELCOME_KEY);
    } catch {
      /* ignore storage errors (private mode etc.) */
    }
  };

  return (
    <div className="wk-app">
      <Header />
      <div className="wk-body">
        {/* One consolidated left sidebar (FE44): New Evaluation, the Runs
            previews, then Documentation / Guidelines / signed-in. */}
        <nav className="wk-sidebar" aria-label="Primary">
          <NavLink to="/new" className="wk-new-btn">
            <span aria-hidden="true">＋</span> New Evaluation
          </NavLink>

          <div className="wk-sidebar-runs">
            <RunsList />
          </div>

          <div className="wk-sidebar-foot">
            <NavLink
              to="/docs"
              className={({ isActive }) => 'wk-nav-item' + (isActive ? ' is-active' : '')}
            >
              Documentation
            </NavLink>
            <button
              type="button"
              className="wk-nav-item wk-nav-btn"
              onClick={() => setWelcomeOpen(true)}
            >
              Guidelines
            </button>
            <div className="wk-nav-foot">Signed in</div>
          </div>
        </nav>

        <main className="wk-detail">
          <Outlet />
        </main>
      </div>
      <Footer />
      <WelcomeModal
        open={welcomeOpen}
        onClose={closeWelcome}
        dontShow={dontShow}
        onDontShowChange={changeDontShow}
      />
    </div>
  );
}

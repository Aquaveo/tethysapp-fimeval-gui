// reactapp/src/AppShell.tsx
// The workspace shell: branded header + footer, a slim left nav, a persistent
// Runs list, and a detail pane (<Outlet/>) that renders the active route
// (New Evaluation wizard / run detail / docs).
import { NavLink, Outlet } from 'react-router-dom';
import Header from './Header';
import Footer from './Footer';
import RunsList from './RunsList';
import './AppShell.css';

export default function AppShell() {
  return (
    <div className="wk-app">
      <Header />
      <div className="wk-body">
        <nav className="wk-nav" aria-label="Primary">
          <NavLink to="/new" className="wk-new-btn">
            <span aria-hidden="true">＋</span> New Evaluation
          </NavLink>
          <NavLink
            to="/docs"
            className={({ isActive }) => 'wk-nav-item' + (isActive ? ' is-active' : '')}
          >
            Documentation
          </NavLink>
          <div className="wk-nav-foot">Signed in</div>
        </nav>

        <aside className="wk-runlist-col" aria-label="Runs">
          <RunsList />
        </aside>

        <main className="wk-detail">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}

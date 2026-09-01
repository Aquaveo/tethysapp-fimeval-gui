// reactapp/src/Header.tsx
// FIM-family branded header (matches FIMbench's chrome): logo + title + tagline,
// and a Documentation link. Rendered by AppShell.
import { Link, NavLink } from 'react-router-dom';

export default function Header() {
  return (
    <header className="wk-header">
      <Link className="wk-brand" to="/new">
        <img
          className="wk-brand-logo"
          src="/static/fimeval_gui/images/android-chrome-512x512.png"
          alt="FIMeval logo"
        />
        <span>
          <h1 className="wk-title">FIMeval</h1>
          <p className="wk-tagline">Evaluate candidate flood maps against benchmarks</p>
        </span>
      </Link>
      <nav className="wk-header-actions">
        <NavLink
          to="/docs"
          className={({ isActive }) => 'wk-doc-pill' + (isActive ? ' is-active' : '')}
        >
          Documentation
        </NavLink>
      </nav>
    </header>
  );
}

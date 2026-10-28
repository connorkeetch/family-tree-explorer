import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export interface NavItem {
  key: string;
  label: string;
}

/**
 * Site-wide top navigation bar. Hosts the brand, the primary section links
 * (Map / Fan chart / Migration / Insights), the "new upload" action, and the
 * account menu (email + sign out) — so navigation and session controls live in
 * one persistent header. On narrow screens the section links scroll horizontally
 * and the brand/root labels collapse rather than overflow.
 */
export default function TopNav({
  items,
  active,
  onSelect,
  rootName,
}: {
  items: NavItem[];
  active: string;
  onSelect: (key: string) => void;
  rootName?: string | null;
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function signOut() {
    await logout();
    navigate("/login");
  }

  return (
    <nav className="topnav">
      <Link className="navbrand" to="/" title="Your trees">
        <span className="navbrand-mark">🌳</span>
        <span className="navbrand-text">Kinwhere</span>
      </Link>
      <div className="navlinks">
        {items.map((it) => (
          <button
            key={it.key}
            className={"navlink" + (active === it.key ? " on" : "")}
            onClick={() => onSelect(it.key)}
            aria-current={active === it.key ? "page" : undefined}
          >
            {it.label}
          </button>
        ))}
      </div>
      {rootName && <span className="navroot">{rootName}</span>}
      <Link className="navlink navup" to="/upload">
        Import tree
      </Link>
      {user && (
        <div className="navacct">
          <span className="navacct-email" title={user.email}>
            {user.email}
          </span>
          <button className="navlink navsignout" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}

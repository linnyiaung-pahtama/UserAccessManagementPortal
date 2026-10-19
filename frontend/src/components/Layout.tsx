import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { REQUESTS_CHANGED } from "../pages/admin/AccessRequestsPage";
import Icon, { type IconName } from "./Icon";
import { Avatar } from "./ui";

function NavItem({ to, icon, label, end, count }: { to: string; icon: IconName; label: string; end?: boolean; count?: number }) {
  return (
    <NavLink to={to} end={end} className="nav-item">
      <Icon name={icon} size={17} />
      <span>{label}</span>
      {!!count && <span className="nav-count">{count}</span>}
    </NavLink>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => setMenuOpen(false), [location.pathname]);

  // Open access requests, shown next to the menu item; refreshed on every page change and after one is handled.
  const [openRequests, setOpenRequests] = useState(0);
  useEffect(() => {
    if (!user?.is_admin) return;
    const load = () => {
      api.get<{ open: number }>("/api/admin/access-requests/count").then((r) => setOpenRequests(r.open)).catch(() => {});
    };
    load();
    window.addEventListener(REQUESTS_CHANGED, load);
    return () => window.removeEventListener(REQUESTS_CHANGED, load);
  }, [user?.is_admin, location.pathname]);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const displayName = user?.username || "";

  return (
    <div className={`app-shell${menuOpen ? " menu-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-logo"><Icon name="shield" size={16} /></span>
          Access Portal
        </div>

        <nav className="nav">
          <NavItem to="/" end icon="grid" label="My apps" />
          {user?.is_admin && (
            <>
              <div className="nav-section">Administration</div>
              <NavItem to="/admin" end icon="dashboard" label="Overview" />
              <NavItem to="/admin/users" icon="users" label="Users" />
              <NavItem to="/admin/applications" icon="layers" label="Systems" />
              <NavItem to="/admin/access-requests" icon="inbox" label="Access requests" count={openRequests} />
              <NavItem to="/admin/audit" icon="activity" label="Audit log" />
            </>
          )}
        </nav>

        <div className="sidebar-footer">
          <NavLink to="/profile" className="user-card">
            <Avatar name={displayName} size={34} />
            <div className="user-card-text">
              <div className="user-card-name">{displayName}</div>
              <div className="user-card-sub">{user?.email}</div>
            </div>
          </NavLink>
          <button className="nav-item as-button" onClick={handleLogout}>
            <Icon name="logout" size={17} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="sidebar-scrim" onClick={() => setMenuOpen(false)} />

      <div className="main">
        <header className="mobile-bar">
          <button className="btn ghost icon-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Icon name="menu" size={20} />
          </button>
          <div className="brand">
            <span className="brand-logo"><Icon name="shield" size={14} /></span>
            Access Portal
          </div>
          <Avatar name={displayName} size={30} />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

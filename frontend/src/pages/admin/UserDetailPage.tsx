import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, EMAIL_DOMAIN, errorMessage, generatePassword, type Application, type UserDetail } from "../../api";
import { useAuth } from "../../auth";
import { useFeedback } from "../../components/feedback";
import Icon from "../../components/Icon";
import { Alert, Avatar, Badge, PageHeader, PasswordInput, Spinner, StatusBadge, TimeAgo } from "../../components/ui";

export default function UserDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user: me } = useAuth();
  const { toast, confirm } = useFeedback();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [apps, setApps] = useState<Application[]>([]);
  const [error, setError] = useState("");

  const [profile, setProfile] = useState({ username: "", full_name: "", email: "", is_active: true, is_admin: false, password: "" });
  const [profileError, setProfileError] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [savingRoles, setSavingRoles] = useState(false);

  useEffect(() => {
    Promise.all([api.get<UserDetail>(`/api/admin/users/${id}`), api.get<Application[]>("/api/admin/applications")])
      .then(([u, a]) => {
        load(u);
        setApps(a);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [id]);

  function load(u: UserDetail) {
    setUser(u);
    setProfile({ username: u.username, full_name: u.full_name, email: u.email, is_active: u.is_active, is_admin: u.is_admin, password: "" });
    setSelected(new Set(u.role_ids));
  }

  const roleLabel = useMemo(() => {
    const m = new Map<number, string>();
    apps.forEach((a) => a.roles.forEach((r) => m.set(r.id, `${a.name}: ${r.name}`)));
    return m;
  }, [apps]);

  const changes = useMemo(() => {
    if (!user) return { added: [] as number[], removed: [] as number[] };
    const orig = new Set(user.role_ids);
    return {
      added: [...selected].filter((r) => !orig.has(r)),
      removed: user.role_ids.filter((r) => !selected.has(r)),
    };
  }, [user, selected]);
  const dirty = changes.added.length + changes.removed.length > 0;

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    if (!user) return;
    setProfileError("");
    if (user.is_active && !profile.is_active) {
      const ok = await confirm({
        title: `Disable ${user.username}?`,
        message: "They'll be signed out of the portal and every system immediately, and won't be able to sign in until re-enabled.",
        confirmLabel: "Disable account",
        danger: true,
      });
      if (!ok) return;
    }
    const username = profile.username.trim();
    if (username !== user.username) {
      const ok = await confirm({
        title: `Change username to "${username}"?`,
        message: <>They'll sign in as <strong>{username}</strong> from now on; <strong>{user.username}</strong> stops working.</>,
        confirmLabel: "Change username",
      });
      if (!ok) return;
    }
    const { password, full_name, ...rest } = { ...profile, username };
    // An older account may have no name yet; it can still be saved without one.
    const body = { ...rest, ...(full_name.trim() ? { full_name: full_name.trim() } : {}), ...(password ? { password } : {}) };
    try {
      const u = await api.patch<UserDetail>(`/api/admin/users/${id}`, body);
      load(u);
      toast(password ? "Saved. Password reset and all sessions signed out." : "Account saved");
    } catch (err) {
      setProfileError(errorMessage(err));
    }
  }

  async function saveRoles() {
    setSavingRoles(true);
    try {
      const u = await api.put<UserDetail>(`/api/admin/users/${id}/roles`, { role_ids: [...selected] });
      load(u);
      toast("Access updated. Systems pick it up at the user's next sign-in or token refresh.");
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSavingRoles(false);
    }
  }

  async function deleteUser() {
    if (!user) return;
    const ok = await confirm({
      title: `Delete ${user.username}?`,
      message: <>This permanently removes the account and all of its system access. Consider <strong>disabling</strong> it instead to keep its history.</>,
      confirmLabel: "Delete user",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/admin/users/${id}`);
      toast(`${user.username} deleted`);
      navigate("/admin/users");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  function toggle(roleId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(roleId)) next.delete(roleId);
      else next.add(roleId);
      return next;
    });
  }

  if (error) return <Alert>{error}</Alert>;
  if (!user) return <Spinner />;
  const isSelf = me?.id === user.id;
  const name = user.full_name || user.username;
  const systemsWithAccess = apps.filter((a) => a.roles.some((r) => selected.has(r.id))).length;

  return (
    <div className={dirty ? "has-save-bar" : ""}>
      <PageHeader
        back={<Link to="/admin/users"><Icon name="arrowLeft" size={14} /> Users</Link>}
        title={
          <span className="title-with-avatar">
            <Avatar name={name} size={44} />
            <span>
              {name}
              <span className="title-badges">
                <StatusBadge active={user.is_active} />
                {user.is_admin && <Badge tone="blue">Admin</Badge>}
                {isSelf && <Badge>You</Badge>}
              </span>
            </span>
          </span>
        }
        subtitle={<>{user.full_name && <>{user.username} · </>}{user.email} · last sign-in <TimeAgo value={user.last_login_at} /></>}
      />

      <div className="detail-grid">
        <div className="card">
          <div className="card-header">
            <div>
              <h2>System access</h2>
              <p className="muted small">
                Has access to {systemsWithAccess} of {apps.length} system{apps.length === 1 ? "" : "s"}. A user can sign in to a system only if they hold at least one of its roles.
              </p>
            </div>
          </div>
          {apps.length === 0 && <p className="muted">No systems registered yet. <Link to="/admin/applications">Register one</Link>.</p>}
          {apps.map((app) => {
            const count = app.roles.filter((r) => selected.has(r.id)).length;
            return (
              <section key={app.id} className={`access-block${count ? " granted" : ""}`}>
                <div className="access-title">
                  <Avatar name={app.name} size={28} square />
                  <Link to={`/admin/applications/${app.id}`}>{app.name}</Link>
                  {count ? <Badge tone="green">{count} role{count === 1 ? "" : "s"}</Badge> : <Badge>No access</Badge>}
                  {!app.is_active && <Badge tone="red">System disabled</Badge>}
                </div>
                {app.roles.length === 0 ? (
                  <p className="muted small">This system has no roles defined yet.</p>
                ) : (
                  <div className="role-grid">
                    {app.roles.map((role) => (
                      <label key={role.id} className={`role-tile${selected.has(role.id) ? " on" : ""}`}>
                        <input type="checkbox" checked={selected.has(role.id)} onChange={() => toggle(role.id)} />
                        <span>
                          <span className="role-name">{role.name}</span>
                          {role.description && <span className="role-desc">{role.description}</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                <EffectivePermissions app={app} saved={new Set(user.role_ids)} selected={selected} />
              </section>
            );
          })}
        </div>

        <div className="stack">
          <form className="card" onSubmit={saveProfile}>
            <h2>Account</h2>
            <Alert>{profileError}</Alert>
            <label>
              Username
              <input
                value={profile.username}
                onChange={(e) => setProfile({ ...profile, username: e.target.value })}
                required
                pattern="[A-Za-z0-9._\-]{3,100}"
                title="3–100 letters, digits, dots, underscores or dashes"
              />
              <span className="hint">What they sign in with. Changing it doesn't sign them out.</span>
            </label>
            <label>
              Full name
              <input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} maxLength={255} placeholder="e.g. Mya Thida" />
              <span className="hint">Shown in the portal, and sent to systems as the person's name.</span>
            </label>
            <label>
              Email
              <input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} required />
              <span className="hint">A new address must end in @{EMAIL_DOMAIN}.</span>
            </label>
            <label>
              Reset password
              <PasswordInput
                value={profile.password}
                onChange={(v) => setProfile({ ...profile, password: v })}
                onGenerate={() => setProfile({ ...profile, password: generatePassword() })}
                minLength={8}
                maxLength={72}
              />
              <span className="hint">Leave blank to keep the current password. Resetting signs the user out everywhere, and they must choose a new one at their next sign-in.</span>
            </label>
            <label className="switch">
              <input type="checkbox" checked={profile.is_active} disabled={isSelf} onChange={(e) => setProfile({ ...profile, is_active: e.target.checked })} />
              <span className="switch-track" />
              <span>Account active{isSelf && <span className="hint">You can't disable your own account.</span>}</span>
            </label>
            <label className="switch">
              <input type="checkbox" checked={profile.is_admin} disabled={isSelf} onChange={(e) => setProfile({ ...profile, is_admin: e.target.checked })} />
              <span className="switch-track" />
              <span>Portal administrator<span className="hint">Can manage all users, systems and roles.</span></span>
            </label>
            <button className="btn primary">Save account</button>
          </form>

          {!isSelf && (
            <div className="card danger-zone">
              <h2>Delete user</h2>
              <p className="muted small">Permanently removes the account and its access. The audit log keeps its history.</p>
              <button className="btn danger" onClick={deleteUser}><Icon name="trash" /> Delete {user.username}</button>
            </div>
          )}
        </div>
      </div>

      {dirty && (
        <div className="save-bar">
          <div className="save-bar-changes">
            <strong>Unsaved access changes</strong>
            <div className="chips">
              {changes.added.map((r) => <Badge key={r} tone="green">+ {roleLabel.get(r)}</Badge>)}
              {changes.removed.map((r) => <Badge key={r} tone="red">− {roleLabel.get(r)}</Badge>)}
            </div>
          </div>
          <div className="row">
            <button className="btn ghost" onClick={() => setSelected(new Set(user.role_ids))}>Discard</button>
            <button className="btn primary" onClick={saveRoles} disabled={savingRoles}>{savingRoles ? "Saving…" : "Save access"}</button>
          </div>
        </div>
      )}
    </div>
  );
}

function EffectivePermissions({ app, saved, selected }: { app: Application; saved: Set<number>; selected: Set<number> }) {
  if (app.permissions.length === 0) return null;
  const grants = (roles: Set<number>) =>
    new Set(app.roles.filter((r) => roles.has(r.id)).flatMap((r) => r.permission_ids));
  const before = grants(saved);
  const after = grants(selected);
  const shown = app.permissions.filter((p) => before.has(p.id) || after.has(p.id));
  return (
    <div className="effective">
      <span className="muted small">Can do:</span>
      {shown.length === 0 && <span className="muted small">nothing</span>}
      {shown.map((p) => {
        const tone = after.has(p.id) && !before.has(p.id) ? "green" : !after.has(p.id) ? "red" : "neutral";
        return (
          <Badge key={p.id} tone={tone} title={p.description}>
            {tone === "green" ? "+ " : tone === "red" ? "− " : ""}{p.name}
          </Badge>
        );
      })}
    </div>
  );
}

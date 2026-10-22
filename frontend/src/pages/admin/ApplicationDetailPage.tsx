import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorMessage, type Application, type ApplicationWithSecret, type Member, type Role } from "../../api";
import { useFeedback } from "../../components/feedback";
import Icon from "../../components/Icon";
import {
  Alert, Avatar, Badge, CopyField, EmptyState, Modal, PageHeader, SecretReveal, Spinner, StatusBadge, Tabs,
} from "../../components/ui";
import PermissionsTab from "./PermissionsTab";
import QuickStart from "../../components/QuickStart";

type Tab = "roles" | "permissions" | "users" | "settings" | "integration";

export default function ApplicationDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast, confirm } = useFeedback();
  const [app, setApp] = useState<Application | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("roles");
  const [secret, setSecret] = useState<string | null>(null);

  const [settings, setSettings] = useState({ name: "", description: "", home_url: "", redirect_uris: "", web_origins: "", is_active: true, allow_access_requests: false });
  const [settingsError, setSettingsError] = useState("");

  const [newRole, setNewRole] = useState({ name: "", description: "" });
  const [editing, setEditing] = useState<Role | null>(null);
  const [roleError, setRoleError] = useState("");
  const [memberQ, setMemberQ] = useState("");

  const base = window.location.origin;

  function loadApp(a: Application) {
    setApp(a);
    setSettings({
      name: a.name, description: a.description, home_url: a.home_url,
      redirect_uris: a.redirect_uris.join("\n"), web_origins: a.web_origins.join("\n"), is_active: a.is_active,
      allow_access_requests: a.allow_access_requests,
    });
  }

  async function refresh() {
    const [a, m] = await Promise.all([
      api.get<Application>(`/api/admin/applications/${id}`),
      api.get<Member[]>(`/api/admin/applications/${id}/members`),
    ]);
    loadApp(a);
    setMembers(m);
  }

  useEffect(() => {
    refresh().catch((e) => setError(errorMessage(e)));
  }, [id]);

  async function saveSettings(e: FormEvent) {
    e.preventDefault();
    if (!app) return;
    setSettingsError("");
    if (app.is_active && !settings.is_active) {
      const ok = await confirm({
        title: `Disable ${app.name}?`,
        message: "Nobody will be able to sign in to this system through the portal until it's re-enabled. Roles and assignments are kept.",
        confirmLabel: "Disable system",
        danger: true,
      });
      if (!ok) return;
    }
    try {
      const a = await api.patch<Application>(`/api/admin/applications/${id}`, {
        ...settings,
        home_url: settings.home_url.trim(),
        redirect_uris: settings.redirect_uris.split(/\s+/).filter(Boolean),
        web_origins: settings.web_origins.split(/\s+/).filter(Boolean),
      });
      loadApp(a);
      toast("Settings saved");
    } catch (err) {
      setSettingsError(errorMessage(err));
    }
  }

  async function rotateSecret() {
    const ok = await confirm({
      title: "Rotate client secret?",
      message: "A new secret is generated and the current one stops working immediately. Update the system's configuration right away to avoid sign-in failures.",
      confirmLabel: "Rotate secret",
      danger: true,
    });
    if (!ok) return;
    try {
      const a = await api.post<ApplicationWithSecret>(`/api/admin/applications/${id}/rotate-secret`);
      setSecret(a.client_secret);
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  async function addRole(e: FormEvent) {
    e.preventDefault();
    setRoleError("");
    try {
      await api.post(`/api/admin/applications/${id}/roles`, newRole);
      toast(`Role "${newRole.name}" added`);
      setNewRole({ name: "", description: "" });
      await refresh();
    } catch (err) {
      setRoleError(errorMessage(err));
    }
  }

  async function saveRole(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setRoleError("");
    try {
      await api.patch(`/api/admin/applications/${id}/roles/${editing.id}`, { name: editing.name, description: editing.description });
      setEditing(null);
      toast("Role updated");
      await refresh();
    } catch (err) {
      setRoleError(errorMessage(err));
    }
  }

  async function deleteRole(role: Role) {
    const holders = members.filter((m) => m.roles.includes(role.name)).length;
    if (holders) {
      // The portal refuses to delete a role in use, so nobody loses access by accident.
      toast(`${holders} user${holders === 1 ? " still has" : "s still have"} "${role.name}". Remove it from them first (see the Users tab), then delete it.`, "error");
      return;
    }
    const ok = await confirm({
      title: `Delete role "${role.name}"?`,
      message: "Nobody holds this role.",
      confirmLabel: "Delete role",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/admin/applications/${id}/roles/${role.id}`);
      toast(`Role "${role.name}" deleted`);
      await refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  async function deleteApp() {
    if (!app) return;
    const ok = await confirm({
      title: `Delete ${app.name}?`,
      message: <>All its roles and the access of <strong>{members.length} user{members.length === 1 ? "" : "s"}</strong> are removed, and nobody can sign in to it any more. This can't be undone.</>,
      confirmLabel: "Delete system",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/admin/applications/${id}`);
      toast(`${app.name} deleted`);
      navigate("/admin/applications");
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  if (error) return <Alert>{error}</Alert>;
  if (!app) return <Spinner />;

  const holders = (role: Role) => members.filter((m) => m.roles.includes(role.name)).length;
  const shownMembers = members.filter((m) =>
    `${m.full_name} ${m.username} ${m.email} ${m.roles.join(" ")}`.toLowerCase().includes(memberQ.toLowerCase()),
  );

  return (
    <>
      <PageHeader
        back={<Link to="/admin/applications"><Icon name="arrowLeft" size={14} /> Systems</Link>}
        title={
          <span className="title-with-avatar">
            <Avatar name={app.name} size={44} square />
            <span>
              {app.name}
              <span className="title-badges"><StatusBadge active={app.is_active} /></span>
            </span>
          </span>
        }
        subtitle={<>{app.description || "No description"} · <code>{app.client_id}</code></>}
        actions={app.home_url && <a className="btn" href={app.home_url} target="_blank" rel="noreferrer"><Icon name="external" /> Open</a>}
      />

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "roles", label: <>Roles <span className="count">{app.roles.length}</span></> },
          { id: "permissions", label: <>Permissions <span className="count">{app.permissions.length}</span></> },
          { id: "users", label: <>Users <span className="count">{members.length}</span></> },
          { id: "settings", label: "Settings" },
          { id: "integration", label: "Integration" },
        ]}
      />

      {tab === "roles" && (
        <div className="card flush">
          <div className="card-pad">
            <p className="muted small">Give people roles from their user page. What each role can do is set on the Permissions tab.</p>
            <Alert>{roleError}</Alert>
          </div>
          {app.roles.length === 0 ? (
            <EmptyState icon="shield" title="No roles yet">Add a role below so users can be given access.</EmptyState>
          ) : (
            <ul className="list bordered">
              {app.roles.map((role) =>
                editing?.id === role.id ? (
                  <li key={role.id} className="list-pad">
                    <form className="inline-form" onSubmit={saveRole}>
                      <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value.toLowerCase() })} required autoFocus />
                      <input value={editing.description} placeholder="Description" onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
                      <button className="btn small primary">Save</button>
                      <button type="button" className="btn small ghost" onClick={() => setEditing(null)}>Cancel</button>
                    </form>
                  </li>
                ) : (
                  <li key={role.id} className="list-pad role-row">
                    <div className="grow">
                      <div className="role-name">{role.name}</div>
                      <div className="muted small">{role.description || "No description"}</div>
                      <div className="chips" style={{ marginTop: 6 }}>
                        {app.permissions.filter((p) => role.permission_ids.includes(p.id)).map((p) => <Badge key={p.id}>{p.name}</Badge>)}
                        {role.permission_ids.length === 0 && <span className="muted small">No permissions yet</span>}
                      </div>
                    </div>
                    <span className="muted small nowrap">{holders(role)} user{holders(role) === 1 ? "" : "s"}</span>
                    <div className="row-actions">
                      <button className="btn small ghost icon-btn" title="Edit role" onClick={() => setEditing(role)}><Icon name="edit" size={14} /></button>
                      <button className="btn small ghost icon-btn danger-text" title="Delete role" onClick={() => deleteRole(role)}><Icon name="trash" size={14} /></button>
                    </div>
                  </li>
                ),
              )}
            </ul>
          )}
          <form className="inline-form card-pad add-row" onSubmit={addRole}>
            <input placeholder="New role name, e.g. approver" value={newRole.name} onChange={(e) => setNewRole({ ...newRole, name: e.target.value.toLowerCase() })} required pattern="[a-z0-9._:\-]{1,100}" title="Lowercase letters, digits and . _ : -" />
            <input placeholder="Description (optional)" value={newRole.description} onChange={(e) => setNewRole({ ...newRole, description: e.target.value })} />
            <button className="btn primary"><Icon name="plus" /> Add role</button>
          </form>
        </div>
      )}

      {tab === "permissions" && <PermissionsTab app={app} onChanged={refresh} />}

      {tab === "users" && (
        <div className="card flush">
          <div className="toolbar">
            <span className="muted small">Everyone who can sign in to {app.name}.</span>
            <div className="search-box">
              <Icon name="search" />
              <input placeholder="Filter users or roles…" value={memberQ} onChange={(e) => setMemberQ(e.target.value)} />
            </div>
          </div>
          {members.length === 0 ? (
            <EmptyState icon="users" title="Nobody has access yet">Open a user's page and give them one of this system's roles.</EmptyState>
          ) : (
            <ul className="list bordered">
              {shownMembers.map((m) => (
                <li key={m.user_id}>
                  <Link to={`/admin/users/${m.user_id}`} className="list-row list-pad">
                    <Avatar name={m.full_name || m.username} size={34} />
                    <div className="grow">
                      <div className="person-name">{m.full_name || m.username} {!m.is_active && <Badge tone="red">Disabled</Badge>}</div>
                      <div className="muted small">{m.username} · {m.email}</div>
                    </div>
                    <div className="chips">{m.roles.map((r) => <Badge key={r} tone="blue">{r}</Badge>)}</div>
                    <Icon name="chevronRight" className="muted" />
                  </Link>
                </li>
              ))}
              {shownMembers.length === 0 && <li className="list-pad muted">No matches.</li>}
            </ul>
          )}
        </div>
      )}

      {tab === "settings" && (
        <div className="detail-grid">
          <form className="card" onSubmit={saveSettings}>
            <h2>Settings</h2>
            <Alert>{settingsError}</Alert>
            <label>Name<input value={settings.name} onChange={(e) => setSettings({ ...settings, name: e.target.value })} required /></label>
            <label>Description<input value={settings.description} onChange={(e) => setSettings({ ...settings, description: e.target.value })} /></label>
            <label>
              Launch URL
              <input type="url" value={settings.home_url} onChange={(e) => setSettings({ ...settings, home_url: e.target.value })} />
              <span className="hint">Where "Open" on the My apps page takes users.</span>
            </label>
            <label>
              Redirect URIs
              <textarea rows={3} value={settings.redirect_uris} onChange={(e) => setSettings({ ...settings, redirect_uris: e.target.value })} />
              <span className="hint">One per line, exact match.</span>
            </label>
            <label>
              Web origins
              <textarea rows={2} value={settings.web_origins} placeholder="https://finance.company.com"
                        onChange={(e) => setSettings({ ...settings, web_origins: e.target.value })} />
              <span className="hint">
                Addresses a browser app runs on (e.g. React), allowed to call the portal directly. One per line,
                no path. Leave empty for server-side apps.
              </span>
            </label>
            <label className="switch">
              <input type="checkbox" checked={settings.is_active} onChange={(e) => setSettings({ ...settings, is_active: e.target.checked })} />
              <span className="switch-track" />
              <span>System active<span className="hint">When off, nobody can sign in to it through the portal.</span></span>
            </label>
            <label className="switch">
              <input type="checkbox" checked={settings.allow_access_requests} onChange={(e) => setSettings({ ...settings, allow_access_requests: e.target.checked })} />
              <span className="switch-track" />
              <span>Allow access requests<span className="hint">Listed on the Request access page (under the sign-in form), so people without access can ask an admin for it.</span></span>
            </label>
            <button className="btn primary">Save settings</button>
          </form>
          <div className="card danger-zone">
            <h2>Delete system</h2>
            <p className="muted small">Removes the system, its roles and everyone's access to it. The audit log keeps its history.</p>
            <button className="btn danger" onClick={deleteApp}><Icon name="trash" /> Delete {app.name}</button>
          </div>
        </div>
      )}

      {tab === "integration" && <QuickStart app={app} portal={base} />}

      {tab === "integration" && (
        <div className="detail-grid">
          <div className="card">
            <h2>Connection details</h2>
            <p className="muted small">Configure {app.name} as an OpenID Connect client. Most frameworks only need the discovery URL, client ID and secret.</p>
            <dl className="kv">
              <dt>Discovery URL</dt><dd><CopyField value={`${base}/.well-known/openid-configuration`} /></dd>
              <dt>Issuer</dt><dd><CopyField value={base} /></dd>
              <dt>Client ID</dt><dd><CopyField value={app.client_id} /></dd>
              <dt>Scopes</dt><dd><CopyField value="openid profile email" /></dd>
              <dt>Client type</dt><dd>{app.is_confidential ? "Confidential (client secret)" : "Public (PKCE, no secret)"}</dd>
              {!app.is_confidential && (
                <><dt>Web origins</dt><dd>{app.web_origins.length ? app.web_origins.join(", ") : <span className="muted">none, set them on the Settings tab</span>}</dd></>
              )}
              <dt>Permissions claim</dt><dd><code>permissions</code> · array of strings, check these in code</dd>
              <dt>Roles claim</dt><dd><code>roles</code> · array of strings</dd>
            </dl>
          </div>
          <div className="card">
            <h2>Client secret</h2>
            {app.is_confidential ? (
              <>
                <p className="muted small">Secrets are stored hashed, so the current one can't be shown. Rotate it to get a new one.</p>
                <button className="btn" onClick={rotateSecret}><Icon name="refresh" /> Rotate secret</button>
              </>
            ) : (
              <p className="muted small">This is a public client. It authenticates with PKCE and has no secret.</p>
            )}
          </div>
        </div>
      )}

      <Modal
        open={!!secret}
        title="New client secret"
        onClose={() => setSecret(null)}
        footer={<button className="btn primary" onClick={() => setSecret(null)}>I've saved it</button>}
      >
        {secret && <SecretReveal label={`${app.name} client secret`} value={secret} />}
      </Modal>
    </>
  );
}

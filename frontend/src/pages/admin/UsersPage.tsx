import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, EMAIL_DOMAIN, EMAIL_PATTERN, errorMessage, generatePassword, type Application, type UserDetail, type UserListItem } from "../../api";
import { useFeedback } from "../../components/feedback";
import Icon from "../../components/Icon";
import { Alert, Avatar, Badge, EmptyState, Modal, PageHeader, PasswordInput, Spinner, StatusBadge, TimeAgo } from "../../components/ui";

const emptyForm = { username: "", full_name: "", email: "", password: "", is_admin: false };

const FILTERS = {
  all: { label: "All", match: () => true },
  active: { label: "Active", match: (u: UserListItem) => u.is_active },
  disabled: { label: "Disabled", match: (u: UserListItem) => !u.is_active },
  noaccess: { label: "No access", match: (u: UserListItem) => u.access.length === 0 },
  admins: { label: "Admins", match: (u: UserListItem) => u.is_admin },
} as const;
type FilterId = keyof typeof FILTERS;

export default function UsersPage() {
  const navigate = useNavigate();
  const { toast } = useFeedback();
  const [users, setUsers] = useState<UserListItem[] | null>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<FilterId>("all");
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  // System access to give the new user straight away (role ids), from the registered systems.
  const [systems, setSystems] = useState<Application[] | null>(null);
  const [roleIds, setRoleIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .get<UserListItem[]>(`/api/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`)
        .then(setUsers)
        .catch((e) => setError(errorMessage(e)));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  function openForm() {
    setForm(emptyForm);
    setRoleIds(new Set());
    setFormError("");
    setShowForm(true);
    api.get<Application[]>("/api/admin/applications").then(setSystems).catch((e) => setFormError(errorMessage(e)));
  }

  function toggleRole(id: number) {
    const next = new Set(roleIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setRoleIds(next);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setSaving(true);
    try {
      const created = await api.post<UserDetail>("/api/admin/users", { ...form, role_ids: [...roleIds] });
      toast(created.emailed
        ? `${created.username} created and emailed their sign-in details${roleIds.size ? " and system links" : ""}.`
        : `${created.username} created. Mail isn't set up: give them their sign-in details yourself.`);
      navigate(`/admin/users/${created.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
      setSaving(false);
    }
  }

  const shown = users?.filter(FILTERS[filter].match) ?? [];

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Company accounts. One account signs in to every system it holds a role in."
        actions={<button className="btn primary" onClick={openForm}><Icon name="plus" /> New user</button>}
      />
      <Alert>{error}</Alert>

      <div className="card flush">
        <div className="toolbar">
          <div className="segmented">
            {(Object.keys(FILTERS) as FilterId[]).map((id) => (
              <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>
                {FILTERS[id].label}
                {users && <span className="count">{users.filter(FILTERS[id].match).length}</span>}
              </button>
            ))}
          </div>
          <div className="search-box">
            <Icon name="search" />
            <input placeholder="Search name, username or email…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>

        {!users && !error && <Spinner />}
        {users && shown.length === 0 && (
          <EmptyState icon="users" title="No users found">{q ? "Try a different search." : "Nobody matches this filter."}</EmptyState>
        )}
        {shown.length > 0 && (
          <div className="table-wrap">
            <table className="table hover stack-sm">
              <thead>
                <tr><th>User</th><th>System access</th><th>Status</th><th className="hide-md">Last sign-in</th></tr>
              </thead>
              <tbody>
                {shown.map((u) => (
                  <tr key={u.id} onClick={() => navigate(`/admin/users/${u.id}`)} className="clickable">
                    <td>
                      <div className="person">
                        <Avatar name={u.full_name || u.username} size={34} />
                        <div>
                          <div className="person-name">
                            {u.full_name || u.username} {u.is_admin && <Badge tone="blue">Admin</Badge>}
                          </div>
                          <div className="muted small">{u.full_name && <>{u.username} · </>}{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {u.access.length === 0 ? (
                        <span className="muted small">No access</span>
                      ) : (
                        <div className="chips">
                          {u.access.map((a) => (
                            <span key={a.application_id} className="access-chip" title={`${a.application_name}: ${a.roles.join(", ")}`}>
                              <strong>{a.application_name}</strong> {a.roles.join(", ")}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td><StatusBadge active={u.is_active} /></td>
                    <td className="muted nowrap hide-md"><TimeAgo value={u.last_login_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={showForm}
        title="New user"
        width={680}
        onClose={() => setShowForm(false)}
        footer={
          <>
            <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
            <button className="btn primary" form="new-user" disabled={saving}>{saving ? "Creating…" : "Create user"}</button>
          </>
        }
      >
        <form id="new-user" className="form-grid" onSubmit={handleCreate}>
          <div className="span-2"><Alert>{formError}</Alert></div>
          <label className="span-2">
            Full name
            <input
              value={form.full_name}
              autoFocus
              required
              maxLength={255}
              placeholder="e.g. Mya Thida"
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </label>
          <label>
            Username
            <input
              value={form.username}
              required
              pattern="[A-Za-z0-9._\-]{3,100}"
              title="3–100 letters, digits, dots, underscores or dashes"
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value.toLowerCase() })}
              placeholder={`name@${EMAIL_DOMAIN}`}
              pattern={EMAIL_PATTERN}
              title={`Use a company address ending in @${EMAIL_DOMAIN}`}
              required
            />
            <span className="hint">Company address only (@{EMAIL_DOMAIN}).</span>
          </label>
          <label className="span-2">
            Initial password
            <PasswordInput
              value={form.password}
              onChange={(v) => setForm({ ...form, password: v })}
              onGenerate={() => setForm({ ...form, password: generatePassword() })}
              minLength={8}
              maxLength={72}
              required
            />
            <span className="hint">It's emailed to them with their username (when mail is set up). It's temporary: they must choose their own the first time they sign in.</span>
          </label>
          <div className="span-2">
            <div className="label">System access <span className="muted small">(optional; you can change it later)</span></div>
            {!systems && <Spinner />}
            {systems?.length === 0 && <p className="muted small">No systems registered yet.</p>}
            {systems?.filter((a) => a.roles.length > 0).map((a) => (
              <section key={a.id} className={`access-block${a.roles.some((r) => roleIds.has(r.id)) ? " granted" : ""}`}>
                <div className="access-title">
                  <Avatar name={a.name} size={24} square />
                  <strong>{a.name}</strong>
                  {!a.is_active && <Badge tone="red">System disabled</Badge>}
                </div>
                <div className="role-grid">
                  {a.roles.map((role) => (
                    <label key={role.id} className={`role-tile${roleIds.has(role.id) ? " on" : ""}`}>
                      <input type="checkbox" checked={roleIds.has(role.id)} onChange={() => toggleRole(role.id)} />
                      <span>
                        <span className="role-name">{role.name}</span>
                        {role.description && <span className="role-desc">{role.description}</span>}
                      </span>
                    </label>
                  ))}
                </div>
              </section>
            ))}
            <span className="hint">The welcome email lists these systems with their links.</span>
          </div>
          <label className="check span-2">
            <input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} />
            <span>
              Portal administrator
              <span className="hint">Can manage all users, systems and roles.</span>
            </span>
          </label>
        </form>
      </Modal>
    </>
  );
}

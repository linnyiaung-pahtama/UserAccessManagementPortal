import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, errorMessage, type Application, type Permission } from "../../api";
import { useFeedback } from "../../components/feedback";
import Icon from "../../components/Icon";
import { Alert, Badge, EmptyState } from "../../components/ui";

type Grid = Map<number, Set<number>>; // role id → permission ids

function gridFrom(app: Application): Grid {
  return new Map(app.roles.map((r) => [r.id, new Set(r.permission_ids)]));
}

export default function PermissionsTab({ app, onChanged }: { app: Application; onChanged: () => Promise<void> }) {
  const { toast, confirm } = useFeedback();
  const [grid, setGrid] = useState<Grid>(() => gridFrom(app));
  const [saving, setSaving] = useState(false);
  const [newPerm, setNewPerm] = useState({ name: "", description: "" });
  const [editing, setEditing] = useState<Permission | null>(null);
  const [error, setError] = useState("");

  useEffect(() => setGrid(gridFrom(app)), [app]);

  const changes = useMemo(() => {
    const list: { role: string; perm: string; added: boolean }[] = [];
    const permName = new Map(app.permissions.map((p) => [p.id, p.name]));
    for (const role of app.roles) {
      const before = new Set(role.permission_ids);
      const after = grid.get(role.id) ?? new Set<number>();
      after.forEach((p) => !before.has(p) && list.push({ role: role.name, perm: permName.get(p) ?? "?", added: true }));
      before.forEach((p) => !after.has(p) && list.push({ role: role.name, perm: permName.get(p) ?? "?", added: false }));
    }
    return list;
  }, [app, grid]);
  const dirty = changes.length > 0;

  function toggle(roleId: number, permId: number) {
    setGrid((prev) => {
      const next = new Map(prev);
      const set = new Set(next.get(roleId));
      if (set.has(permId)) set.delete(permId);
      else set.add(permId);
      next.set(roleId, set);
      return next;
    });
  }

  async function saveGrid() {
    setSaving(true);
    const changed = app.roles.filter((r) => {
      const after = grid.get(r.id) ?? new Set<number>();
      return after.size !== r.permission_ids.length || r.permission_ids.some((p) => !after.has(p));
    });
    try {
      await api.put(`/api/admin/applications/${app.id}/role-permissions`, {
        roles: Object.fromEntries(changed.map((r) => [r.id, [...(grid.get(r.id) ?? [])]])),
      });
      await onChanged();
      toast(`Permissions updated. Users get them at their next sign-in or token refresh.`);
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  }

  async function addPermission(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/api/admin/applications/${app.id}/permissions`, newPerm);
      toast(`Permission "${newPerm.name}" added. Now choose which roles grant it.`);
      setNewPerm({ name: "", description: "" });
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function savePermission(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const original = app.permissions.find((p) => p.id === editing.id);
    if (original && original.name !== editing.name) {
      const ok = await confirm({
        title: `Rename "${original.name}"?`,
        message: <>{app.name}'s code checks for permission names. Renaming it to <code>{editing.name}</code> without updating the code will make those checks fail for everyone.</>,
        confirmLabel: "Rename permission",
        danger: true,
      });
      if (!ok) return;
    }
    setError("");
    try {
      await api.patch(`/api/admin/applications/${app.id}/permissions/${editing.id}`, {
        name: editing.name, description: editing.description,
      });
      setEditing(null);
      toast("Permission updated");
      await onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function deletePermission(p: Permission) {
    const roles = app.roles.filter((r) => r.permission_ids.includes(p.id)).map((r) => r.name);
    const ok = await confirm({
      title: `Delete permission "${p.name}"?`,
      message: roles.length
        ? <>It's also removed from <strong>{roles.join(", ")}</strong>. It can only be deleted while nobody holds it through those roles.</>
        : "No role grants it yet.",
      confirmLabel: "Delete permission",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/admin/applications/${app.id}/permissions/${p.id}`);
      toast(`Permission "${p.name}" deleted`);
      await onChanged();
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  return (
    <div className={dirty ? "has-save-bar" : ""}>
      <div className="card flush">
        <div className="card-pad">
          <h2>Role permissions</h2>
          <p className="muted small">
            Tick what each role can do in {app.name}. A user gets every permission of every role they hold here,
            sent in the <code>permissions</code> claim of their token.
          </p>
        </div>
        {app.permissions.length === 0 || app.roles.length === 0 ? (
          <EmptyState icon="shield" title={app.permissions.length === 0 ? "No permissions yet" : "No roles yet"}>
            {app.permissions.length === 0 ? "Add the permissions this system checks, below." : "Add roles on the Roles tab first."}
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table matrix">
              <thead>
                <tr>
                  <th>Permission</th>
                  {app.roles.map((r) => (
                    <th key={r.id} className="matrix-col" title={r.description}>
                      {r.name}
                      <span className="count">{grid.get(r.id)?.size ?? 0}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {app.permissions.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <div className="role-name">{p.name}</div>
                      {p.description && <div className="muted small">{p.description}</div>}
                    </td>
                    {app.roles.map((r) => {
                      const on = grid.get(r.id)?.has(p.id) ?? false;
                      const changed = on !== r.permission_ids.includes(p.id);
                      return (
                        <td key={r.id} className={`matrix-cell${changed ? " changed" : ""}`}>
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={() => toggle(r.id, p.id)}
                            aria-label={`${r.name} can ${p.name}`}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card flush" style={{ marginTop: 20 }}>
        <div className="card-pad">
          <h2>Permissions</h2>
          <p className="muted small">
            The actions {app.name}'s code checks for, such as <code>reports.view</code>. Names must match the code exactly.
          </p>
          <Alert>{error}</Alert>
        </div>
        {app.permissions.length > 0 && (
          <ul className="list bordered">
            {app.permissions.map((p) =>
              editing?.id === p.id ? (
                <li key={p.id} className="list-pad">
                  <form className="inline-form" onSubmit={savePermission}>
                    <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value.toLowerCase() })} required autoFocus pattern="[A-Za-z0-9._:\-]{1,100}" />
                    <input value={editing.description} placeholder="Description" onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
                    <button className="btn small primary">Save</button>
                    <button type="button" className="btn small ghost" onClick={() => setEditing(null)}>Cancel</button>
                  </form>
                </li>
              ) : (
                <li key={p.id} className="list-pad role-row">
                  <div className="grow">
                    <div className="role-name">{p.name}</div>
                    <div className="muted small">{p.description || "No description"}</div>
                  </div>
                  <div className="chips">
                    {app.roles.filter((r) => r.permission_ids.includes(p.id)).map((r) => <Badge key={r.id}>{r.name}</Badge>)}
                  </div>
                  <div className="row-actions">
                    <button className="btn small ghost icon-btn" title="Edit permission" onClick={() => setEditing(p)}><Icon name="edit" size={14} /></button>
                    <button className="btn small ghost icon-btn danger-text" title="Delete permission" onClick={() => deletePermission(p)}><Icon name="trash" size={14} /></button>
                  </div>
                </li>
              ),
            )}
          </ul>
        )}
        <form className="inline-form card-pad add-row" onSubmit={addPermission}>
          <input placeholder="New permission, e.g. invoices.approve" value={newPerm.name} onChange={(e) => setNewPerm({ ...newPerm, name: e.target.value.toLowerCase() })} required pattern="[a-z0-9._:\-]{1,100}" title="Lowercase letters, digits and . _ : -" />
          <input placeholder="What it allows (optional)" value={newPerm.description} onChange={(e) => setNewPerm({ ...newPerm, description: e.target.value })} />
          <button className="btn primary"><Icon name="plus" /> Add permission</button>
        </form>
      </div>

      {dirty && (
        <div className="save-bar">
          <div className="save-bar-changes">
            <strong>Unsaved permission changes</strong>
            <div className="chips">
              {changes.map((c, i) => (
                <Badge key={i} tone={c.added ? "green" : "red"}>{c.added ? "+" : "−"} {c.role}: {c.perm}</Badge>
              ))}
            </div>
          </div>
          <div className="row">
            <button className="btn ghost" onClick={() => setGrid(gridFrom(app))}>Discard</button>
            <button className="btn primary" onClick={saveGrid} disabled={saving}>{saving ? "Saving…" : "Save permissions"}</button>
          </div>
        </div>
      )}
    </div>
  );
}

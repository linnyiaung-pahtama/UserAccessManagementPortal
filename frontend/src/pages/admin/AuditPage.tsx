import { useEffect, useState } from "react";
import { api, errorMessage, type AuditEntry } from "../../api";
import Icon from "../../components/Icon";
import { Alert, Avatar, EmptyState, PageHeader, Spinner, TimeAgo } from "../../components/ui";

const LABELS: Record<string, string> = {
  login: "signed in to the portal",
  "login.failed": "failed to sign in as",
  logout: "signed out",
  "sso.authorize": "signed in to",
  "sso.denied": "was denied access to",
  "user.create": "created user",
  "user.update": "updated user",
  "user.delete": "deleted user",
  "user.roles": "changed access for",
  "user.password_changed": "changed their password",
  "app.create": "registered system",
  "app.update": "updated system",
  "app.delete": "deleted system",
  "app.rotate_secret": "rotated the client secret of",
  "role.create": "added role",
  "role.update": "updated role",
  "role.delete": "deleted role",
  "role.permissions": "changed role permissions in",
  "permission.create": "added permission",
  "permission.update": "updated permission",
  "permission.delete": "deleted permission",
  "access.request": "requested access:",
  "access.approve": "approved the access request of",
  "access.decline": "declined the access request of",
};
// Actions where the target is the actor themselves.
const SELF_ACTIONS = new Set(["login", "logout", "user.password_changed"]);

export function describe(e: AuditEntry): { verb: string; target: string } {
  return { verb: LABELS[e.action] ?? e.action, target: SELF_ACTIONS.has(e.action) ? "" : e.target };
}

export function actionTone(action: string): "red" | "green" | "blue" | "neutral" {
  if (action.endsWith("failed") || action.endsWith("denied") || action.endsWith("delete")) return "red";
  if (action === "login" || action === "sso.authorize") return "green";
  if (action === "user.roles" || action.startsWith("role.") || action.startsWith("permission.")) return "blue";
  return "neutral";
}

const FILTERS = {
  all: { label: "All", match: () => true },
  signin: { label: "Sign-ins", match: (a: string) => a.startsWith("login") || a === "logout" || a.startsWith("sso.") },
  access: { label: "Access changes", match: (a: string) => a === "user.roles" || a.startsWith("role.") || a.startsWith("permission.") },
  admin: { label: "Users & systems", match: (a: string) => (a.startsWith("user.") && a !== "user.roles") || a.startsWith("app.") || a.startsWith("access.") },
  problems: { label: "Problems", match: (a: string) => a.endsWith("failed") || a.endsWith("denied") },
} as const;
type FilterId = keyof typeof FILTERS;

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<FilterId>("all");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .get<AuditEntry[]>(`/api/admin/audit?limit=500${q ? `&q=${encodeURIComponent(q)}` : ""}`)
        .then(setEntries)
        .catch((e) => setError(errorMessage(e)));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  const shown = entries?.filter((e) => FILTERS[filter].match(e.action)) ?? [];

  return (
    <>
      <PageHeader title="Audit log" subtitle="Sign-ins, SSO grants and every change to users, systems and roles." />
      <Alert>{error}</Alert>
      <div className="card flush">
        <div className="toolbar">
          <div className="segmented">
            {(Object.keys(FILTERS) as FilterId[]).map((id) => (
              <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>
                {FILTERS[id].label}
                {entries && <span className="count">{entries.filter((e) => FILTERS[id].match(e.action)).length}</span>}
              </button>
            ))}
          </div>
          <div className="search-box">
            <Icon name="search" />
            <input placeholder="Search user, system or action…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>

        {!entries && !error && <Spinner />}
        {entries && shown.length === 0 && <EmptyState icon="activity" title="No matching events" />}
        {shown.length > 0 && (
          <div className="table-wrap">
            <table className="table stack-sm">
              <thead>
                <tr><th>When</th><th>Event</th><th>Detail</th><th className="hide-sm">IP</th></tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const { verb, target } = describe(e);
                  return (
                    <tr key={e.id}>
                      <td className="nowrap muted"><TimeAgo value={e.created_at} /></td>
                      <td>
                        <div className="event">
                          <span className={`dot ${actionTone(e.action)}`} />
                          {e.actor_username ? <Avatar name={e.actor_username} size={22} /> : null}
                          <span>
                            <strong>{e.actor_username || "Someone"}</strong> <span className="muted">{verb}</span> {target && <strong>{target}</strong>}
                          </span>
                        </div>
                      </td>
                      <td className="muted">{e.detail}</td>
                      <td className="muted small hide-sm">{e.ip}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

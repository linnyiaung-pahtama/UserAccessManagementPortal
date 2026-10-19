import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, generatePassword, type AccessRequest } from "../../api";
import { useFeedback } from "../../components/feedback";
import { Alert, Badge, EmptyState, Modal, PageHeader, PasswordInput, Spinner, TimeAgo } from "../../components/ui";

/** Tells the sidebar to refresh its open-requests count. */
export const REQUESTS_CHANGED = "access-requests-changed";

const FILTERS = {
  open: { label: "Open", match: (r: AccessRequest) => r.status === "open" },
  approved: { label: "Approved", match: (r: AccessRequest) => r.status === "approved" },
  declined: { label: "Declined", match: (r: AccessRequest) => r.status === "declined" },
  all: { label: "All", match: () => true },
} as const;
type FilterId = keyof typeof FILTERS;

const STATUS_TONE = { open: "amber", approved: "green", declined: "neutral" } as const;

/** A username suggestion from the email: the part before @, with only the allowed characters. */
function usernameFrom(email: string): string {
  return email.split("@")[0].replace(/[^A-Za-z0-9._-]/g, "").slice(0, 100);
}

export default function AccessRequestsPage() {
  const { toast } = useFeedback();
  const [requests, setRequests] = useState<AccessRequest[] | null>(null);
  const [filter, setFilter] = useState<FilterId>("open");
  const [error, setError] = useState("");

  const [approving, setApproving] = useState<AccessRequest | null>(null);
  const [form, setForm] = useState({ role_id: "", username: "", password: "" });
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [declining, setDeclining] = useState<AccessRequest | null>(null);
  const [reason, setReason] = useState("");

  async function refresh() {
    setRequests(await api.get<AccessRequest[]>("/api/admin/access-requests"));
    window.dispatchEvent(new Event(REQUESTS_CHANGED));
  }

  useEffect(() => {
    refresh().catch((e) => setError(errorMessage(e)));
  }, []);

  function openApprove(r: AccessRequest) {
    setForm({
      role_id: r.roles.length === 1 ? String(r.roles[0].id) : "",
      username: r.user_id ? "" : usernameFrom(r.email),
      password: "",
    });
    setFormError("");
    setApproving(r);
  }

  async function handleApprove(e: FormEvent) {
    e.preventDefault();
    if (!approving) return;
    setFormError("");
    setSaving(true);
    try {
      const body = approving.user_id
        ? { role_id: Number(form.role_id) }
        : { role_id: Number(form.role_id), username: form.username, password: form.password };
      const done = await api.post<AccessRequest>(`/api/admin/access-requests/${approving.id}/approve`, body);
      const told = approving.user_id
        ? done.emailed ? "They're emailed." : "Mail isn't set up: let them know yourself."
        : done.emailed
          ? "Their username and temporary password are emailed to them."
          : "Mail isn't set up: give them their username and temporary password yourself.";
      toast(`${done.username} ${approving.user_id ? "now has" : "created with"} access to ${done.application_name}. ${told}`);
      setApproving(null);
      await refresh();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDecline(e: FormEvent) {
    e.preventDefault();
    if (!declining) return;
    setSaving(true);
    try {
      const done = await api.post<AccessRequest>(`/api/admin/access-requests/${declining.id}/decline`, { reason });
      toast(done.emailed
        ? `Request declined. ${declining.email} is emailed${reason.trim() ? " with your reason" : ""}.`
        : "Request declined. Mail isn't set up, so they aren't emailed.");
      setDeclining(null);
      await refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  }

  const shown = requests?.filter(FILTERS[filter].match) ?? [];

  return (
    <>
      <PageHeader
        title="Access requests"
        subtitle="People asking for access from the sign-in page. Approve to create their account (if needed) and give a role."
      />
      <Alert>{error}</Alert>

      <div className="card flush">
        <div className="toolbar">
          <div className="segmented">
            {(Object.keys(FILTERS) as FilterId[]).map((id) => (
              <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>
                {FILTERS[id].label}
                {requests && <span className="count">{requests.filter(FILTERS[id].match).length}</span>}
              </button>
            ))}
          </div>
        </div>

        {!requests && !error && <Spinner />}
        {requests && shown.length === 0 && (
          <EmptyState icon="inbox" title={filter === "open" ? "No open requests" : "No requests here"} />
        )}
        {shown.length > 0 && (
          <div className="table-wrap">
            <table className="table stack-sm">
              <thead>
                <tr><th>Email</th><th>System</th><th>Account</th><th className="hide-md">Requested</th><th>Status</th><th /></tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id}>
                    <td><strong>{r.email}</strong></td>
                    <td>{r.application_name}</td>
                    <td>
                      {r.user_id ? (
                        <>
                          <Link to={`/admin/users/${r.user_id}`}>{r.username}</Link>{" "}
                          {r.user_active === false && <Badge tone="red">Disabled</Badge>}
                          {r.current_roles.length > 0 && <div className="muted small">Has: {r.current_roles.join(", ")}</div>}
                        </>
                      ) : (
                        <span className="muted small">No account yet</span>
                      )}
                    </td>
                    <td className="muted nowrap hide-md"><TimeAgo value={r.created_at} /></td>
                    <td>
                      <Badge tone={STATUS_TONE[r.status]}>{r.status[0].toUpperCase() + r.status.slice(1)}</Badge>
                      {r.handled_by && <div className="muted small">by {r.handled_by}</div>}
                      {r.reason && <div className="muted small" title={r.reason}>Reason: {r.reason}</div>}
                    </td>
                    <td className="nowrap">
                      {r.status === "open" && (
                        <div className="row">
                          <button className="btn primary small" onClick={() => openApprove(r)}>Approve</button>
                          <button className="btn small" onClick={() => { setReason(""); setDeclining(r); }}>Decline</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={!!approving}
        title={`Approve access to ${approving?.application_name ?? ""}`}
        onClose={() => setApproving(null)}
        footer={
          <>
            <button className="btn" onClick={() => setApproving(null)}>Cancel</button>
            <button className="btn primary" form="approve-request" disabled={saving}>
              {saving ? "Approving…" : approving?.user_id ? "Give access" : "Create user and give access"}
            </button>
          </>
        }
      >
        {approving && (
          <form id="approve-request" className="form-grid" onSubmit={handleApprove}>
            <div className="span-2"><Alert>{formError}</Alert></div>
            <p className="span-2 muted small">
              {approving.user_id ? (
                <>
                  <strong>{approving.email}</strong> already has an account (<strong>{approving.username}</strong>). Choose the role to add.
                  {approving.user_active === false && " The account is disabled: turn it on from the user's page too."}
                </>
              ) : (
                <>There is no account for <strong>{approving.email}</strong> yet. This creates it.</>
              )}
            </p>
            {!approving.user_id && (
              <>
                <label className="span-2">
                  Username
                  <input
                    value={form.username}
                    required
                    pattern="[A-Za-z0-9._\-]{3,100}"
                    title="3–100 letters, digits, dots, underscores or dashes"
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                  />
                </label>
                <label className="span-2">
                  Temporary password
                  <PasswordInput
                    value={form.password}
                    onChange={(v) => setForm({ ...form, password: v })}
                    onGenerate={() => setForm({ ...form, password: generatePassword() })}
                    minLength={8}
                    maxLength={72}
                    required
                  />
                  <span className="hint">It's emailed to them with their username (when mail is set up). They choose their own the first time they sign in.</span>
                </label>
              </>
            )}
            <label className="span-2">
              Role in {approving.application_name}
              <select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })} required>
                <option value="" disabled>{approving.roles.length ? "Choose a role" : "This system has no roles yet"}</option>
                {approving.roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}{approving.current_roles.includes(role.name) ? " (already has it)" : ""}
                  </option>
                ))}
              </select>
            </label>
          </form>
        )}
      </Modal>
      <Modal
        open={!!declining}
        title="Decline this request?"
        onClose={() => setDeclining(null)}
        footer={
          <>
            <button className="btn" onClick={() => setDeclining(null)}>Cancel</button>
            <button className="btn danger" form="decline-request" disabled={saving}>{saving ? "Declining…" : "Decline"}</button>
          </>
        }
      >
        {declining && (
          <form id="decline-request" className="form-grid" onSubmit={handleDecline}>
            <p className="span-2 muted small">
              <strong>{declining.email}</strong> won't get access to {declining.application_name}. They're emailed that the request was declined.
            </p>
            <label className="span-2">
              Reason (optional)
              <textarea className="prose" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={3} autoFocus />
              <span className="hint">If you write one, it's included in the email.</span>
            </label>
          </form>
        )}
      </Modal>
    </>
  );
}
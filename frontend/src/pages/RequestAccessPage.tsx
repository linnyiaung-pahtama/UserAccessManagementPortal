import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, EMAIL_DOMAIN, EMAIL_PATTERN, errorMessage, type RequestableSystem } from "../api";
import Icon from "../components/Icon";
import { Alert } from "../components/ui";
import { safeNext } from "./LoginPage";

/** The client_id of the system that sent the person to sign in (next=/oauth/authorize?client_id=...), if any. */
function clientIdFrom(next: string | null): string | null {
  if (!next?.startsWith("/oauth/")) return null;
  return new URLSearchParams(next.split("?")[1] ?? "").get("client_id");
}

export default function RequestAccessPage() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const backToLogin = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  const [systems, setSystems] = useState<RequestableSystem[] | null>(null);
  const [email, setEmail] = useState("");
  const [systemId, setSystemId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    api
      .get<RequestableSystem[]>("/api/access-requests/systems")
      .then((list) => {
        setSystems(list);
        const from = list.find((s) => s.client_id === clientIdFrom(next));
        if (from) setSystemId(String(from.id));
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.post("/api/access-requests", { email, application_id: Number(systemId) });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const systemName = systems?.find((s) => String(s.id) === systemId)?.name;

  return (
    <div className="auth-page">
      <aside className="auth-hero">
        <div className="brand light">
          <span className="brand-logo"><Icon name="shield" size={16} /></span>
          Access Portal
        </div>
        <div>
          <h2>Ask for access to a company system.</h2>
          <ul className="hero-points">
            <li><Icon name="check" /> Tell us your company email and the system</li>
            <li><Icon name="check" /> An administrator reviews your request</li>
            <li><Icon name="check" /> They'll contact you with your sign-in details</li>
          </ul>
        </div>
        <div className="hero-foot">Need help? Contact your IT administrator.</div>
      </aside>

      <main className="auth-main">
        {sent ? (
          <div className="auth-form">
            <h1>Request sent</h1>
            <p className="muted">
              Your request for {systemName ?? "access"} has been sent to the administrators. They'll review it and
              contact you at <strong>{email}</strong>.
            </p>
            <Link className="btn block large" to={backToLogin}>Back to sign in</Link>
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <h1>Request access</h1>
            <p className="muted">An administrator will review your request.</p>
            <Alert>{error}</Alert>
            <label>
              Company email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value.toLowerCase())}
                placeholder={`name@${EMAIL_DOMAIN}`}
                pattern={EMAIL_PATTERN}
                title={`Use your company address ending in @${EMAIL_DOMAIN}`}
                autoFocus
                autoComplete="email"
                required
              />
            </label>
            <label>
              System
              <select value={systemId} onChange={(e) => setSystemId(e.target.value)} required disabled={!systems}>
                <option value="" disabled>{systems ? "Choose a system" : "Loading…"}</option>
                {systems?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <button className="btn primary block large" disabled={busy || !systems}>
              {busy ? <><span className="spinner light" /> Sending…</> : "Send request"}
            </button>
            <p className="auth-alt">
              Already have an account? <Link to={backToLogin}>Sign in</Link>
            </p>
          </form>
        )}
      </main>
    </div>
  );
}

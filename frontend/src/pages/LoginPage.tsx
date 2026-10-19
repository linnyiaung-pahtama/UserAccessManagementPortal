import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api";
import { useAuth } from "../auth";
import Icon from "../components/Icon";
import { Alert, PasswordInput } from "../components/ui";

/** Only same-origin relative paths are accepted, to prevent open redirects. */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  return next;
}

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  const fromSystem = next?.startsWith("/oauth/") ?? false;

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function proceed() {
    // OIDC requests continue on the backend, so they need a full page load.
    if (fromSystem && next) window.location.assign(next);
    else navigate(next || "/", { replace: true });
  }

  useEffect(() => {
    if (!loading && user) proceed();
  }, [loading, user]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <aside className="auth-hero">
        <div className="brand light">
          <span className="brand-logo"><Icon name="shield" size={16} /></span>
          Access Portal
        </div>
        <div>
          <h2>One account for every company system.</h2>
          <ul className="hero-points">
            <li><Icon name="check" /> Sign in once, open all your systems</li>
            <li><Icon name="check" /> Access managed centrally by IT</li>
            <li><Icon name="check" /> Every sign-in and change is audited</li>
          </ul>
        </div>
        <div className="hero-foot">Need help? Contact your IT administrator.</div>
      </aside>

      <main className="auth-main">
        <form className="auth-form" onSubmit={handleSubmit}>
          <h1>Sign in</h1>
          <p className="muted">
            {fromSystem
              ? "Sign in to continue to the system you requested. You'll only need to do this once."
              : "Use your company account."}
          </p>
          <Alert>{error}</Alert>
          <label>
            Username or email
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" required />
          </label>
          <label>
            Password
            <PasswordInput value={password} onChange={setPassword} autoComplete="current-password" required />
          </label>
          <button className="btn primary block large" disabled={busy}>
            {busy ? <><span className="spinner light" /> Signing in…</> : "Sign in"}
          </button>
          <p className="auth-alt">
            Don't have access? <Link to={next ? `/request-access?next=${encodeURIComponent(next)}` : "/request-access"}>Request access</Link>
          </p>
        </form>
      </main>
    </div>
  );
}

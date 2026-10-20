import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api";
import { useAuth } from "../auth";
import Icon from "../components/Icon";
import { Alert, PasswordInput } from "../components/ui";
import { safeNext } from "./LoginPage";

/**
 * First sign-in with a password an admin set (new account or reset). The user must choose their own
 * before going anywhere: the portal guards its pages with RequireAuth, and /oauth/authorize sends
 * systems' sign-ins here too, with `next` pointing back to it so the sign-in finishes afterwards.
 */
export default function ChangePasswordPage() {
  const { user, loading, logout, changePassword } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));

  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const done = !loading && !!user && !user.must_change_password;
  const toSystem = next?.startsWith("/oauth/") ?? false;

  useEffect(() => {
    // A system's sign-in continues on the backend, so it needs a full page load.
    if (done && toSystem && next) window.location.replace(next);
  }, [done, toSystem, next]);

  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Navigate to={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} replace />;
  // Nothing to change (or just changed): carry on to where they were going.
  if (done) return toSystem ? <div className="center muted">Continuing…</div> : <Navigate to={next || "/"} replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== confirm) return setError("The new passwords don't match.");
    setBusy(true);
    try {
      await changePassword(current, password); // clears the flag, so the next render carries on
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="auth-page">
      <aside className="auth-hero">
        <div className="brand light">
          <span className="brand-logo"><Icon name="shield" size={16} /></span>
          Access Portal
        </div>
        <div>
          <h2>Make it yours.</h2>
          <ul className="hero-points">
            <li><Icon name="check" /> Your administrator set a temporary password</li>
            <li><Icon name="check" /> Choose your own once, here</li>
            <li><Icon name="check" /> It then works for every company system</li>
          </ul>
        </div>
        <div className="hero-foot">Need help? Contact your IT administrator.</div>
      </aside>

      <main className="auth-main">
        <form className="auth-form" onSubmit={handleSubmit}>
          <h1>Choose your password</h1>
          <p className="muted">
            Hi {user.full_name || user.username}. You signed in with a temporary password. Choose your own to continue.
          </p>
          <Alert>{error}</Alert>
          <label>
            Temporary password
            <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" autoFocus required />
          </label>
          <label>
            New password
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" minLength={8} maxLength={72} required />
            <span className="hint">At least 8 characters, different from the temporary one.</span>
          </label>
          <label>
            Confirm new password
            <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" required />
          </label>
          <button className="btn primary block large" disabled={busy}>
            {busy ? <><span className="spinner light" /> Saving…</> : "Save and continue"}
          </button>
          <button type="button" className="btn ghost block" onClick={signOut} style={{ marginTop: 8 }}>
            Sign out
          </button>
        </form>
      </main>
    </div>
  );
}

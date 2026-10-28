import { useState, FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const FEATURES = [
  { icon: "🗺", title: "Origins map", body: "See recorded family birthplaces on a world map." },
  { icon: "🌀", title: "Family tree", body: "Follow family relationships generation by generation, and center the tree on anyone." },
  { icon: "↗", title: "Migration paths", body: "See where recorded immigrant ancestors came from and settled." },
  { icon: "🧭", title: "Research hints", body: "Find missing people and places in the file you imported." },
];

export default function LoginPage() {
  const { user, loading, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from;
  const returnTo = typeof from === "string" && from.startsWith("/") &&
    !from.startsWith("//") && !/[\\\u0000-\u001f]/.test(from) && !/^\/login(?:[/?#]|$)/.test(from)
    ? from : "/";

  if (!loading && user) return <Navigate to={returnTo} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, invite || undefined);
      navigate(returnTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-hero">
      <div className="auth-pitch">
        <h1>Kinwhere</h1>
        <p className="auth-tagline">
          Explore the paths that brought you here.
        </p>
        <p>
          Import a family tree file to explore a map of your ancestry, follow family relationships,
          see migration paths, and find information to research next.
        </p>
        <div className="features">
          {FEATURES.map((f) => (
            <div className="feature" key={f.title}>
              <span className="feature-icon">{f.icon}</span>
              <div>
                <div className="feature-title">{f.title}</div>
                <div className="sub" style={{ margin: 0 }}>
                  {f.body}
                </div>
              </div>
            </div>
          ))}
        </div>
        <p className="sub" style={{ marginTop: 4 }}>
          🔒 Your data stays private to you. This site never asks for or sees your FamilySearch password —
          you export the file yourself and upload only that.
        </p>
      </div>

      <div className="auth-card-wrap">
        <div className="card">
          <h2>Local app account</h2>
          <p className="auth-help sub">This account belongs to this Kinwhere installation. It is separate from FamilySearch.</p>
          <p className="auth-first-time">First visit? Create an account to save and explore your trees.</p>
          <div className="auth-mode-switch" style={{ display: "flex", gap: 6, marginBottom: 14 }}>
            <button
              className={mode === "login" ? "btn-primary" : ""}
              style={{ flex: 1 }}
              disabled={busy}
              aria-pressed={mode === "login"}
              onClick={() => { setMode("login"); setError(null); }}
            >
              Sign in
            </button>
            <button
              className={mode === "register" ? "btn-primary" : ""}
              style={{ flex: 1 }}
              disabled={busy}
              aria-pressed={mode === "register"}
              onClick={() => { setMode("register"); setError(null); }}
            >
              Create account
            </button>
          </div>
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="account-email">Email</label>
              <input id="account-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="account-password">Password {mode === "register" && "(min 8 characters)"}</label>
              <input
                id="account-password"
                type="password"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {mode === "register" && (
              <>
                <p className="sub">Create an account on this installation. Use a separate password from FamilySearch.</p>
                <details>
                  <summary>Have an installation invite code?</summary>
                  <div className="field" style={{ marginTop: 8 }}>
                    <label htmlFor="invite-code">Invite code</label>
                    <input id="invite-code" type="text" value={invite} onChange={(e) => setInvite(e.target.value)} />
                    <span style={{ marginTop: 4 }}>
                      Local installations do not require one by default. Only enter a code if the person running this installation supplied it.
                    </span>
                  </div>
                </details>
              </>
            )}
            <button className="btn-primary" type="submit" disabled={busy || loading} style={{ marginTop: 8, width: "100%" }}>
              {loading ? "Checking account…" : busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
          {error && <div className="err" role="alert">{error}</div>}
          <details className="account-recovery">
            <summary>Forgot your password?</summary>
            <p className="sub">This installation sends no email, including password reset messages. The person running it can reset your local account password using Account recovery in the self-hosting guide. Your saved trees stay with your account.</p>
          </details>
        </div>
      </div>
    </div>
  );
}

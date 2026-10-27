import { useState, FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const FEATURES = [
  { icon: "🗺", title: "Origins map", body: "See where every ancestral line was born, clustered across the world." },
  { icon: "🌀", title: "Re-rootable fan chart", body: "Spin your pedigree out generation by generation, re-center on anyone." },
  { icon: "↗", title: "Migration paths", body: "Trace each immigrant from the Old World to where they first settled." },
  { icon: "🧭", title: "An honest read", body: "Exactly where each line goes cold — pull walls vs. true dead-ends." },
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

  if (!loading && user) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, invite || undefined);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-hero">
      <div className="auth-pitch">
        <h1>Where did your family come from?</h1>
        <p className="auth-tagline">
          Upload a GEDCOM and get an interactive map of your ancestry, a re-rootable fan chart, migration
          paths, and an honest read on where each line goes cold.
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
          <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
            <button
              className={mode === "login" ? "btn-primary" : ""}
              style={{ flex: 1 }}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              className={mode === "register" ? "btn-primary" : ""}
              style={{ flex: 1 }}
              onClick={() => setMode("register")}
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
            <button className="btn-primary" type="submit" disabled={busy} style={{ marginTop: 8, width: "100%" }}>
              {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
          {error && <div className="err">{error}</div>}
        </div>
      </div>
    </div>
  );
}

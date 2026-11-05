import { useState } from "react";
import { USERS } from "../auth/roles";
import { C } from "../styles/theme";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [showPass, setShowPass] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    await new Promise(r => setTimeout(r, 700));
    const user = USERS.find(u => u.username === username.trim() && u.password === password);
    if (user) {
      onLogin(user);
    } else {
      setError("Invalid username or password. Please try again.");
      setLoading(false);
    }
  };

  const quickLogin = (user) => {
    setUsername(user.username);
    setPassword(user.password);
    setError("");
  };

  return (
    <div style={{
      minHeight: "100vh", width: "100vw",
      background: "linear-gradient(135deg, #0a0e1a 0%, #111827 50%, #0f1929 100%)",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      padding: 20,
    }}>
      {/* Background grid pattern */}
      <div style={{
        position: "fixed", inset: 0, opacity: 0.03,
        backgroundImage: "linear-gradient(#e2e8f0 1px, transparent 1px), linear-gradient(90deg, #e2e8f0 1px, transparent 1px)",
        backgroundSize: "40px 40px",
        pointerEvents: "none",
      }} />

      <div style={{ width: "100%", maxWidth: 420, position: "relative", zIndex: 1 }}>

        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 14,
            background: "linear-gradient(135deg, #f59e0b, #f97316)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 26, margin: "0 auto 14px",
            boxShadow: "0 4px 20px rgba(245,158,11,0.4)",
          }}>◈</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0", letterSpacing: "0.04em" }}>
            SEMANTIC DIGITAL TWIN
          </div>
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 4, letterSpacing: "0.08em" }}>
            Supply Chain Intelligence Platform
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: "#111827",
          border: "1px solid #1e2d45",
          borderRadius: 16,
          padding: 32,
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0", marginBottom: 4 }}>
            Sign in to your account
          </div>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 24 }}>
            Enter your credentials to access the platform
          </div>

          <form onSubmit={handleLogin}>
            {/* Username */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 11, color: "#94a3b8", display: "block", marginBottom: 6, letterSpacing: "0.06em" }}>
                USERNAME
              </label>
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                style={{
                  width: "100%", padding: "10px 14px",
                  background: "#0a0e1a", border: `1px solid ${error ? "#ef4444" : "#1e2d45"}`,
                  borderRadius: 8, color: "#e2e8f0", fontSize: 13,
                  outline: "none", fontFamily: "inherit",
                  boxSizing: "border-box", transition: "border-color 0.15s",
                }}
                onFocus={e => e.target.style.borderColor = "#f59e0b"}
                onBlur={e => e.target.style.borderColor = error ? "#ef4444" : "#1e2d45"}
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, color: "#94a3b8", display: "block", marginBottom: 6, letterSpacing: "0.06em" }}>
                PASSWORD
              </label>
              <div style={{ position: "relative" }}>
                <input
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  style={{
                    width: "100%", padding: "10px 40px 10px 14px",
                    background: "#0a0e1a", border: `1px solid ${error ? "#ef4444" : "#1e2d45"}`,
                    borderRadius: 8, color: "#e2e8f0", fontSize: 13,
                    outline: "none", fontFamily: "inherit",
                    boxSizing: "border-box", transition: "border-color 0.15s",
                  }}
                  onFocus={e => e.target.style.borderColor = "#f59e0b"}
                  onBlur={e => e.target.style.borderColor = error ? "#ef4444" : "#1e2d45"}
                />
                <button type="button" onClick={() => setShowPass(s => !s)}
                  style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#64748b", fontSize: 13 }}>
                  {showPass ? "🙈" : "👁"}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div style={{ marginBottom: 16, padding: "8px 12px", background: "#ef444422", border: "1px solid #ef444444", borderRadius: 6, fontSize: 11, color: "#ef4444" }}>
                ⚠ {error}
              </div>
            )}

            {/* Submit */}
            <button type="submit" disabled={loading || !username || !password}
              style={{
                width: "100%", padding: "11px",
                background: loading || !username || !password ? "#1e2d45" : "linear-gradient(135deg, #f59e0b, #f97316)",
                border: "none", borderRadius: 8,
                color: loading || !username || !password ? "#64748b" : "#000",
                fontSize: 13, fontWeight: 700, cursor: loading || !username || !password ? "not-allowed" : "pointer",
                fontFamily: "inherit", letterSpacing: "0.04em",
                transition: "all 0.15s",
                boxShadow: loading || !username || !password ? "none" : "0 2px 12px rgba(245,158,11,0.35)",
              }}>
              {loading ? "Signing in..." : "Sign In →"}
            </button>
          </form>
        </div>

        {/* Quick login cards */}
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 10, color: "#475569", textAlign: "center", marginBottom: 12, letterSpacing: "0.08em" }}>
            QUICK LOGIN — DEMO ACCOUNTS
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            {USERS.map(u => (
              <div key={u.id} onClick={() => quickLogin(u)}
                style={{
                  background: "#111827", border: "1px solid #1e2d45",
                  borderRadius: 10, padding: "12px 10px", cursor: "pointer",
                  textAlign: "center", transition: "all 0.15s",
                  borderTop: `3px solid ${u.avatarColor}`,
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = u.avatarColor}
                onMouseLeave={e => e.currentTarget.style.borderColor = "#1e2d45"}
              >
                <div style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: u.avatarColor + "22", border: `2px solid ${u.avatarColor}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 700, color: u.avatarColor,
                  margin: "0 auto 6px",
                }}>{u.avatar}</div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#e2e8f0" }}>{u.name.split(" ")[0]}</div>
                <div style={{ fontSize: 9, color: "#64748b", marginTop: 2 }}>{u.roleLabel}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ textAlign: "center", marginTop: 20, fontSize: 10, color: "#334155" }}>
          © 2026 Semantic Digital Twin · Supply Chain Intelligence
        </div>
      </div>
    </div>
  );
}

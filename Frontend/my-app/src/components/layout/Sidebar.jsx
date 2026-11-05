import { C } from "../../styles/theme";
import { NAV } from "../../data/constants";
import { ROLE_PAGES } from "../../auth/roles";

export default function Sidebar({ activePage, onNavigate, user }) {
  const now = new Date().toLocaleString("en-US", { hour:"2-digit", minute:"2-digit", hour12:false });
  const allowedPages = ROLE_PAGES[user?.role] || [];
  const visibleNav = NAV.filter(n => allowedPages.includes(n.id));

  return (
    <div style={{
      width: 240, minWidth: 240, background: C.surface,
      borderRight: `1px solid ${C.border}`,
      display: "flex", flexDirection: "column",
      overflowY: "auto",
    }}>
      {/* Logo */}
      <div style={{ padding: "20px 20px 16px", borderBottom: `1px solid ${C.border}`, marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 9,
            background: "linear-gradient(135deg, #f59e0b, #f97316)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, boxShadow: "0 2px 10px rgba(245,158,11,0.35)",
          }}>◈</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, color: C.text, letterSpacing: "-0.01em" }}>
              Semantic Digital Twin
            </div>
            <div style={{ fontSize: 11, color: C.muted, marginTop: 1 }}>Supply Chain v1.0</div>
          </div>
        </div>
      </div>

      {/* User role badge */}
      {user && (
        <div style={{ padding: "6px 12px 4px" }}>
          <div style={{
            padding: "8px 12px", borderRadius: 9,
            background: user.avatarColor + "15",
            border: `1px solid ${user.avatarColor}30`,
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <div style={{
              width: 26, height: 26, borderRadius: "50%",
              background: user.avatarColor + "25",
              border: `2px solid ${user.avatarColor}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: 700, color: user.avatarColor, flexShrink: 0,
            }}>{user.avatar}</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.text, lineHeight: 1.2 }}>{user.name}</div>
              <div style={{ fontSize: 11, color: user.avatarColor, fontWeight: 500 }}>{user.roleLabel}</div>
            </div>
          </div>
        </div>
      )}

      {/* Nav label */}
      <div style={{ padding: "12px 20px 6px", fontSize: 11, color: C.muted, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        Navigation
      </div>

      {/* Nav items */}
      {visibleNav.map(n => (
        <div key={n.id}
          className="nav-item"
          onClick={() => onNavigate(n.id)}
          style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 20px", margin: "1px 8px",
            cursor: "pointer", fontSize: 14, fontWeight: 500,
            color:      activePage === n.id ? C.accent : C.textSoft,
            background: activePage === n.id ? "rgba(245,158,11,0.1)" : "transparent",
            borderRadius: 9,
            borderLeft: activePage === n.id ? `3px solid ${C.accent}` : "3px solid transparent",
            transition: "all 0.12s",
          }}>
          <span style={{ fontSize: 15, width: 18, textAlign: "center", flexShrink: 0 }}>{n.icon}</span>
          <span style={{ flex: 1 }}>{n.label}</span>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: n.dot, boxShadow: `0 0 5px ${n.dot}`, flexShrink: 0, opacity: 0.8 }} />
        </div>
      ))}

      {/* Footer */}
      <div style={{ marginTop: "auto", padding: "14px 20px", borderTop: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: C.green, boxShadow: `0 0 6px ${C.green}` }} className="glow-dot" />
          <span style={{ fontSize: 12, color: C.muted }}>Reasoner Online</span>
        </div>
        <div style={{ fontSize: 11, color: C.muted }}>⏱ {now} · EGY/Cairo</div>
      </div>
    </div>
  );
}

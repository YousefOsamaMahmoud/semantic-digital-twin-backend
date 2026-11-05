export const C = {
  bg: "#0a0e1a",
  surface: "#111827",
  surface2: "#0f1929",
  border: "#1e2d45",
  borderHi: "#2a4a6b",
  text: "#f1f5f9",
  textSoft: "#cbd5e1",
  muted: "#64748b",
  accent: "#f59e0b",
  accentLo: "#78350f",
  blue: "#3b82f6",
  green: "#10b981",
  red: "#ef4444",
  orange: "#f97316",
  purple: "#8b5cf6",
  pink: "#ec4899",
};

export const S = {
  card: {
    background: "#111827",
    border: "1px solid #1e2d45",
    borderRadius: 12,
    padding: 20,
    boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
  },
  cardHeader: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 13, fontWeight: 700, color: "#94a3b8",
    letterSpacing: "0.04em", textTransform: "uppercase",
  },
  pageHeader: { marginBottom: 24 },
  pageTitle: {
    fontSize: 24, fontWeight: 800, color: "#f1f5f9",
    letterSpacing: "-0.02em", lineHeight: 1.2,
  },
  pageDesc: { fontSize: 14, color: "#64748b", marginTop: 6, lineHeight: 1.5 },

  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginBottom: 18 },
  grid3: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 18, marginBottom: 18 },
  grid4: { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 22 },

  table: { width: "100%", borderCollapse: "collapse", fontSize: 14 },
  th: {
    textAlign: "left", padding: "10px 14px",
    fontSize: 12, color: "#64748b", fontWeight: 600,
    letterSpacing: "0.05em", textTransform: "uppercase",
    borderBottom: "1px solid #1e2d45",
    background: "#0f1929",
  },
  td: {
    padding: "12px 14px",
    borderBottom: "1px solid rgba(30,45,69,0.6)",
    verticalAlign: "middle",
    color: "#cbd5e1",
    fontSize: 14,
  },
  input: {
    background: "#0a0e1a", border: "1px solid #1e2d45",
    borderRadius: 8, padding: "10px 14px", color: "#f1f5f9",
    fontSize: 14, outline: "none", width: "100%",
    boxSizing: "border-box",
    fontFamily: "'Inter', -apple-system, sans-serif",
    transition: "border-color 0.15s",
  },
  select: {
    background: "#0a0e1a", border: "1px solid #1e2d45",
    borderRadius: 8, padding: "8px 12px", color: "#f1f5f9",
    fontSize: 13, outline: "none",
    fontFamily: "'Inter', -apple-system, sans-serif",
    cursor: "pointer",
  },
  btn: (variant = "primary") => ({
    padding: "9px 18px", borderRadius: 8, fontSize: 13, fontWeight: 600,
    cursor: "pointer", border: "none", letterSpacing: "0.01em",
    fontFamily: "'Inter', -apple-system, sans-serif",
    background: variant === "primary" ? "#f59e0b"
      : variant === "danger" ? "#ef4444"
        : variant === "ghost" ? "transparent"
          : "#1e2d45",
    color: variant === "primary" ? "#000"
      : variant === "danger" ? "#fff"
        : variant === "ghost" ? "#94a3b8"
          : "#f1f5f9",
    border: variant === "ghost" ? "1px solid #1e2d45" : "none",
    boxShadow: variant === "primary" ? "0 2px 8px rgba(245,158,11,0.25)" : "none",
    transition: "all 0.15s",
  }),
  badge: (color) => ({
    padding: "3px 10px", borderRadius: 20, fontSize: 12, fontWeight: 600,
    background: color + "22", color,
    border: `1px solid ${color}44`,
    display: "inline-block",
    letterSpacing: "0.02em",
  }),
  riskBadge: (level) => {
    const map = {
      HIGH: { bg: "#ef444422", color: "#ef4444" },
      MEDIUM: { bg: "#f59e0b22", color: "#f59e0b" },
      LOW: { bg: "#10b98122", color: "#10b981" },
      CRITICAL: { bg: "#ec489922", color: "#ec4899" },
      MITIGATED: { bg: "#10b98122", color: "#10b981" },
    };
    const t = map[level] || { bg: "#1e2d45", color: "#64748b" };
    return {
      display: "inline-block", padding: "3px 10px", borderRadius: 20,
      fontSize: 12, fontWeight: 600, background: t.bg, color: t.color,
      border: `1px solid ${t.color}33`,
    };
  },
  trafficLight: (level) => {
    const map = { RED: "#ef4444", YELLOW: "#f59e0b", GREEN: "#10b981" };
    const c = map[level] || "#64748b";
    return { width: 10, height: 10, borderRadius: "50%", background: c, boxShadow: `0 0 8px ${c}`, flexShrink: 0 };
  },
  progressBar: (pct, color) => ({
    outer: { height: 6, background: "#1e2d45", borderRadius: 99, marginTop: 8 },
    inner: { height: "100%", width: `${Math.min(100, pct)}%`, background: color, borderRadius: 99, transition: "width 0.5s" },
  }),
  chatBubble: (role) => ({
    maxWidth: "80%", alignSelf: role === "user" ? "flex-end" : "flex-start",
    background: role === "user" ? "#78350f" : "#111827",
    border: `1px solid ${role === "user" ? "#f59e0b44" : "#1e2d45"}`,
    borderRadius: role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
    padding: "12px 16px", fontSize: 14, lineHeight: 1.6,
    color: "#f1f5f9",
    boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
  }),
};

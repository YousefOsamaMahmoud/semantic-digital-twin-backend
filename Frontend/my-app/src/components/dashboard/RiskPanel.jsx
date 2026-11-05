import { C, S } from "../../styles/theme";

export default function RiskPanel({ risks, onDrillDown }) {
  return (
    <div style={S.card}>
      <div style={S.cardHeader}>
        <span style={S.cardTitle}>⚠ Inventory Risk Overview</span>
        <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 20, background: C.orange + "20", color: C.orange }} className="live-pulse">● Live</span>
      </div>
      {risks.map((r, i) => {
        // Guard: if threshold is 0 (field not stored in KB), derive a visual % from status
        const hasStockData = r.threshold > 0;
        const pct = hasStockData
          ? (r.stock >= r.threshold ? 0 : Math.round(100 - (r.stock / r.threshold) * 100))
          : r.trafficLight === "RED" ? 80 : 15;
        const derivedRisk = pct >= 80 ? "CRITICAL" : pct >= 50 ? "HIGH" : pct >= 20 ? "MEDIUM" : "LOW";
        const color = derivedRisk === "CRITICAL" ? C.red
                    : derivedRisk === "HIGH"     ? C.orange
                    : derivedRisk === "MEDIUM"   ? C.accent
                    : C.green;
        const pb = S.progressBar(pct, color);
        return (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: i < risks.length - 1 ? `1px solid ${C.border}` : "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
              <span
                style={{ fontSize: 14, fontWeight: 600, color: C.text, cursor: onDrillDown ? "pointer" : "default" }}
                onClick={() => onDrillDown && onDrillDown(r)}
              >
                {r.material}
              </span>
              <span style={S.riskBadge(derivedRisk)}>{derivedRisk}</span>
            </div>
            <div style={{ fontSize: 13, color: C.muted, marginBottom: 6 }}>
              {r.impact}{r.delay > 0 ? ` · +${r.delay}d delay` : ""}
            </div>
            <div style={pb.outer}><div style={pb.inner} /></div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5 }}>
              <span style={{ fontSize: 12, color: C.muted }}>
                Supplier: {r.supplier}
              </span>
              <span style={{ fontSize: 12, color, fontWeight: 600 }}>{Math.round(pct)}% Risk</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

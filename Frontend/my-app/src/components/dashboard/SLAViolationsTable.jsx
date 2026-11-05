import { C, S } from "../../styles/theme";

export default function SLAViolationsTable({ data }) {
  return (
    <div style={S.card}>
      <div style={S.cardHeader}>
        <span style={S.cardTitle}>📋 SLA Compliance Monitor</span>
        <span style={{ fontSize: 13, color: C.muted }}>{data.length} contracts · {data.filter(d => d.violationStatus).length} breached</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={S.table}>
          <thead>
            <tr>{["ID", "Supplier", "Material", "Compliance", "Status", "Daily Penalty"].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {data.map((s, i) => (
              <tr key={i} className="data-row" style={{ background: s.risk === "CRITICAL" ? "rgba(239,68,68,0.04)" : "transparent" }}>
                <td style={{ ...S.td, color: C.blue, fontFamily: "monospace", fontWeight: 600 }}>{s.id}</td>
                <td style={{ ...S.td, fontWeight: 600, color: C.text }}>{s.supplier}</td>
                <td style={{ ...S.td, color: C.muted }}>{s.material}</td>
                <td style={S.td}>
                  {s.compliance !== null ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontWeight: 700, fontSize: 14, color: s.compliance > 80 ? C.green : s.compliance > 60 ? C.orange : C.red }}>{s.compliance}%</span>
                      <div style={{ flex: 1, height: 6, background: C.border + "33", borderRadius: 99, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${s.compliance}%`, background: s.compliance > 80 ? C.green : s.compliance > 60 ? C.orange : C.red, borderRadius: 99 }} />
                      </div>
                    </div>
                  ) : (
                    <span style={{ color: C.muted }}>—</span>
                  )}
                </td>
                <td style={S.td}>
                  {s.violationStatus
                    ? <span style={S.riskBadge("CRITICAL")}>BREACHED</span>
                    : <span style={S.riskBadge("LOW")}>COMPLIANT</span>}
                </td>
                <td style={{ ...S.td, fontWeight: 600, color: s.violationStatus ? C.green : C.muted }}>{s.penalty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

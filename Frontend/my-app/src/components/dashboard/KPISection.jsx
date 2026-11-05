import { C, S } from "../../styles/theme";

export default function KPISection({ data }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.length},1fr)`, gap: 14, marginBottom: 22 }}>
      {data.map((k, i) => (
        <div key={i} style={{ ...S.card, borderTop: `3px solid ${k.color}`, padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10,
              background: k.color + "18",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 18,
            }}>{k.icon}</div>
            {/* Only render the change badge when there is an actual value */}
            {k.change ? (
              <span style={{
                fontSize: 12, fontWeight: 600, padding: "3px 9px", borderRadius: 20,
                background: k.up ? C.green + "20" : C.red + "20",
                color: k.up ? C.green : C.red,
              }}>{k.up ? "▲" : "▼"} {k.change}</span>
            ) : (
              <span style={{
                fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20,
                background: C.blue + "18", color: C.blue,
              }}>● Live</span>
            )}
          </div>
          <div style={{ fontSize: 30, fontWeight: 800, color: k.color, lineHeight: 1, marginBottom: 6 }}>{k.value}</div>
          <div style={{ fontSize: 13, color: C.muted, fontWeight: 500 }}>{k.label}</div>
        </div>
      ))}
    </div>
  );
}

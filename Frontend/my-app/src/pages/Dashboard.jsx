import { useState, useEffect } from "react";
import { C, S } from "../styles/theme";
import KPISection from "../components/dashboard/KPISection";
import RiskPanel from "../components/dashboard/RiskPanel";
import SLAViolationsTable from "../components/dashboard/SLAViolationsTable";
import ReliabilityChart from "../components/dashboard/ReliabilityChart";
import { fetchRiskScores, fetchComplianceAlerts, fetchKPIs } from "../services/api";

const ROLE_CFG = {
  admin: { showRisk: true, showReliability: true, showSla: true },
  logistics: { showRisk: true, showReliability: false, showSla: false },
  procurement: { showRisk: false, showReliability: true, showSla: true },
  production: { showRisk: true, showReliability: false, showSla: false },
};

// KPI card skeleton — values filled from backend on mount
const buildKpiCards = (kpis) => [
  {
    label: "Active Suppliers",
    value: kpis.active_suppliers !== undefined ? String(kpis.active_suppliers) : "—",
    change: "", up: true, color: C.blue, icon: "🏭",
  },
  {
    label: "At-Risk Shipments",
    value: kpis.at_risk_shipments !== undefined ? String(kpis.at_risk_shipments) : "—",
    change: "", 
    up: kpis.at_risk_shipments === 0, 
    color: kpis.at_risk_shipments > 0 ? C.orange : C.green, 
    icon: kpis.at_risk_shipments > 0 ? "⚠" : "✅",
  },
  {
    label: "SLA Compliance",
    value: kpis.sla_compliance !== undefined ? `${kpis.sla_compliance}%` : "—",
    change: "", up: kpis.sla_compliance >= 80, color: C.green, icon: "📋",
  },
  {
    label: "Avg Delay (days)",
    value: kpis.avg_lead_time !== undefined ? String(kpis.avg_lead_time) : "—",
    change: "", up: false, color: C.purple, icon: "⏱",
  },
  {
    label: "Total Penalties",
    value: kpis.total_penalty !== undefined
      ? (kpis.total_penalty >= 1000 ? `$${(kpis.total_penalty / 1000).toFixed(1).replace(/\.0$/, "")}K` : `$${kpis.total_penalty}`)
      : "—",
    change: "", up: false, color: C.red, icon: "💰",
  },
  {
    label: "Alerts (48h)",
    value: kpis.alert_count !== undefined ? String(kpis.alert_count) : "—",
    change: "", up: false, color: C.pink, icon: "🔔",
  },
];

function EmptyState({ message }) {
  return (
    <div style={{ textAlign: "center", padding: "32px 20px", color: C.muted, fontSize: 14 }}>
      <div style={{ fontSize: 32, marginBottom: 10 }}>📭</div>
      {message}
    </div>
  );
}

function ErrorState({ message }) {
  return (
    <div style={{ padding: "12px 16px", background: C.red + "15", border: `1px solid ${C.red}33`, borderRadius: 8, fontSize: 13, color: C.red }}>
      ⚠ {message}
    </div>
  );
}

export default function Dashboard({ user }) {
  const cfg = ROLE_CFG[user?.role] || ROLE_CFG.admin;

  const [riskScores, setRiskScores] = useState([]);
  const [slaAlerts, setSlaAlerts] = useState([]);
  const [kpis, setKpis] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const load = async (isFirstLoad) => {
      try {
        const [scores, alerts, kpiData] = await Promise.all([
          fetchRiskScores(),
          fetchComplianceAlerts(),
          fetchKPIs(user?.role),
        ]);
        if (cancelled) return;
        setRiskScores(scores);
        setSlaAlerts(alerts);
        setKpis(kpiData);
        setError("");
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled && isFirstLoad) setLoading(false);
      }
    };

    load(true);

    // Keep KPIs, risk scores, and compliance alerts live as the
    // background telemetry simulator produces new disruption/SLA
    // events, without requiring a manual page refresh.
    const intervalId = setInterval(() => load(false), 5000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  const kpiCards = buildKpiCards(kpis);

  const visibleKpis = user?.role === "procurement"
    ? kpiCards.filter(k => ["SLA Compliance", "Alerts (48h)", "Total Penalties", "At-Risk Shipments"].includes(k.label))
    : user?.role === "production"
      ? kpiCards.filter(k => ["At-Risk Shipments", "Alerts (48h)", "SLA Compliance", "Avg Delay (days)"].includes(k.label))
      : user?.role === "logistics"
        ? kpiCards.filter(k => ["Active Suppliers", "At-Risk Shipments", "Avg Delay (days)", "Alerts (48h)"].includes(k.label))
        : kpiCards;


  // Map risk scores to RiskPanel format
  const riskPanelData = riskScores.map(r => ({
    material: r.material || r.materialLabel || "Unknown Material",
    supplier: r.supplier || r.supplierLabel || "Unknown Supplier",
    impact: r.product || r.productLabel || "",
    trafficLight: r.status === "RED" ? "RED" : "GREEN",
    risk: r.status === "RED" ? "HIGH" : "LOW",
    stock: r.stock || 0,
    threshold: r.threshold || 0,
    delay: r.delayDuration || 0,
    delayProb: r.status === "RED" ? 80 : 10,
    processes: r.product ? [r.product] : [],
  }));

  // Map risk scores to ReliabilityChart format (unique suppliers)
  const uniqueSuppliers = Array.from(new Set(riskScores.map(r => r.supplier || r.supplierLabel)));
  const reliabilityData = uniqueSuppliers.map(supName => {
    const s = riskScores.find(r => (r.supplier || r.supplierLabel) === supName);
    if (!s.reliabilityScore) return null;
    const scoreVal = parseFloat(s.reliabilityScore);
    return {
      name: supName,
      score: Math.round(scoreVal * 100),
      countryCode: (s.country || "GL").substring(0, 2).toUpperCase(),
      risk: scoreVal >= 0.8 ? "LOW" : scoreVal >= 0.5 ? "MEDIUM" : "HIGH",
    };
  }).filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 6);

  // Map compliance alerts to SLA table format
  const slaTableData = slaAlerts.map((a, i) => ({
    id: `SLA-${String(i + 1).padStart(3, "0")}`,
    supplier: a.supplier || a.supplierLabel || "Unknown",
    material: a.material || a.materialLabel || "Unknown",
    deadline: a.deadline || "—",
    compliance: a.compliance !== undefined ? a.compliance : null,
    risk: a.risk || "MEDIUM",
    penalty: a.penalty || a.penaltyRate ? `$${a.penaltyRate}/day` : "—",
    penaltyDaily: a.penaltyRate || 0,
    delayDays: a.delayDays || 0,
    violationStatus: a.violationStatus,
    gracePeriod: "48h",
    clause: a.clause || "—",
  }));

  return (
    <div>
      <div style={{ ...S.pageHeader, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={S.pageTitle}>Welcome back, {user?.name?.split(" ")[0]} 👋</div>
          <div style={S.pageDesc}>
            {user?.roleLabel} · Supply Chain Intelligence Platform
            {loading && <span style={{ color: C.accent, marginLeft: 10 }}><span className="spin">⚙</span> Loading live data...</span>}
          </div>
        </div>
        <div style={{ padding: "6px 14px", borderRadius: 8, background: (user?.avatarColor || C.accent) + "18", border: `1px solid ${(user?.avatarColor || C.accent)}33`, fontSize: 12, color: user?.avatarColor || C.accent, fontWeight: 700 }}>
          {user?.roleLabel?.toUpperCase()}
        </div>
      </div>

      <KPISection data={visibleKpis} />

      {error && <div style={{ marginBottom: 16 }}><ErrorState message={`Failed to load data: ${error}`} /></div>}

      <div style={{ display: "grid", gridTemplateColumns: cfg.showRisk && cfg.showReliability ? "2fr 1fr" : "1fr", gap: 18, marginBottom: 18 }}>
        {cfg.showRisk && (
          <div>
            {loading ? (
              <div style={{ ...S.card, textAlign: "center", padding: "24px", color: C.accent }}>
                <span className="spin">⚙</span> Loading risk data...
              </div>
            ) : riskPanelData.length === 0 ? (
              <div style={S.card}><EmptyState message="No risk data returned from Knowledge Graph" /></div>
            ) : (
              <RiskPanel risks={riskPanelData} />
            )}
          </div>
        )}

        {cfg.showReliability && (
          <div>
            {loading ? (
              <div style={{ ...S.card, textAlign: "center", padding: "24px", color: C.accent }}>
                <span className="spin">⚙</span> Loading...
              </div>
            ) : reliabilityData.length === 0 ? (
              <div style={S.card}><EmptyState message="No suppliers to chart" /></div>
            ) : (
              <ReliabilityChart suppliers={reliabilityData} />
            )}
          </div>
        )}
      </div>

      {cfg.showSla && (
        <div>
          {loading ? (
            <div style={{ ...S.card, textAlign: "center", padding: "24px", color: C.accent }}><span className="spin">⚙</span> Loading SLA data...</div>
          ) : slaTableData.length === 0 ? (
            <div style={S.card}><EmptyState message="No SLA data returned from Knowledge Graph" /></div>
          ) : (
            <SLAViolationsTable data={slaTableData} />
          )}
        </div>
      )}
    </div>
  );
}

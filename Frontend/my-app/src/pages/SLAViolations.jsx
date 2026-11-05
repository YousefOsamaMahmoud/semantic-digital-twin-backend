import { useState, useEffect } from "react";
import { C, S } from "../styles/theme";
import { fetchComplianceAlerts } from "../services/api";

// ── SLA Detail Modal ──────────────────────────────────────────────────────────
function SLAModal({ sla, onClose }) {
  if (!sla) return null;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }} onClick={onClose}>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, width: "100%", maxWidth: 500, boxShadow: "0 20px 60px rgba(0,0,0,0.5)", overflow: "hidden" }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: "16px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>SLA Contract — {sla.id}</div>
            <div style={{ fontSize: 12, color: C.muted }}>{sla.supplier} · {sla.material}</div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: C.muted, cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>
        <div style={{ padding: "16px 20px" }}>
          {[
            ["Supplier", sla.supplier || "—"],
            ["Material", sla.material || "—"],
            ["Compliance Rate", sla.compliance !== undefined ? `${sla.compliance}%` : "—"],
            ["Risk Level", sla.risk || "—"],
            ["Penalty Rate", sla.penalty || "—"],
            ["Lead Time", sla.leadTimeDays !== undefined ? `${sla.leadTimeDays} days` : "—"],
            ["Delay Days", sla.violationType === "LateDelivery" && sla.delayDays > 0 ? `${sla.delayDays} days overdue` : sla.violationType === "UnderShipment" ? "Quantity Shortage Breach" : sla.violationType === "DamagedGoods" ? "Quality Goods Breach" : "On track"],
            ["Status", sla.violationStatus ? `BREACHED — Penalty Active ($${(sla.penaltyOwed || 0).toLocaleString()})` : "COMPLIANT"],
          ].map(([k, v], i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 13 }}>
              <span style={{ color: C.muted }}>{k}</span>
              <span style={{ fontWeight: 600, color: k === "Status" ? (sla.violationStatus ? C.red : C.green) : C.text }}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop: 16 }}>
            <a href={`mailto:contact@${(sla.supplier || "supplier").toLowerCase().replace(/ /g, "")}.com`}
              style={{ ...S.btn(), textDecoration: "none", fontSize: 12, padding: "8px 16px" }}>
              ✉ Contact Supplier
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SLAViolations({ user }) {
  const [slaList, setSlaList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [penalty, setPenalty] = useState(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [slaModal, setSlaModal] = useState(null);
  const [filterSupplier, setFilterSupplier] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchComplianceAlerts()
      .then(alerts => {
        const mapped = (alerts || []).map((a, i) => ({
          id: a.id || `SLA-${String(i + 1).padStart(3, "0")}`,
          supplier: a.supplier || a.supplierLabel || "—",
          material: a.material || a.materialLabel || "—",
          deadline: a.deadline || "—",
          compliance: a.compliance !== undefined ? a.compliance : null,
          risk: a.risk || "LOW",
          penalty: a.penalty || (a.penaltyRate ? `$${a.penaltyRate}/day` : "—"),
          penaltyDaily: a.penaltyRate || 0,
          leadTimeDays: a.leadTimeDays !== undefined ? a.leadTimeDays : 0,
          delayDays: a.delayDays || 0,
          violationStatus: a.violationStatus || false,
          gracePeriod: a.gracePeriod || "48h",
          clause: a.clause || "—",
          violationType: a.violationType || null,
          penaltyOwed: a.penaltyOwed || 0,
          orderedQty: a.orderedQty || null,
          deliveredQty: a.deliveredQty || null,
          totalCost: a.totalCost || null,
          missedItemPenaltyRate: a.missedItemPenaltyRate || null,
          qualityPenaltyRate: a.qualityPenaltyRate || null,
        }));
        setSlaList(mapped);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleCalcPenalty = async (sla) => {
    setSelected(sla.id); setCalcLoading(true); setPenalty(null);
    await new Promise(r => setTimeout(r, 300));
    
    if (sla.violationType === "UnderShipment") {
      const ordered = sla.orderedQty || 100;
      const delivered = sla.deliveredQty || 70;
      const missed = Math.max(0, ordered - delivered);
      const rate = sla.missedItemPenaltyRate || 50;
      setPenalty({
        slaId: sla.id,
        type: "Under-Shipment",
        orderedQty: ordered,
        deliveredQty: delivered,
        missedQty: missed,
        rate,
        totalPenalty: sla.penaltyOwed || (missed * rate),
        clause: sla.clause && sla.clause !== "—" ? sla.clause : `Missed Item Penalty: $${rate}/unit`,
      });
    } else if (sla.violationType === "DamagedGoods") {
      const cost = sla.totalCost || 5000;
      const rate = sla.qualityPenaltyRate || 0.1;
      setPenalty({
        slaId: sla.id,
        type: "Damaged Goods (Quality)",
        totalCost: cost,
        rate: Math.round(rate * 100),
        totalPenalty: sla.penaltyOwed || (cost * rate),
        clause: sla.clause && sla.clause !== "—" ? sla.clause : `Quality Penalty: ${Math.round(rate * 100)}% of PO Cost`,
      });
    } else {
      // LateDelivery or default
      const graceDays = 2;
      const billableDays = Math.max(0, (sla.delayDays || 0) - graceDays);
      const dailyRate = sla.penaltyDaily || 0;
      setPenalty({
        slaId: sla.id,
        type: "Late Delivery",
        delayDays: sla.delayDays || 0,
        gracePeriodDays: graceDays,
        billableDays,
        dailyRate,
        totalPenalty: sla.penaltyOwed || (billableDays * dailyRate),
        clause: sla.clause,
      });
    }
    setCalcLoading(false);
  };

  const filteredSlaList = slaList.filter(s => {
    const matchesSupplier = filterSupplier === "ALL" || s.supplier === filterSupplier;
    const matchesSearch = !searchQuery || 
      (s.supplier || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.material || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.id || "").toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSupplier && matchesSearch;
  });
  const violations = filteredSlaList.filter(s => s.violationStatus);
  const totalOwed = violations.reduce((acc, s) => acc + (s.penaltyOwed || 0), 0);
  const validCompliances = filteredSlaList.filter(s => s.compliance !== null);
  const avgCompliance = validCompliances.length > 0
    ? Math.round(validCompliances.reduce((a, s) => a + (s.compliance || 0), 0) / validCompliances.length)
    : null;

  const lateDeliveryPenalties = filteredSlaList
    .filter(s => s.violationStatus && (!s.violationType || s.violationType === "LateDelivery"))
    .reduce((acc, s) => acc + (s.penaltyOwed || 0), 0);

  const underShipmentPenalties = filteredSlaList
    .filter(s => s.violationStatus && s.violationType === "UnderShipment")
    .reduce((acc, s) => acc + (s.penaltyOwed || 0), 0);

  const damagedGoodsPenalties = filteredSlaList
    .filter(s => s.violationStatus && s.violationType === "DamagedGoods")
    .reduce((acc, s) => acc + (s.penaltyOwed || 0), 0);

  return (
    <div>
      {slaModal && <SLAModal sla={slaModal} onClose={() => setSlaModal(null)} />}

      <div style={{ ...S.pageHeader, display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <div style={S.pageTitle}>SLA Violations · Compliance Monitor</div>
          <div style={S.pageDesc}>Track supplier SLA breaches and penalties owed to your company</div>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Search bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: C.card, padding: "8px 16px", borderRadius: 8, border: `1px solid ${C.border}44` }}>
            <span style={{ fontSize: 13, color: C.muted, fontWeight: 500 }}>🔍 Search:</span>
            <input
              type="text"
              placeholder="Search supplier..."
              value={searchQuery}
              onChange={e => {
                setSearchQuery(e.target.value);
                setSelected(null);
                setPenalty(null);
              }}
              style={{
                padding: "6px 12px",
                borderRadius: 4,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                fontSize: 13,
                outline: "none",
                width: 160,
                transition: "all 0.15s",
              }}
            />
          </div>

          {/* Supplier dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: C.card, padding: "8px 16px", borderRadius: 8, border: `1px solid ${C.border}44` }}>
            <span style={{ fontSize: 13, color: C.muted, fontWeight: 500 }}>Filter by Supplier:</span>
            <select 
              value={filterSupplier}
              onChange={e => {
                setFilterSupplier(e.target.value);
                setSelected(null);
                setPenalty(null);
              }}
              style={{ padding: "6px 12px", borderRadius: 4, border: `1px solid ${C.border}`, background: C.bg, color: C.text, fontSize: 13, outline: "none", cursor: "pointer" }}
            >
              <option value="ALL">All Suppliers</option>
              {Array.from(new Set(slaList.map(v => v.supplier))).filter(Boolean).sort().map(sup => (
                <option key={sup} value={sup}>{sup}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* KPIs — only show real numbers, dash if unknown */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
        {[
          { label: filterSupplier === "ALL" ? "Total Contracts" : "Supplier Contracts", value: loading ? "—" : filteredSlaList.length.toString(), color: C.blue },
          { label: "Active Breaches", value: loading ? "—" : violations.length.toString(), color: C.red },
          { label: "Avg Compliance", value: loading ? "—" : avgCompliance !== null ? `${avgCompliance}%` : "—", color: C.green },
          { label: "Total Penalties Owed", value: loading ? "—" : totalOwed > 0 ? `$${totalOwed.toLocaleString()}` : "$0", color: C.accent },
        ].map((k, i) => (
          <div key={i} style={{ ...S.card, borderTop: `3px solid ${k.color}`, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: "0.07em" }}>{k.label}</div>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color: loading ? C.muted : k.color }}>
              {loading ? <span className="spin" style={{ fontSize: 16 }}>⚙</span> : k.value}
            </div>
            {k.label === "Total Penalties Owed" && !loading && totalOwed > 0 && (
              <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>Owed to your company</div>
            )}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: "12px 16px", background: C.red + "15", border: `1px solid ${C.red}33`, borderRadius: 8, fontSize: 13, color: C.red, marginBottom: 16 }}>
          ⚠ Backend error: {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ ...S.card, textAlign: "center", padding: "48px", color: C.accent }}>
          <div style={{ fontSize: 22, marginBottom: 10 }} className="spin">⚙</div>
          <div style={{ fontSize: 14 }}>Loading SLA data from Knowledge Graph...</div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && slaList.length === 0 && (
        <div style={{ ...S.card, textAlign: "center", padding: "48px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 14 }}>📭</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 8 }}>No SLA data returned</div>
          <div style={{ fontSize: 14, color: C.muted }}>
            The backend returned no compliance alerts.<br />
            Check that GraphDB is running and the ontology is loaded.
          </div>
        </div>
      )}

      {/* Data */}
      {!loading && slaList.length > 0 && (
        <div style={S.grid2}>
          {/* Contract list */}
          <div style={S.card}>
            <div style={{ ...S.cardTitle, marginBottom: 16 }}>📋 SLA Contract Status {filterSupplier !== "ALL" && `(${filterSupplier})`}</div>
            {filteredSlaList.map((s, i) => (
              <div key={i} className="data-row"
                style={{ padding: "12px 0", borderBottom: `1px solid ${C.border}22`, background: selected === s.id ? "rgba(245,158,11,0.04)" : "transparent", transition: "background 0.15s" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{s.supplier}</div>
                    <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>
                      <span style={{ fontFamily: "monospace", color: C.blue }}>{s.id}</span> · {s.material}
                    </div>
                    {s.violationStatus && s.penaltyOwed > 0 && (
                      <div style={{ fontSize: 12, color: C.green, marginTop: 2, fontWeight: 600 }}>
                        💰 ${s.penaltyOwed.toLocaleString()} owed
                      </div>
                    )}
                  </div>
                  {s.violationStatus
                    ? <span style={S.riskBadge("CRITICAL")}>
                        {s.violationType === "UnderShipment" ? "⚠️ UNDER-SHIPMENT" : s.violationType === "DamagedGoods" ? "❌ DAMAGED GOODS" : "⏳ LATE DELIVERY"}
                      </span>
                    : <span style={S.riskBadge("LOW")}>COMPLIANT</span>}
                </div>

                {s.compliance !== null && (
                  <div style={{ height: 3, background: C.border, borderRadius: 2, marginBottom: 10 }}>
                    <div style={{ height: "100%", width: `${s.compliance}%`, background: s.compliance > 80 ? C.green : s.compliance > 60 ? C.orange : C.red, borderRadius: 2 }} />
                  </div>
                )}

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button style={{ ...S.btn("ghost"), fontSize: 11, padding: "4px 10px" }} onClick={() => setSlaModal(s)}>
                    📄 View SLA
                  </button>
                  <a href={`mailto:contact@${(s.supplier || "").toLowerCase().replace(/ /g, "")}.com`}
                    style={{ ...S.btn("secondary"), fontSize: 11, padding: "4px 10px", textDecoration: "none" }}>
                    ✉ Contact
                  </a>
                  {s.violationStatus && (
                    <button style={{ ...S.btn("ghost"), fontSize: 11, padding: "4px 10px" }} onClick={() => handleCalcPenalty(s)}>
                      💰 Calc Penalty
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Right: Penalty calculator + compliance chart */}
          <div>
            <div style={{ ...S.card, marginBottom: 16 }}>
              <div style={{ ...S.cardTitle, marginBottom: 14 }}>💰 Penalty Calculator</div>
              {!selected && !calcLoading && (
                <div style={{ textAlign: "center", padding: "28px 20px", color: C.muted, fontSize: 13 }}>
                  Click "Calc Penalty" on a breached contract to see the breakdown
                </div>
              )}
              {calcLoading && (
                <div style={{ textAlign: "center", padding: "20px", color: C.accent }}>
                  <span className="spin">⚙</span> Calculating...
                </div>
              )}
              {penalty && !calcLoading && (
                <div>
                  {penalty.type && (
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.accent, marginBottom: 10 }}>
                      Violation: {penalty.type}
                    </div>
                  )}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                    {penalty.type === "Under-Shipment" ? (
                      <>
                        {[
                          ["Ordered Qty", `${penalty.orderedQty} units`, C.blue],
                          ["Delivered Qty", `${penalty.deliveredQty} units`, C.green],
                          ["Missed Qty", `${penalty.missedQty} units`, C.red],
                          ["Penalty Rate", `$${penalty.rate}/unit`, C.text],
                        ].map(([k, v, c], i) => (
                          <div key={i} style={{ padding: "8px 10px", background: C.bg, borderRadius: 5, border: `1px solid ${C.border}` }}>
                            <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>{k}</div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: c }}>{v}</div>
                          </div>
                        ))}
                      </>
                    ) : penalty.type === "Damaged Goods (Quality)" ? (
                      <>
                        {[
                          ["Order Value", `$${penalty.totalCost.toLocaleString()}`, C.blue],
                          ["Penalty Rate", `${penalty.rate}%`, C.red],
                        ].map(([k, v, c], i) => (
                          <div key={i} style={{ padding: "8px 10px", background: C.bg, borderRadius: 5, border: `1px solid ${C.border}` }}>
                            <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>{k}</div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: c }}>{v}</div>
                          </div>
                        ))}
                      </>
                    ) : (
                      <>
                        {[
                          ["Total Delay", `${penalty.delayDays} days`, C.orange],
                          ["Grace Period", `${penalty.gracePeriodDays} days`, C.muted],
                          ["Billable Days", `${penalty.billableDays} days`, C.text],
                          ["Daily Rate", `$${penalty.dailyRate}/day`, C.text],
                        ].map(([k, v, c], i) => (
                          <div key={i} style={{ padding: "8px 10px", background: C.bg, borderRadius: 5, border: `1px solid ${C.border}` }}>
                            <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>{k}</div>
                            <div style={{ fontSize: 13, fontWeight: 700, color: c }}>{v}</div>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                  <div style={{ padding: "14px 16px", background: C.green + "11", border: `1px solid ${C.green}33`, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, color: C.muted, marginBottom: 4 }}>PENALTY OWED TO YOUR COMPANY</div>
                    <div style={{ fontSize: 30, fontWeight: 800, color: C.green }}>${penalty.totalPenalty.toLocaleString()}</div>
                    <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>
                      {penalty.type === "Under-Shipment"
                        ? `$${penalty.rate.toLocaleString()}/unit × ${penalty.missedQty} units missed`
                        : penalty.type === "Damaged Goods (Quality)"
                        ? `${penalty.rate}% of $${penalty.totalCost.toLocaleString()} PO cost`
                        : `$${penalty.dailyRate.toLocaleString()}/day × ${penalty.billableDays} billable days`
                      }
                    </div>
                    {penalty.clause && penalty.clause !== "—" && (
                      <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{penalty.clause}</div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Compliance chart */}
            {filteredSlaList.some(s => s.compliance !== null) && (
              <div style={S.card}>
                <div style={{ ...S.cardTitle, marginBottom: 14 }}>📊 Compliance Overview</div>
                {filteredSlaList.map((s, i) => (
                  <div key={i} style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <div>
                        <span style={{ fontSize: 13, color: C.text, fontWeight: 500 }}>{s.supplier}</span>
                        <span style={{ fontSize: 11, color: C.muted, marginLeft: 6 }}>{s.id}</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {s.violationStatus && s.penaltyOwed > 0 && (
                          <span style={{ fontSize: 10, color: C.green, fontWeight: 600 }}>
                            +${s.penaltyOwed.toLocaleString()} owed
                          </span>
                        )}
                        <span style={{ fontSize: 13, fontWeight: 700, color: s.compliance > 80 ? C.green : s.compliance > 60 ? C.orange : C.red }}>
                          {s.compliance !== null ? `${s.compliance}%` : "—"}
                        </span>
                      </div>
                    </div>
                    {s.compliance !== null && (
                      <div style={{ height: 6, background: C.border, borderRadius: 3 }}>
                        <div style={{ height: "100%", width: `${s.compliance}%`, background: s.compliance > 80 ? C.green : s.compliance > 60 ? C.orange : C.red, borderRadius: 3, transition: "width 0.5s" }} />
                      </div>
                    )}
                  </div>
                ))}
                {totalOwed > 0 && (
                  <div style={{ marginTop: 14, padding: "12px 14px", background: C.accent + "11", border: `1px solid ${C.accent}33`, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, color: C.muted, marginBottom: 8, fontWeight: 700, letterSpacing: "0.05em" }}>PENALTY BY VIOLATION TYPE</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {lateDeliveryPenalties > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: C.textSoft }}>⏳ Late Delivery</span>
                          <span style={{ color: C.accent, fontWeight: 700 }}>${lateDeliveryPenalties.toLocaleString()}</span>
                        </div>
                      )}
                      {underShipmentPenalties > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: C.textSoft }}>⚠️ Under-Shipment</span>
                          <span style={{ color: C.accent, fontWeight: 700 }}>${underShipmentPenalties.toLocaleString()}</span>
                        </div>
                      )}
                      {damagedGoodsPenalties > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: C.textSoft }}>❌ Damaged Goods</span>
                          <span style={{ color: C.accent, fontWeight: 700 }}>${damagedGoodsPenalties.toLocaleString()}</span>
                        </div>
                      )}
                      <div style={{ borderTop: `1px solid ${C.accent}22`, marginTop: 6, paddingTop: 6, display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700 }}>
                        <span style={{ color: C.text }}>Total Penalties</span>
                        <span style={{ color: C.accent }}>${totalOwed.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

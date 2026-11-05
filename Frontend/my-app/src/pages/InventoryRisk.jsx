import { useState, useEffect } from "react";
import { C, S } from "../styles/theme";
import { fetchRiskScores, requestFallbackSupplier } from "../services/api";

const COLUMN_HEADERS = {
  material: "Material",
  supplier: "Supplier",
  process: "Impacted Process",
  status: "Status",
  reliabilityScore: "Reliability",
  leadTime: "Lead Time",
  stock: "Current Stock",
  threshold: "Safety Stock Level",
  requiredQty: "Delayed Quantity"
};

export default function InventoryRisk({ onNavigate, user }) {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  // States for Urgent Fallback Request Modal
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [requestResult, setRequestResult] = useState(null);

  useEffect(() => {
    fetchRiskScores()
      .then(p => setProducts(p))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleDownloadExcel = () => {
    if (!products || products.length === 0) return;

    // Filter keys present in the first product and in COLUMN_HEADERS to maintain column order
    const keys = Object.keys(products[0]).filter(k => k in COLUMN_HEADERS);
    const headers = keys.map(k => COLUMN_HEADERS[k]);

    const csvRows = [headers.join(",")];

    products.forEach(p => {
      const values = keys.map(k => {
        let val = p[k];
        if (k === "status") {
          const upper = String(val || "").toUpperCase();
          if (upper === "RED") return "Critical Risk";
          if (upper === "YELLOW") return "Warning (Delayed)";
          if (upper === "GREEN") return "Healthy";
          return val || "Unknown";
        }
        if (k === "reliabilityScore" && val !== null && val !== undefined) {
          return `${(parseFloat(val) * 100).toFixed(0)}%`;
        }
        if (k === "leadTime" && val !== null && val !== undefined) {
          return `${val}d`;
        }
        if (val === null || val === undefined) {
          return "—";
        }
        // Clean values for CSV: escape double quotes, wrap in quotes if there are commas/newlines
        let cell = String(val).replace(/"/g, '""');
        if (cell.includes(",") || cell.includes("\n") || cell.includes('"')) {
          cell = `"${cell}"`;
        }
        return cell;
      });
      csvRows.push(values.join(","));
    });

    const csvContent = "\uFEFF" + csvRows.join("\n"); // Include BOM for Excel UTF-8 support
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `inventory_risk_knowledge_graph_${new Date().toISOString().slice(0, 10)}.csv`);
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div>
      <div style={S.pageHeader}>
        <div style={S.pageTitle}>Inventory Risk · Traffic Light</div>
        <div style={S.pageDesc}>Live data from Knowledge Graph · OWL reasoning · SPARQL</div>
      </div>

      {loading && (
        <div style={{ ...S.card, textAlign: "center", padding: "40px", color: C.accent }}>
          <div style={{ fontSize: 24, marginBottom: 10 }} className="spin">⚙</div>
          Querying Knowledge Graph via SPARQL...
        </div>
      )}

      {error && (
        <div style={{ padding: "14px 18px", background: C.red + "15", border: `1px solid ${C.red}33`, borderRadius: 8, fontSize: 14, color: C.red, marginBottom: 16 }}>
          ⚠ Backend error: {error}
        </div>
      )}

      {!loading && !error && products.length === 0 && (
        <div style={{ ...S.card, textAlign: "center", padding: "48px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 14 }}>📭</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 8 }}>No impacted products found</div>
          <div style={{ fontSize: 14, color: C.muted, maxWidth: 420, margin: "0 auto" }}>
            The Knowledge Graph returned no results for the impacted products query.<br /><br />
            This likely means the SPARQL query namespace doesn't match the ontology. Check that the backend prefix matches:
            <code style={{ display: "block", marginTop: 10, padding: "8px 12px", background: C.bg, borderRadius: 6, fontSize: 12, color: C.accent }}>
              http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#
            </code>
          </div>
        </div>
      )}

      {!loading && products.length > 0 && (
        <>
          {/* Traffic light cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14, marginBottom: 22 }}>
            {products.map((p, i) => {
              const isAtRisk  = p.status === "RED";
              const isWarning = p.status === "YELLOW";
              const color = isAtRisk ? C.red : isWarning ? C.orange : C.green;
              return (
                <div key={i} className="card-hover"
                  onClick={() => setSelected(selected === i ? null : i)}
                  style={{ ...S.card, cursor: "pointer", borderTop: `3px solid ${color}`, outline: selected === i ? `2px solid ${color}` : "none", outlineOffset: 2 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ width: 12, height: 12, borderRadius: "50%", background: color, boxShadow: `0 0 10px ${color}` }} className="glow-dot" />
                    <span style={S.riskBadge(isAtRisk ? "HIGH" : isWarning ? "MEDIUM" : "LOW")}>
                      {isAtRisk ? "AT RISK" : isWarning ? "DELAYED" : "OK"}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 6 }}>{p.materialLabel || p.material || "—"}</div>
                  <div style={{ fontSize: 12, color: C.muted }}>{p.supplierLabel || p.supplier || "—"}</div>
                  {(p.processLabel || p.process) && (
                    <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>Process: {p.processLabel || p.process}</div>
                  )}
                  {isWarning && (
                    <div style={{ fontSize: 11, color: C.orange, marginTop: 6, fontWeight: 600 }}>
                      {(p.stock > 0 || p.threshold > 0)
                        ? "⚡ Delivery delayed — stock still OK"
                        : "⚡ Delivery delayed — stock data unavailable"}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Detail table */}
          <div style={S.card}>
            <div style={S.cardHeader}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={S.cardTitle}>📊 Full Results from Knowledge Graph</span>
                <span style={S.badge(C.green)}>{products.length} rows</span>
              </div>
              <button
                style={S.btn("secondary")}
                onClick={handleDownloadExcel}
              >
                📥 Download Excel
              </button>
            </div>
            <table style={S.table}>
              <thead>
                <tr>
                  {Object.keys(products[0] || {})
                    .filter(k => k in COLUMN_HEADERS)
                    .map(k => (
                      <th key={k} style={S.th}>{COLUMN_HEADERS[k]}</th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {products.map((p, i) => (
                  <tr key={i} className="data-row">
                    {Object.keys(p)
                      .filter(k => k in COLUMN_HEADERS)
                      .map(k => {
                        let val = p[k];
                        if (k === "reliabilityScore" && val !== null) {
                          val = `${(parseFloat(val) * 100).toFixed(0)}%`;
                        } else if (k === "leadTime" && val !== null) {
                          val = `${val}d`;
                        }

                        if (k === "status") {
                          const isRed = val === "RED";
                          const isYellow = val === "YELLOW";
                          const badgeText = isRed ? "Critical Risk" : isYellow ? "Warning (Delayed)" : "Healthy";
                          const color = isRed ? C.red : isYellow ? C.orange : C.green;
                          return (
                            <td key={k} style={{ ...S.td, fontSize: 13 }}>
                              <span style={S.badge(color)}>{badgeText}</span>
                            </td>
                          );
                        }

                        return (
                          <td key={k} style={{ ...S.td, fontSize: 13 }}>{String(val ?? "—")}</td>
                        );
                      })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {selected !== null && products[selected] && (
        <div style={{ ...S.card, marginTop: 16, borderLeft: `4px solid ${C.blue}` }}>
          <div style={{ ...S.cardTitle, marginBottom: 12 }}>🔍 Detail — {products[selected].materialLabel || products[selected].material}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {(products[selected].status === "RED" || products[selected].status === "YELLOW") && (
              <div style={{ display: "flex", gap: 8 }}>
                <button style={S.btn()} onClick={() => {
                  if (user?.role === "production") {
                    setShowConfirmModal(true);
                    setRequestResult(null);
                  } else {
                    onNavigate("suppliers");
                  }
                }}>
                  {user?.role === "production"
                    ? (products[selected].status === "RED" ? "🚨 Request Fallback Supplier" : "⚡ Proactive Fallback Request")
                    : "🔄 Find Fallback Supplier"}
                </button>
              </div>
            )}
            
            <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.muted, marginBottom: 8 }}>🤖 Ask AI Assistant:</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button style={{ ...S.btn("ghost"), fontSize: 12 }} onClick={() => {
                  const mat = products[selected].materialLabel || products[selected].material || "";
                  onNavigate("ai", `Are there any alternative suppliers for ${mat}?`);
                }}>🔍 Alternative Suppliers</button>
                
                <button style={{ ...S.btn("ghost"), fontSize: 12 }} onClick={() => {
                  const mat = products[selected].materialLabel || products[selected].material || "";
                  onNavigate("ai", `Which production lines are affected by ${mat}?`);
                }}>🏭 Impacted Production Lines</button>
                
                <button style={{ ...S.btn("ghost"), fontSize: 12 }} onClick={() => {
                  const mat = products[selected].materialLabel || products[selected].material || "";
                  onNavigate("ai", `What is the inventory stock and safety stock level of ${mat}?`);
                }}>📦 Stock Levels</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Urgent Fallback Request Modal for Production Manager */}
      {showConfirmModal && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(10,14,26,0.85)", backdropFilter: "blur(4px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20
        }} onClick={() => !isSubmitting && setShowConfirmModal(false)}>
          <div style={{
            background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14,
            width: "100%", maxWidth: 480, boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            overflow: "hidden"
          }} onClick={e => e.stopPropagation()}>
            
            {/* Modal Header */}
            <div style={{
              padding: "16px 20px", background: C.bg, borderBottom: `1px solid ${C.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center"
            }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>⚠️ Urgent Fallback Request</div>
                <div style={{ fontSize: 12, color: C.muted }}>Material: <span style={{ color: C.accent, fontWeight: 600 }}>{products[selected]?.materialLabel || products[selected]?.material || ""}</span></div>
              </div>
              {!isSubmitting && (
                <button onClick={() => setShowConfirmModal(false)} style={{ background: "none", border: "none", color: C.muted, cursor: "pointer", fontSize: 18 }}>✕</button>
              )}
            </div>

            {/* Modal Body */}
            <div style={{ padding: "20px" }}>
              {requestResult ? (
                <div style={{ textAlign: "center", padding: "12px 0" }}>
                  {requestResult.success ? (
                    <>
                      <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: C.green, marginBottom: 8 }}>Request Sent Successfully</div>
                      <div style={{ fontSize: 13, color: C.textSoft, lineHeight: 1.5, marginBottom: 18 }}>
                        {requestResult.message}
                      </div>
                    </>
                  ) : (
                    <>
                      <div style={{ fontSize: 40, marginBottom: 12 }}>❌</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: C.red, marginBottom: 8 }}>Request Failed</div>
                      <div style={{ fontSize: 13, color: C.textSoft, lineHeight: 1.5, marginBottom: 18 }}>
                        {requestResult.message}
                      </div>
                    </>
                  )}
                  <button style={S.btn("secondary")} onClick={() => { setShowConfirmModal(false); setRequestResult(null); }}>Close</button>
                </div>
              ) : (
                <>
                  <div style={{ fontSize: 13, color: C.textSoft, lineHeight: 1.6, marginBottom: 16 }}>
                    {products[selected]?.status === "YELLOW" ? (
                      (() => {
                        const p = products[selected];
                        const hasStockData = p && (p.stock > 0 || p.threshold > 0);
                        return hasStockData ? (
                          <>
                            A delay has been detected for this material's supplier, but stock is
                            currently <strong style={{ color: C.green }}>above the safety threshold</strong>.
                            Requesting a proactive fallback now gives the logistics team time to
                            source an alternative <em>before</em> stock runs out.
                          </>
                        ) : (
                          <>
                            A delay has been detected for this material's supplier.
                            <strong style={{ color: C.orange }}> Stock data is not available</strong> in the
                            knowledge graph — act proactively to avoid a potential shortage.
                          </>
                        );
                      })()
                    ) : (
                      <>This material's safety stock buffer is depleted by <strong style={{ color: C.red }}>{(() => {
                        const p = products[selected];
                        if (!p) return 0;
                        const stock = p.stock || 0;
                        const threshold = p.threshold || 0;
                        return threshold > 0 ? Math.max(0, Math.round(((threshold - stock) / threshold) * 100)) : 0;
                      })()}%</strong>.</>
                    )}
                  </div>
                  <div style={{ fontSize: 13, color: C.textSoft, lineHeight: 1.6, marginBottom: 20 }}>
                    Would you like to send an urgent fallback supplier request to the <strong style={{ color: C.blue }}>Logistics Manager</strong>?
                    The system will automatically generate a <strong style={{
                      color: (() => {
                        const p = products[selected];
                        if (!p) return C.muted;
                        // YELLOW: stock is above threshold, use fixed HIGH (50) since delay is active
                        if (p.status === "YELLOW") return C.orange;
                        const stock = p.stock || 0;
                        const threshold = p.threshold || 0;
                        const riskPercent = threshold > 0 ? Math.max(0, Math.round(((threshold - stock) / threshold) * 100)) : 0;
                        return riskPercent >= 75 ? C.red : riskPercent >= 40 ? C.orange : C.green;
                      })()
                    }}>{(() => {
                      const p = products[selected];
                      if (!p) return "LOW";
                      // YELLOW: delay is real but stock is OK → HIGH proactive alert
                      if (p.status === "YELLOW") return "HIGH";
                      const stock = p.stock || 0;
                      const threshold = p.threshold || 0;
                      const riskPercent = threshold > 0 ? Math.max(0, Math.round(((threshold - stock) / threshold) * 100)) : 0;
                      return riskPercent >= 75 ? "CRITICAL" : riskPercent >= 40 ? "HIGH" : "LOW";
                    })()}</strong> priority alert.
                  </div>

                  {/* Actions */}
                  <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                    <button style={S.btn("ghost")} disabled={isSubmitting} onClick={() => setShowConfirmModal(false)}>Cancel</button>
                    <button style={S.btn("primary")} disabled={isSubmitting} onClick={async () => {
                      setIsSubmitting(true);
                      try {
                        const p = products[selected];
                        // YELLOW: stock is above safety threshold so the depletion formula gives 0.
                        // Use a fixed 50 (maps to HIGH severity) — a delay is active and we need
                        // logistics to act proactively before stock actually runs out.
                        const isYellow = p.status === "YELLOW";
                        const stock = p.stock || 0;
                        const threshold = p.threshold || 0;
                        const riskPercent = isYellow
                          ? 50
                          : (threshold > 0 ? Math.max(0, Math.round(((threshold - stock) / threshold) * 100)) : 0);
                        // Automatically put underscores in name
                        const rawMat = p.materialLabel || p.material || "";
                        const materialClean = rawMat.trim().replace(/ /g, "_");

                        const res = await requestFallbackSupplier(materialClean, riskPercent);
                        setRequestResult({
                          success: true,
                          message: `An urgent fallback supplier request has been generated with ${res.severity} priority (ID: ${res.alert_id}). Ahmed Hassan (Logistics Manager) and Omar Nasser (Production Manager) will track this in their Alert Center.`
                        });
                      } catch (err) {
                        setRequestResult({
                          success: false,
                          message: err.message || "Failed to create fallback request alert."
                        });
                      } finally {
                        setIsSubmitting(false);
                      }
                    }}>
                      {isSubmitting ? "Sending..." : "✓ Send Request"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

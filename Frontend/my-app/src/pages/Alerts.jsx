import { useState, useEffect } from "react";
import { C, S } from "../styles/theme";
import { fetchAlerts, markAlertRead, dismissAlert, fetchAssemblyLines, assignMaterialToProcess } from "../services/api";

const TYPE_COLOR = {
  CRITICAL: C.red,
  HIGH: C.orange,
  INFO: C.blue,
  LOW: C.green,
  ESCALATION: C.purple,
};

const TYPE_ICON = {
  CRITICAL: "🚨",
  HIGH: "⚠️",
  INFO: "ℹ️",
  LOW: "✅",
  ESCALATION: "📩",
};

// ── Detail Modal ─────────────────────────────────────────────────────────────
function AlertDetailModal({ alert: a, onClose, onDismiss, onAssigned }) {
  const typeColor = a ? (TYPE_COLOR[a.type] || C.muted) : C.muted;
  const isNewMaterial = a ? a.category === "New Material" : false;

  const [assemblyLines, setAssemblyLines]       = useState([]);
  const [selectedProcess, setSelectedProcess]   = useState("");
  const [safetyStock, setSafetyStock]           = useState("");
  const [assigning, setAssigning]               = useState(false);
  const [assignSuccess, setAssignSuccess]       = useState(false);
  const [assignError, setAssignError]           = useState("");
  const [isNewProcess, setIsNewProcess]         = useState(false);
  const [newProcessName, setNewProcessName]     = useState("");

  useEffect(() => {
    if (isNewMaterial) {
      fetchAssemblyLines()
        .then(data => setAssemblyLines(data?.assembly_lines || []))
        .catch(() => {});
    }
  }, [isNewMaterial]);

  const handleAssign = async () => {
    const processToAssign = isNewProcess ? newProcessName.trim() : selectedProcess;
    
    if (!processToAssign) {
      setAssignError(isNewProcess ? "Please enter a brand-new assembly line name." : "Please select an assembly line.");
      return;
    }
    if (!safetyStock || parseInt(safetyStock, 10) <= 0) {
      setAssignError("Please enter a valid positive safety stock level.");
      return;
    }
    setAssigning(true); setAssignError("");
    try {
      await assignMaterialToProcess(a.materialName || a.desc, processToAssign, a.id, safetyStock);
      setAssignSuccess(true);
      if (onAssigned) onAssigned(a.id);
    } catch (err) {
      setAssignError("Failed to assign. Please try again.");
    } finally {
      setAssigning(false);
    }
  };

  if (!a) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.65)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: C.surface, borderRadius: 16, width: "100%", maxWidth: 560,
          border: `1px solid ${C.border}`,
          boxShadow: "0 24px 80px rgba(0,0,0,0.6)",
          overflow: "hidden",
          maxHeight: "90vh",
          display: "flex", flexDirection: "column",
        }}
      >
        {/* Header stripe */}
        <div style={{
          borderLeft: `6px solid ${typeColor}`,
          padding: "20px 24px",
          borderBottom: `1px solid ${C.border}`,
          display: "flex", alignItems: "flex-start", gap: 16,
          flexShrink: 0,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: typeColor + "20",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 24, flexShrink: 0,
          }}>
            {a.icon || TYPE_ICON[a.type] || "🔔"}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
              <span style={{ ...S.badge(typeColor), fontSize: 11 }}>{a.type}</span>
              <span style={{ ...S.badge(C.blue), fontSize: 11 }}>{a.category}</span>
              {a.unread && <span style={{ ...S.badge(C.accent), fontSize: 11 }}>UNREAD</span>}
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text, lineHeight: 1.4 }}>{a.title}</div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: C.muted, fontSize: 20, cursor: "pointer", lineHeight: 1, padding: 4, flexShrink: 0 }}
          >✕</button>
        </div>

        {/* Scrollable body */}
        <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1 }}>
          {/* Full description */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: C.muted, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>
              Description
            </div>
            <div style={{
              fontSize: 14, color: C.text, lineHeight: 1.7,
              background: C.bg, borderRadius: 10, padding: "14px 16px",
              border: `1px solid ${C.border}`,
            }}>
              {a.desc || "No additional description available."}
            </div>
          </div>

          {/* Metadata grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
            {[
              { label: "Severity", value: a.type, color: typeColor },
              { label: "Category", value: a.category },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ background: C.bg, borderRadius: 8, padding: "10px 14px", border: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 10, color: C.muted, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                  {label}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: color || C.text }}>{value}</div>
              </div>
            ))}
          </div>

          {/* ── New Material: Assembly Line Assignment ── */}
          {isNewMaterial && (
            <div style={{ background: C.orange + "10", border: `1px solid ${C.orange}44`, borderRadius: 12, padding: "16px 18px", marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.orange, marginBottom: 10 }}>🏭 Assign Assembly Line</div>
              {assignSuccess ? (
                <div style={{ fontSize: 13, color: C.green, fontWeight: 600 }}>✅ Successfully assigned! The material is now linked to the selected assembly line.</div>
              ) : (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontSize: 12, color: C.muted }}>
                      {isNewProcess ? "Enter brand-new assembly line name:" : "Select which assembly line this material belongs to:"}
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setIsNewProcess(!isNewProcess);
                        setAssignError("");
                      }}
                      style={{
                        background: "none", border: "none",
                        color: C.orange, fontSize: 11, fontWeight: 600,
                        cursor: "pointer", textDecoration: "underline",
                        padding: 0,
                      }}
                    >
                      {isNewProcess ? "Select existing line" : "Create new line"}
                    </button>
                  </div>

                  {isNewProcess ? (
                    <input
                      type="text"
                      placeholder="e.g. EV Battery Pack Assembly Line"
                      value={newProcessName}
                      onChange={e => setNewProcessName(e.target.value)}
                      style={{ ...S.input, width: "100%", marginBottom: 14, background: C.bg, color: C.text }}
                    />
                  ) : (
                    <select
                      value={selectedProcess}
                      onChange={e => setSelectedProcess(e.target.value)}
                      style={{ ...S.input, width: "100%", marginBottom: 14, background: C.bg, color: C.text }}
                    >
                      <option value="">-- Select Assembly Line --</option>
                      {assemblyLines.map(line => (
                        <option key={line} value={line}>{line.replace(/_/g, " ")}</option>
                      ))}
                    </select>
                  )}

                  <div style={{ fontSize: 12, color: C.muted, marginBottom: 6 }}>Enter Safety Stock Level (units):</div>
                  <input
                    type="number"
                    min="1"
                    placeholder="e.g. 100"
                    value={safetyStock}
                    onChange={e => setSafetyStock(e.target.value)}
                    style={{ ...S.input, width: "100%", marginBottom: 14, background: C.bg, color: C.text }}
                  />

                  {assignError && <div style={{ color: C.red, fontSize: 12, marginBottom: 8 }}>{assignError}</div>}
                  <button
                    onClick={handleAssign}
                    disabled={!(isNewProcess ? newProcessName.trim() : selectedProcess) || !safetyStock || assigning}
                    style={{
                      ...S.btn(),
                      fontSize: 13,
                      opacity: (!(isNewProcess ? newProcessName.trim() : selectedProcess) || !safetyStock || assigning) ? 0.6 : 1,
                      width: "100%",
                    }}
                  >
                    {assigning ? "⚙ Assigning..." : "✓ Assign Assembly Line & Safety Stock"}
                  </button>
                </>
              )}
            </div>
          )}

          {/* Escalation notice */}
          {a.type === "ESCALATION" && (
            <div style={{
              background: C.purple + "10", border: `1px solid ${C.purple}33`,
              borderRadius: 10, padding: "12px 16px", marginBottom: 8,
              display: "flex", gap: 10, alignItems: "flex-start",
            }}>
              <span style={{ fontSize: 18 }}>📩</span>
              <div style={{ fontSize: 13, color: C.purple, lineHeight: 1.5 }}>
                This alert was escalated by <strong>{a.from}</strong> ({a.fromRole}) and requires your acknowledgment.
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div style={{ padding: "14px 24px", borderTop: `1px solid ${C.border}`, display: "flex", gap: 10, justifyContent: "flex-end", flexShrink: 0 }}>
          {a.type === "ESCALATION" && (
            <button style={{ ...S.btn(), fontSize: 13 }}>✓ Acknowledge</button>
          )}
          <button
            onClick={() => { onDismiss(a.id); onClose(); }}
            style={{ ...S.btn("ghost"), fontSize: 13, color: C.red, borderColor: C.red + "55" }}
          >
            Dismiss Alert
          </button>
          <button onClick={onClose} style={{ ...S.btn("secondary"), fontSize: 13 }}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Alerts({ user, initialAlertId, clearInitialAlertId, onAlertsChanged }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [filter, setFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [expanded, setExpanded] = useState(null);
  const [detailAlert, setDetailAlert] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const formatTimestamp = (ts) => {
      if (!ts) return "";
      let value = ts;
      if (typeof value === "string" && !/[+-]\\d{2}:?\\d{2}$|Z$/.test(value)) {
        value = value.replace(" ", "T") + "Z";
      }
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return ts;
      const adjusted = new Date(dt.getTime() + 60 * 60 * 1000);
      const year = adjusted.getUTCFullYear();
      const month = String(adjusted.getUTCMonth() + 1).padStart(2, "0");
      const day = String(adjusted.getUTCDate()).padStart(2, "0");
      const hour = String(adjusted.getUTCHours());
      const minute = String(adjusted.getUTCMinutes()).padStart(2, "0");
      return `${year}-${month}-${day} ${hour}:${minute}`;
    };

    const normalizeAlert = (alert) => {
      const rawTs = alert.createdAt || alert.date || alert.time;
      const formatted = formatTimestamp(rawTs);
      return {
        ...alert,
        createdAt: rawTs,
        timestamp: formatted || alert.time || alert.date || "",
        time: formatted || alert.time || "",
        date: formatted || alert.date || "",
      };
    };

    const load = (isFirstLoad) => {
      fetchAlerts()
        .then(data => {
          if (cancelled) return;
          const items = (data || []).map(normalizeAlert);
          items.sort((a, b) => new Date(b.createdAt || b.date || b.time || 0) - new Date(a.createdAt || a.date || a.time || 0));
          setAlerts(items);
          setFetchError("");
          // If we arrived here from a notification click, auto-open that alert
          if (isFirstLoad && initialAlertId) {
            const target = items.find(a => a.id === initialAlertId);
            if (target) {
              setDetailAlert(target);
              setExpanded(target.id);
            }
            if (clearInitialAlertId) clearInitialAlertId();
          }
        })
        .catch(err => {
          if (cancelled) return;
          setFetchError(err.message);
        })
        .finally(() => {
          if (!cancelled && isFirstLoad) setLoading(false);
        });
    };

    load(true);
    const intervalId = setInterval(() => load(false), 5000);
    return () => { cancelled = true; clearInterval(intervalId); };
  }, [initialAlertId]);

  const markRead = async (id) => {
    setAlerts(p => p.map(a => a.id === id ? { ...a, unread: false } : a));
    if (onAlertsChanged) onAlertsChanged();
    try { await markAlertRead(id); } catch (e) { console.error("Failed to mark read:", e); }
  };

  const markAllRead = async () => {
    const unreadIds = alerts.filter(a => a.unread).map(a => a.id);
    if (unreadIds.length === 0) return;
    setAlerts(p => p.map(a => ({ ...a, unread: false })));
    if (onAlertsChanged) onAlertsChanged();
    try {
      await Promise.all(unreadIds.map(id => markAlertRead(id)));
    } catch (e) {
      console.error("Failed to mark all read:", e);
    }
  };

  const dismiss = async (id) => {
    setAlerts(p => p.filter(a => a.id !== id));
    try { await dismissAlert(id); } catch (e) { console.error("Failed to dismiss:", e); }
  };

  const myAlerts = alerts.filter(a => !user || user.role === "admin" || !a.roles || a.roles.includes(user.role));

  const filtered = myAlerts.filter(a => {
    const catMatch = filter === "All" || a.category === filter;
    const typeMatch = typeFilter === "All" || a.type === typeFilter;
    return catMatch && typeMatch;
  });

  const unreadCount = myAlerts.filter(a => a.unread).length;
  const escalations = myAlerts.filter(a => a.type === "ESCALATION");

  return (
    <div>
      {/* Detail modal */}
      <AlertDetailModal
        alert={detailAlert}
        onClose={() => setDetailAlert(null)}
        onDismiss={dismiss}
        onAssigned={(id) => {
          dismiss(id);
          setDetailAlert(null);
        }}
      />

      <div style={{ ...S.pageHeader, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={S.pageTitle}>Alerts · Notifications Center</div>
            {unreadCount > 0 && (
              <span style={{ padding: "3px 10px", borderRadius: 20, background: C.red + "22", color: C.red, fontSize: 13, fontWeight: 700 }}>
                {unreadCount} unread
              </span>
            )}
          </div>
          <div style={S.pageDesc}>System alerts, SLA breaches and supply chain notifications</div>
        </div>
        {unreadCount > 0 && (
          <button style={S.btn("ghost")} className="btn-hover" onClick={markAllRead}>✓ Mark all read</button>
        )}
      </div>

      {/* Escalation banner */}
      {escalations.filter(e => e.unread).length > 0 && (
        <div style={{ ...S.card, marginBottom: 16, borderLeft: `4px solid ${C.purple}`, background: C.purple + "08", padding: "14px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>📩</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.purple }}>
                {escalations.filter(e => e.unread).length} Escalation{escalations.filter(e => e.unread).length > 1 ? "s" : ""} Require Your Attention
              </div>
              {escalations.filter(e => e.unread).map(e => (
                <div key={e.id} style={{ fontSize: 12, color: C.muted, marginTop: 3 }}>
                  From <span style={{ color: C.purple, fontWeight: 700 }}>{e.from}</span> ({e.fromRole}): {e.title}
                </div>
              ))}
            </div>
            <span style={S.badge(C.purple)}>ACTION REQUIRED</span>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ ...S.card, textAlign: "center", padding: "40px", color: C.accent, marginBottom: 16 }}>
          <div style={{ fontSize: 24, marginBottom: 10 }} className="spin">⚙</div>
          Loading live alerts from Knowledge Graph...
        </div>
      )}

      {fetchError && (
        <div style={{ padding: "12px 16px", background: C.red + "15", border: `1px solid ${C.red}33`, borderRadius: 8, fontSize: 13, color: C.red, marginBottom: 16 }}>
          ⚠ Backend error: {fetchError} — Check that the server is running at <strong>http://localhost:8001</strong>
        </div>
      )}

      {/* Summary KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginBottom: 20 }}>
        {[
          { label: "Total Alerts", value: myAlerts.length, color: C.blue },
          { label: "Unread", value: unreadCount, color: C.red },
          { label: "Critical / High", value: myAlerts.filter(a => a.type === "CRITICAL" || a.type === "HIGH").length, color: C.orange },
        ].map((k, i) => (
          <div key={i} style={{ ...S.card, borderTop: `3px solid ${k.color}`, padding: 16 }}>
            <div style={{ fontSize: 11, color: C.muted, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.07em" }}>{k.label}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: k.color }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {[
            "All",
            "SLA Breach",
            "Inventory",
            ...(!user || user.role === "admin" || user.role === "production" ? ["New Material"] : []),
            ...(!user || user.role === "admin" || user.role === "production" || user.role === "logistics" ? ["Production Disruption"] : [])
          ].map(cat => (
            <button key={cat} className="tab-btn" onClick={() => setFilter(cat)} style={{
              padding: "5px 12px", borderRadius: 6,
              background: filter === cat ? C.accent : "transparent",
              border: `1px solid ${filter === cat ? C.accent : C.border}`,
              cursor: "pointer", fontSize: 12, fontFamily: "inherit",
              color: filter === cat ? "#000" : C.muted,
              fontWeight: filter === cat ? 700 : 400,
            }}>{cat}</button>
          ))}
        </div>
        <div style={{ width: 1, background: C.border }} />
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {["All", "CRITICAL", "HIGH", "LOW"].map(type => (
            <button key={type} className="tab-btn" onClick={() => setTypeFilter(type)} style={{
              padding: "5px 12px", borderRadius: 6,
              background: typeFilter === type ? (TYPE_COLOR[type] || C.accent) + "22" : "transparent",
              border: `1px solid ${typeFilter === type ? (TYPE_COLOR[type] || C.accent) : C.border}`,
              cursor: "pointer", fontSize: 12, fontFamily: "inherit",
              color: typeFilter === type ? (TYPE_COLOR[type] || C.accent) : C.muted,
              fontWeight: typeFilter === type ? 700 : 400,
            }}>{type}</button>
          ))}
        </div>
      </div>

      {filtered.length === 0 && (
        <div style={{ ...S.card, textAlign: "center", padding: "56px 24px" }}>
          <div style={{ fontSize: 44, marginBottom: 14 }}>🔔</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 8 }}>No alerts yet</div>
          <div style={{ fontSize: 14, color: C.muted, maxWidth: 400, margin: "0 auto", lineHeight: 1.6 }}>
            Alerts will appear here when the backend generates them — SLA breaches, inventory risks, supplier delays and escalations.
          </div>
        </div>
      )}

      {/* Alert cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map(a => {
          const typeColor = TYPE_COLOR[a.type] || C.muted;
          const isExpanded = expanded === a.id;
          return (
            <div key={a.id} style={{ ...S.card, borderLeft: `4px solid ${typeColor}`, padding: 0, overflow: "hidden", background: a.unread ? C.blue + "0A" : C.surface, transition: "all 0.15s" }}>
              <div
                style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: "14px 18px", cursor: "pointer" }}
                onClick={() => { setExpanded(isExpanded ? null : a.id); markRead(a.id); }}
              >
                <div style={{ width: 42, height: 42, borderRadius: 10, flexShrink: 0, background: typeColor + "18", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>
                  {a.icon || TYPE_ICON[a.type] || "🔔"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: a.unread ? 700 : 600, color: C.text }}>{a.title}</span>
                      {a.unread && <div style={{ width: 7, height: 7, borderRadius: "50%", background: typeColor, boxShadow: `0 0 5px ${typeColor}` }} />}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      <span style={{ ...S.badge(typeColor), fontSize: 11 }}>{a.type}</span>
                      <span style={{ fontSize: 12, color: C.muted }}>{a.timestamp || a.time}</span>
                    </div>
                  </div>
                  {a.from && (
                    <div style={{ fontSize: 12, color: C.purple, marginBottom: 4 }}>
                      📩 From: <span style={{ fontWeight: 700 }}>{a.from}</span> · {a.fromRole}
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: C.muted, marginBottom: 4 }}>
                    <span style={{ ...S.badge(C.blue), fontSize: 10, marginRight: 6 }}>{a.category}</span>
                    {a.timestamp || a.date}
                  </div>
                  <div style={{ fontSize: 13, color: C.text, lineHeight: 1.5 }}>
                    {isExpanded ? a.desc : (a.desc || "").slice(0, 100) + (a.desc?.length > 100 ? "..." : "")}
                  </div>
                </div>
                <span style={{ color: C.muted, fontSize: 12, flexShrink: 0 }}>{isExpanded ? "▲" : "▼"}</span>
              </div>

              {isExpanded && (
                <div style={{ padding: "0 18px 14px 74px", display: "flex", gap: 8 }}>
                  {a.type === "ESCALATION" && (
                    <button style={{ ...S.btn(), fontSize: 12, padding: "6px 14px" }}>✓ Acknowledge</button>
                  )}
                  <button
                    onClick={e => { e.stopPropagation(); markRead(a.id); setDetailAlert(a); }}
                    style={{ ...S.btn("secondary"), fontSize: 12, padding: "6px 14px" }}
                  >
                    View Details
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); dismiss(a.id); }}
                    style={{ ...S.btn("ghost"), fontSize: 12, padding: "6px 14px", marginLeft: "auto", color: C.red }}
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

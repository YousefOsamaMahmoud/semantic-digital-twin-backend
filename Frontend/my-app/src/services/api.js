// ============================================================
// services/api.js — Live Backend Only (no mock data)
// All data comes from FastAPI at http://localhost:8001
// ============================================================

const BASE = process.env.REACT_APP_API_URL || "http://localhost:8001";

async function safeFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

// GET /api/dashboard/risk-scores
export async function fetchRiskScores() {
  const data = await safeFetch(`${BASE}/api/dashboard/risk-scores`);
  return data.risk_scores || [];
}

// GET /api/dashboard/compliance-alerts
export async function fetchComplianceAlerts() {
  const data = await safeFetch(`${BASE}/api/dashboard/compliance-alerts`);
  return data.alerts || [];
}

// GET /api/dashboard/kpis
export async function fetchKPIs(role) {
  const url = role ? `${BASE}/api/dashboard/kpis?role=${encodeURIComponent(role)}` : `${BASE}/api/dashboard/kpis`;
  const data = await safeFetch(url);
  return data.kpis || {};
}

// GET /api/dashboard/alerts
export async function fetchAlerts() {
  const data = await safeFetch(`${BASE}/api/dashboard/alerts`);
  return data.alerts || [];
}

export async function markAlertRead(alertId) {
  return safeFetch(`${BASE}/api/dashboard/alerts/mark-read`, {
    method: "POST",
    body: JSON.stringify({ alert_id: alertId }),
  });
}

export async function dismissAlert(alertId) {
  return safeFetch(`${BASE}/api/dashboard/alerts/dismiss`, {
    method: "POST",
    body: JSON.stringify({ alert_id: alertId }),
  });
}

// GET /api/dashboard/fallback-options/{material_id}
export async function fetchFallbackOptions(material) {
  const data = await safeFetch(
    `${BASE}/api/dashboard/fallback-options/${encodeURIComponent(material)}`
  );
  return data.suppliers || [];
}

// POST /api/dashboard/assign-fallback
export async function assignFallback(material, supplierName, assignmentType) {
  return safeFetch(`${BASE}/api/dashboard/assign-fallback`, {
    method: "POST",
    body: JSON.stringify({ material, supplierName, assignmentType }),
  });
}

// POST /api/dashboard/request-fallback
export async function requestFallbackSupplier(material, riskPercent) {
  return safeFetch(`${BASE}/api/dashboard/request-fallback`, {
    method: "POST",
    body: JSON.stringify({ material, risk_percent: riskPercent }),
  });
}

// GET /api/sandbox/impacted-products
export async function fetchImpactedProducts() {
  const data = await safeFetch(`${BASE}/api/sandbox/impacted-products`);
  return data.impacted_products || [];
}

// POST /api/sandbox/simulate-iot
export async function simulateIoTEvent(eventPayload) {
  return safeFetch(`${BASE}/api/sandbox/simulate-iot`, {
    method: "POST",
    body: JSON.stringify(eventPayload),
  });
}

// ── AI Chat ───────────────────────────────────────────────────────────────────

// POST /api/dashboard/chat
export async function sendChatMessage(question) {
  const data = await safeFetch(`${BASE}/api/dashboard/chat`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
  if (!data.topic_accepted) {
    return {
      answer: "I'm a Supply Chain assistant. I can only answer questions about deliveries, suppliers, materials, SLA agreements, and logistics.",
      sparql: ""
    };
  }
  return {
    answer: data.answer || "No answer returned from the model.",
    sparql: data.sparql || ""
  };
}

// ── SLA Upload — Step 1 ───────────────────────────────────────────────────────

// POST /api/sandbox/upload-pdf
export async function uploadSLAPdf(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/sandbox/upload-pdf`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: HTTP ${res.status}`);
  }
  return res.json();
}

// ── SLA Upload — Step 2 ───────────────────────────────────────────────────────

// POST /api/sandbox/confirm-sla
export async function confirmSLA(confirmedData) {
  return safeFetch(`${BASE}/api/sandbox/confirm-sla`, {
    method: "POST",
    body: JSON.stringify(confirmedData),
  });
}

// GET /api/sandbox/match-assembly-line?material=<name>
export async function matchAssemblyLine(material) {
  return safeFetch(`${BASE}/api/sandbox/match-assembly-line?material=${encodeURIComponent(material)}`);
}

// GET /api/dashboard/active-sla?supplier=<name>&material=<name>
export async function fetchActiveSLA(supplier, material) {
  return safeFetch(`${BASE}/api/dashboard/active-sla?supplier=${encodeURIComponent(supplier)}&material=${encodeURIComponent(material)}`);
}

// GET /api/dashboard/assembly-lines
export async function fetchAssemblyLines() {
  return safeFetch(`${BASE}/api/dashboard/assembly-lines`);
}

// POST /api/dashboard/assign-material-process
export async function assignMaterialToProcess(material, process, alertId = null, safetyStock = null) {
  const payload = { material, process, alert_id: alertId };
  if (safetyStock !== null && safetyStock !== undefined && safetyStock !== "") {
    payload.safety_stock = parseInt(safetyStock, 10);
  }
  return safeFetch(`${BASE}/api/dashboard/assign-material-process`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


// POST /api/sandbox/upload-transactions
export async function uploadTransactions(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/sandbox/upload-transactions`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: HTTP ${res.status}`);
  }
  return res.json();
}

// ── Backend health check ──────────────────────────────────────────────────────

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${BASE}/`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return { online: true, message: data.message || "OK" };
    }
    return { online: false, message: "Backend error" };
  } catch {
    return { online: false, message: "Backend offline" };
  }
}

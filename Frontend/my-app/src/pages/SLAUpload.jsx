import { useState, useEffect } from "react";
import { C, S } from "../styles/theme";
import { uploadSLAPdf, confirmSLA, matchAssemblyLine, fetchActiveSLA } from "../services/api";

// ── Field must be defined OUTSIDE the parent component so React
// does not remount it on every keystroke (which caused typing to break)
function Field({ label, field, type = "text", editedFields, setEditedFields, error, step }) {
  const value = editedFields[field];
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ fontSize: 12, color: C.muted, display: "block", marginBottom: 5, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
        {label}
      </label>
      <input
        type={type}
        step={step}
        value={value !== undefined && value !== null ? value : ""}
        onChange={e => setEditedFields(p => ({ ...p, [field]: e.target.value }))}
        style={{ ...S.input, borderColor: error ? C.red : C.border, background: error ? C.red + "0A" : C.bg }}
      />
      {error && <div style={{ color: C.red, fontSize: 11, marginTop: 4, fontWeight: 500 }}>{error}</div>}
    </div>
  );
}

const pipelineSteps = [
  "📤 File uploaded to staging",
  "🤖 LLM extracting entities...",
  "🔍 Validating contract structure...",
  "✅ Extraction complete",
];

export default function SLAUpload({ user }) {
  const [dragging,     setDragging]     = useState(false);
  const [step,         setStep]         = useState("idle"); // idle | extracting | review | confirming | done | error
  const [extraction,   setExtraction]   = useState(null);
  const [editedFields, setEditedFields] = useState({});
  const [confirmed,    setConfirmed]    = useState(null);
  const [error,        setError]        = useState("");
  const [formErrors,   setFormErrors]   = useState({});
  const [pipelineStep, setPipelineStep] = useState(0);
  const [assemblyMatch, setAssemblyMatch] = useState(null); // { matched, process } | null
  const [fileName,     setFileName]     = useState("");
  const [fileSize,     setFileSize]     = useState("");
  const [copied,       setCopied]       = useState(false);
  const [fileObject,   setFileObject]   = useState(null);
  const [fileUrl,      setFileUrl]      = useState("");
  const [existingSLA,  setExistingSLA]  = useState(null);
  const [checkingSLA,  setCheckingSLA]  = useState(false);

  useEffect(() => {
    const materialName = editedFields.material;
    if (!materialName || step !== "review") {
      return;
    }

    setAssemblyMatch(null); // Show checking/loading state

    const delayDebounceFn = setTimeout(() => {
      matchAssemblyLine(materialName)
        .then(match => {
          if (editedFields.material === materialName) {
            setAssemblyMatch(match);
          }
        })
        .catch(() => {
          if (editedFields.material === materialName) {
            setAssemblyMatch({ matched: false, process: null });
          }
        });
    }, 400); // 400ms debounce to avoid excessive backend requests

    return () => clearTimeout(delayDebounceFn);
  }, [editedFields.material, step]);

  useEffect(() => {
    if (!fileObject) {
      setFileUrl("");
      return;
    }
    const url = URL.createObjectURL(fileObject);
    setFileUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [fileObject]);

  useEffect(() => {
    const supplier = editedFields.supplier_name;
    const material = editedFields.material;
    if (!supplier || !material || step !== "review") {
      setExistingSLA(null);
      return;
    }

    setCheckingSLA(true);
    setExistingSLA(null);

    const delayDebounceFn = setTimeout(() => {
      fetchActiveSLA(supplier, material)
        .then(res => {
          if (editedFields.supplier_name === supplier && editedFields.material === material) {
            if (res.exists) {
              setExistingSLA(res.sla);
            } else {
              setExistingSLA(null);
            }
            setCheckingSLA(false);
          }
        })
        .catch(() => {
          if (editedFields.supplier_name === supplier && editedFields.material === material) {
            setExistingSLA(null);
            setCheckingSLA(false);
          }
        });
    }, 400);

    return () => clearTimeout(delayDebounceFn);
  }, [editedFields.supplier_name, editedFields.material, step]);

  const handleFile = async (file) => {
    if (!file) return;
    setStep("extracting"); setError(""); setFormErrors({}); setExtraction(null); setConfirmed(null); setPipelineStep(0);
    setFileName(file.name);
    const size = file.size > 1024 * 1024 
      ? `${(file.size / (1024 * 1024)).toFixed(2)} MB` 
      : `${(file.size / 1024).toFixed(1)} KB`;
    setFileSize(size);
    setFileObject(file);

    // Animate pipeline steps while uploading
    const stepTimer = setInterval(() => {
      setPipelineStep(p => (p < 2 ? p + 1 : p));
    }, 700);

    try {
      const result = await uploadSLAPdf(file);
      clearInterval(stepTimer);
      setPipelineStep(3);
      setExtraction(result);
      const materialName = result.mapped_sla?.material || result.extracted_data?.material || "";
      
      const delayPenalty = result.mapped_sla?.delay_penalty_rate !== undefined && result.mapped_sla?.delay_penalty_rate !== null ? result.mapped_sla.delay_penalty_rate : result.extracted_data?.delay_penalty_rate;
      const missedItemPenalty = result.mapped_sla?.missed_item_penalty_rate !== undefined && result.mapped_sla?.missed_item_penalty_rate !== null ? result.mapped_sla.missed_item_penalty_rate : result.extracted_data?.missed_item_penalty_rate;
      const minQuality = result.mapped_sla?.min_quality_threshold !== undefined && result.mapped_sla?.min_quality_threshold !== null ? result.mapped_sla.min_quality_threshold : result.extracted_data?.minimum_quality_threshold;
      const qualityPenalty = result.mapped_sla?.quality_penalty_rate !== undefined && result.mapped_sla?.quality_penalty_rate !== null ? result.mapped_sla.quality_penalty_rate : result.extracted_data?.quality_penalty_rate;
      
      const quantityVal = result.mapped_sla?.quantity !== undefined && result.mapped_sla?.quantity !== null ? result.mapped_sla.quantity : result.extracted_data?.quantity;
      const unitCostVal = result.mapped_sla?.unit_cost !== undefined && result.mapped_sla?.unit_cost !== null ? result.mapped_sla.unit_cost : result.extracted_data?.unit_cost;

      setEditedFields({
        supplier_name:            result.mapped_sla?.supplier_name  || result.extracted_data?.supplier_name || "",
        material:                 materialName,
        lead_time_days:           result.mapped_sla?.lead_time_days || Math.ceil((result.extracted_data?.sla_lead_time_hours || 0) / 24) || "",
        penalty_clause:           result.mapped_sla?.penalty_clause || (delayPenalty > 0 ? `Delay penalty: $${delayPenalty}/day.` : "") || "",
        corrections:              "",
        quantity:                 quantityVal > 0 ? quantityVal : "",
        unit_cost:                unitCostVal > 0 ? unitCostVal : "",
        is_fallback:              false,
        delay_penalty_rate:       delayPenalty > 0 ? delayPenalty : "",
        missed_item_penalty_rate: missedItemPenalty > 0 ? missedItemPenalty : "",
        min_quality_threshold:    minQuality > 0 ? minQuality : "",
        quality_penalty_rate:     qualityPenalty > 0 ? qualityPenalty : "",
      });
      setStep("review");
    } catch (err) {
      clearInterval(stepTimer);
      setError(err.message || "Extraction failed.");
      setStep("error");
    }
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false);
    handleFile(e.dataTransfer?.files?.[0]);
  };

  const handleBrowse = (e) => handleFile(e.target?.files?.[0]);

  const handleConfirm = async () => {
    // Validate required fields
    const newErrors = {};
    if (!editedFields.supplier_name) newErrors.supplier_name = "Supplier Name is required";
    if (!editedFields.material) newErrors.material = "Material is required";
    if (!editedFields.lead_time_days) newErrors.lead_time_days = "Lead Time is required";
    if (!editedFields.penalty_clause) newErrors.penalty_clause = "Penalty Clause is required";
    if (!editedFields.quantity) newErrors.quantity = "Quantity is required";
    if (!editedFields.unit_cost) newErrors.unit_cost = "Unit Cost is required";

    if (Object.keys(newErrors).length > 0) {
      setFormErrors(newErrors);
      return;
    }
    setFormErrors({});
    
    setStep("confirming");
    try {
      const qty = parseInt(editedFields.quantity, 10) || 0;
      const cost = parseFloat(editedFields.unit_cost) || 0.0;
      const delayPen = parseFloat(editedFields.delay_penalty_rate);
      const missedPen = parseFloat(editedFields.missed_item_penalty_rate);
      const minQual = parseFloat(editedFields.min_quality_threshold);
      const qualPen = parseFloat(editedFields.quality_penalty_rate);

      const result = await confirmSLA({
        extraction_id:            extraction.extraction_id,
        supplier_name:            editedFields.supplier_name,
        material:                 editedFields.material,
        lead_time_days:           parseInt(editedFields.lead_time_days, 10) || 0,
        penalty_clause:           editedFields.penalty_clause,
        corrections:              editedFields.corrections || null,
        quantity:                 qty,
        unit_cost:                cost,
        impacted_process:         assemblyMatch?.matched ? assemblyMatch.process : null,
        is_fallback:              editedFields.is_fallback || false,
        delay_penalty_rate:       !isNaN(delayPen) ? delayPen : null,
        missed_item_penalty_rate: !isNaN(missedPen) ? missedPen : null,
        min_quality_threshold:    !isNaN(minQual) ? minQual : null,
        quality_penalty_rate:     !isNaN(qualPen) ? qualPen : null,
      });
      setConfirmed(result);
      setStep("done");
    } catch (err) {
      setError(err.message || "Failed to save to Knowledge Graph.");
      setStep("error");
    }
  };

  const reset = () => {
    setStep("idle"); setExtraction(null); setConfirmed(null);
    setError(""); setEditedFields({}); setPipelineStep(0); setAssemblyMatch(null);
    setFileName(""); setFileSize(""); setCopied(false);
    setFileObject(null);
    setExistingSLA(null);
    setCheckingSLA(false);
  };

  return (
    <div>
      <div style={S.pageHeader}>
        <div style={S.pageTitle}>SLA Upload · LLM Parser</div>
        <div style={S.pageDesc}>Upload a PDF contract — AI extracts entities · Review · Save to Knowledge Graph</div>
      </div>

      {/* Processing Pipeline - Horizontal Stepper at the top */}
      {step !== "idle" && step !== "error" && (
        <div style={{ ...S.card, marginBottom: 18 }}>
          <div style={{ ...S.cardTitle, marginBottom: 14 }}>⚙ Processing Pipeline</div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            {pipelineSteps.map((s, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 180,
                padding: "10px 14px", background: i <= pipelineStep ? C.surface2 : "transparent",
                border: `1px solid ${i <= pipelineStep ? C.borderHi : C.border}44`, borderRadius: 8
              }}>
                <div style={{
                  width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 700,
                  background: i < pipelineStep ? C.green : i === pipelineStep && step === "extracting" ? C.accent : i <= pipelineStep ? C.green : C.border,
                  color: i <= pipelineStep ? "#000" : C.muted,
                }}>
                  {i < pipelineStep || (i === pipelineStep && step !== "extracting" && step !== "idle" && step !== "error") ? "✓" : i === pipelineStep && step === "extracting" ? <span className="spin" style={{ fontSize: 9 }}>⚙</span> : i + 1}
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: i <= pipelineStep ? C.text : C.muted }}>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Step: review — show raw numbers and virtual twin comparison side-by-side above the form/doc grid */}
      {(step === "review" || step === "confirming") && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 18, marginBottom: 18 }}>
          {/* Raw values */}
          {extraction?.extracted_data && (
            <div style={S.card}>
              <div style={{ ...S.cardTitle, marginBottom: 14 }}>📋 Raw Extracted Values</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[
                  ["Lead Time", `${extraction.extracted_data.sla_lead_time_hours}h`],
                  ["Delay Penalty", `$${extraction.extracted_data.delay_penalty_rate}/day`],
                  ["Quality Threshold", `${(extraction.extracted_data.minimum_quality_threshold * 100).toFixed(0)}%`],
                  ["Quality Penalty", `${(extraction.extracted_data.quality_penalty_rate * 100).toFixed(0)}%`],
                  ["Quantity", `${extraction.extracted_data.quantity || 0}`],
                  ["Unit Cost", `$${extraction.extracted_data.unit_cost || 0.0}`],
                ].map(([k, v], i) => (
                  <div key={i} style={{ fontSize: 12, display: "flex", justifyContent: "space-between", borderBottom: `1px solid ${C.border}22`, paddingBottom: 6 }}>
                    <span style={{ color: C.muted }}>{k}</span>
                    <span style={{ color: C.accent, fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Virtual Twin comparison */}
          <div style={S.card}>
            {existingSLA ? (
              <div>
                <div style={{ fontSize: 13, color: C.blue, fontWeight: 700, marginBottom: 8, letterSpacing: "0.04em", display: "flex", alignItems: "center", gap: 5 }}>
                  🌐 VIRTUAL TWIN MATCH FOUND
                </div>
                <div style={{ fontSize: 12, color: C.muted, marginBottom: 12 }}>
                  Comparing proposed contract against active SLA in the Knowledge Graph:
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      <th style={{ textAlign: "left", paddingBottom: 6, color: C.muted }}>Metric</th>
                      <th style={{ textAlign: "right", paddingBottom: 6, color: C.accent }}>Proposed</th>
                      <th style={{ textAlign: "right", paddingBottom: 6, color: C.text }}>Active Twin</th>
                      <th style={{ textAlign: "right", paddingBottom: 6, color: C.muted }}>Diff</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["Lead Time", `${editedFields.lead_time_days || "—"}d`, `${existingSLA.lead_time_days || "—"}d`, 
                       (editedFields.lead_time_days && existingSLA.lead_time_days) ? (parseInt(editedFields.lead_time_days) - existingSLA.lead_time_days) : null, "d"],
                      ["Quantity", editedFields.quantity || "—", existingSLA.quantity || "—", 
                       (editedFields.quantity && existingSLA.quantity) ? (parseInt(editedFields.quantity) - existingSLA.quantity) : null, ""],
                      ["Unit Cost", `$${editedFields.unit_cost || "—"}`, `$${existingSLA.unit_cost || "—"}`, 
                       (editedFields.unit_cost && existingSLA.unit_cost) ? (parseFloat(editedFields.unit_cost) - existingSLA.unit_cost) : null, "$", true],
                      ["Delay Penalty", `$${editedFields.delay_penalty_rate || "—"}/d`, `$${existingSLA.delay_penalty_rate || "—"}/d`, 
                       (editedFields.delay_penalty_rate && existingSLA.delay_penalty_rate) ? (parseFloat(editedFields.delay_penalty_rate) - existingSLA.delay_penalty_rate) : null, "$"],
                      ["Missed Item Penalty", `$${editedFields.missed_item_penalty_rate || "—"}/unit`, `$${existingSLA.missed_item_penalty_rate || "—"}/unit`, 
                       (editedFields.missed_item_penalty_rate && existingSLA.missed_item_penalty_rate) ? (parseFloat(editedFields.missed_item_penalty_rate) - existingSLA.missed_item_penalty_rate) : null, "$"],
                      ["Min Quality Threshold", 
                       editedFields.min_quality_threshold !== undefined && editedFields.min_quality_threshold !== "" ? `${(parseFloat(editedFields.min_quality_threshold) * 100).toFixed(0)}%` : "—", 
                       existingSLA.min_quality_threshold !== null && existingSLA.min_quality_threshold !== undefined ? `${(existingSLA.min_quality_threshold * 100).toFixed(0)}%` : "—", 
                       (editedFields.min_quality_threshold && existingSLA.min_quality_threshold) ? (parseFloat(editedFields.min_quality_threshold) - existingSLA.min_quality_threshold) : null, "%", false, true],
                      ["Quality Penalty Rate", 
                       editedFields.quality_penalty_rate !== undefined && editedFields.quality_penalty_rate !== "" ? `${(parseFloat(editedFields.quality_penalty_rate) * 100).toFixed(0)}%` : "—", 
                       existingSLA.quality_penalty_rate !== null && existingSLA.quality_penalty_rate !== undefined ? `${(existingSLA.quality_penalty_rate * 100).toFixed(0)}%` : "—", 
                       (editedFields.quality_penalty_rate && existingSLA.quality_penalty_rate) ? (parseFloat(editedFields.quality_penalty_rate) - existingSLA.quality_penalty_rate) : null, "%", false, true],
                    ].map(([label, propVal, twinVal, diff, unit, isCurrency, isPercent], idx) => {
                      const hasDiff = diff !== null && diff !== 0;
                      const diffColor = diff > 0 ? C.red : diff < 0 ? C.green : C.muted;
                      const diffSign = diff > 0 ? "+" : "";
                      let diffText = "—";
                      if (hasDiff) {
                        if (isCurrency) {
                          diffText = `${diffSign}$${diff.toFixed(2)}`;
                        } else if (isPercent) {
                          diffText = `${diffSign}${(diff * 100).toFixed(0)}%`;
                        } else {
                          diffText = `${diffSign}${diff.toFixed(0)}${unit}`;
                        }
                      } else if (diff === 0) {
                        diffText = "No change";
                      }
                      return (
                        <tr key={idx} style={{ borderBottom: `1px solid ${C.border}22` }}>
                          <td style={{ padding: "5px 0", color: C.textSoft, fontWeight: 500 }}>{label}</td>
                          <td style={{ padding: "5px 0", textAlign: "right", color: C.accent, fontWeight: 600 }}>{propVal}</td>
                          <td style={{ padding: "5px 0", textAlign: "right", color: C.textSoft }}>{twinVal}</td>
                          <td style={{ padding: "5px 0", textAlign: "right", color: diffColor, fontWeight: 600 }}>
                            {diffText}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : checkingSLA ? (
              <div style={{ padding: "10px 14px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 12, color: C.muted }}>
                ⏳ Checking active Digital Twin state for {editedFields.supplier_name || "supplier"}...
              </div>
            ) : (
              (editedFields.supplier_name && editedFields.material) ? (
                <div style={{ padding: "10px 14px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 12, color: C.muted }}>
                  🌐 Virtual Twin: No active contract found for this Supplier/Material pair. (Will be saved as new node).
                </div>
              ) : (
                <div style={{ padding: "10px 14px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 12, color: C.muted }}>
                  🌐 Enter Supplier & Material to compare against active Digital Twin state.
                </div>
              )
            )}
          </div>
        </div>
      )}

      <div style={S.grid2}>
        {/* Left: Upload flow */}
        <div>
          {/* Step: idle or error — show drop zone */}
          {(step === "idle" || step === "error") && (
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              style={{
                ...S.card, textAlign: "center", padding: 48,
                borderStyle: "dashed", borderWidth: 2,
                borderColor: dragging ? C.accent : C.border,
                background: dragging ? "rgba(245,158,11,0.05)" : C.surface,
                cursor: "pointer", transition: "all 0.2s", marginBottom: 16,
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 14 }}>📄</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>Drop SLA Contract Here</div>
              <div style={{ fontSize: 13, color: C.muted, marginBottom: 20 }}>PDF · TXT · DOC · DOCX · Max 50MB</div>
              <label style={{ ...S.btn(), cursor: "pointer", display: "inline-block" }}>
                Browse Files
                <input type="file" accept=".pdf,.txt,.doc,.docx,application/pdf,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" style={{ display: "none" }} onChange={handleBrowse} />
              </label>

              {step === "error" && (
                <div style={{ marginTop: 16, padding: "10px 14px", background: C.red + "18", border: `1px solid ${C.red}44`, borderRadius: 8, fontSize: 13, color: C.red }}>
                  ⚠ {error}
                </div>
              )}
            </div>
          )}

          {/* Step: review — show editable extracted fields */}
          {(step === "review" || step === "confirming") && (
            <div style={{ ...S.card, borderLeft: `3px solid ${C.blue}` }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: C.text, marginBottom: 4 }}>👤 Review Extracted Data</div>
              <div style={{ fontSize: 13, color: C.muted, marginBottom: 16 }}>
                Review and correct before saving to Knowledge Graph
              </div>

              <Field label="Supplier Name"   field="supplier_name"  editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.supplier_name} />
              <Field label="Material"         field="material"       editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.material} />
              <Field label="Lead Time (Days)" field="lead_time_days" type="number" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.lead_time_days} />
              <Field label="Penalty Clause"   field="penalty_clause" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.penalty_clause} />

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Quantity"         field="quantity"       type="number" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.quantity} />
                <Field label="Unit Cost ($)"    field="unit_cost"      type="number" step="any" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.unit_cost} />
              </div>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Delay Penalty ($/day)" field="delay_penalty_rate" type="number" step="any" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.delay_penalty_rate} />
                <Field label="Missed Item Penalty ($/unit)" field="missed_item_penalty_rate" type="number" step="any" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.missed_item_penalty_rate} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Min Quality Threshold (0.0-1.0)" field="min_quality_threshold" type="number" step="0.01" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.min_quality_threshold} />
                <Field label="Quality Penalty Rate (0.0-1.0)" field="quality_penalty_rate" type="number" step="0.01" editedFields={editedFields} setEditedFields={setEditedFields} error={formErrors.quality_penalty_rate} />
              </div>
              
              {/* Register as Fallback option */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, marginTop: 4 }}>
                <input
                  type="checkbox"
                  id="is_fallback"
                  checked={editedFields.is_fallback || false}
                  onChange={e => setEditedFields(p => ({ ...p, is_fallback: e.target.checked }))}
                  style={{ width: 17, height: 17, cursor: "pointer", accentColor: C.accent }}
                />
                <label htmlFor="is_fallback" style={{ fontSize: 13, fontWeight: 600, color: C.text, cursor: "pointer", userSelect: "none" }}>
                  Register as Alternative/Backup Supplier
                </label>
              </div>
              
              {/* Assembly Line: auto-matched or new-material notice */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, color: C.muted, display: "block", marginBottom: 5, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  Assembly Line
                </label>
                {assemblyMatch === null && (
                  <div style={{ fontSize: 12, color: C.muted, padding: "8px 12px", background: C.bg, borderRadius: 6, border: `1px solid ${C.border}` }}>
                    ⏳ Checking knowledge graph...
                  </div>
                )}
                {assemblyMatch?.matched && (
                  <div style={{ fontSize: 13, color: C.green, padding: "10px 14px", background: C.green + "15", borderRadius: 8, border: `1px solid ${C.green}44`, fontWeight: 600 }}>
                    ✅ Auto-matched: <span style={{ color: C.text }}>{assemblyMatch.process.replace(/_/g, " ")}</span>
                    <div style={{ fontSize: 11, color: C.muted, fontWeight: 400, marginTop: 2 }}>This material is already linked to an assembly line in the system.</div>
                  </div>
                )}
                {assemblyMatch !== null && !assemblyMatch.matched && (
                  <div style={{ fontSize: 13, color: C.orange, padding: "10px 14px", background: C.orange + "15", borderRadius: 8, border: `1px solid ${C.orange}44`, fontWeight: 600 }}>
                    ⚠ New material detected
                    <div style={{ fontSize: 11, color: C.muted, fontWeight: 400, marginTop: 2 }}>An alert will be sent to the Production Manager to manually assign this material to an assembly line.</div>
                  </div>
                )}
              </div>


              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, color: C.muted, display: "block", marginBottom: 5, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  Corrections / Notes (Optional)
                </label>
                <textarea
                  value={editedFields.corrections || ""}
                  onChange={e => setEditedFields(p => ({ ...p, corrections: e.target.value }))}
                  placeholder="Note any corrections made..."
                  style={{ ...S.input, height: 70, resize: "vertical" }}
                />
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button style={{ ...S.btn("ghost"), flex: 1 }} onClick={reset}>← Start Over</button>
                <button
                  style={{ ...S.btn(), flex: 2, opacity: step === "confirming" ? 0.7 : 1 }}
                  disabled={step === "confirming"}
                  onClick={handleConfirm}
                >
                  {step === "confirming"
                    ? <><span className="spin">⚙</span> Saving to Knowledge Graph...</>
                    : "✓ Confirm & Save"}
                </button>
              </div>
            </div>
          )}

          {/* Step: done */}
          {step === "done" && confirmed && (
            <div style={{ ...S.card, borderLeft: `3px solid ${C.green}` }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: C.green, marginBottom: 14 }}>✅ Saved to Knowledge Graph</div>
              {[
                ["Extraction ID", confirmed.extraction_id],
                ["Supplier",      confirmed.supplier],
                ["Material",      confirmed.material],
                ["Triples Added", confirmed.triples_inserted?.toString() || "—"],
                ["Repository",    confirmed.graph || "supply-chain"],
              ].map(([k, v], i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: `1px solid ${C.border}22`, fontSize: 13 }}>
                  <span style={{ color: C.muted }}>{k}</span>
                  <span style={{ color: C.text, fontWeight: 600 }}>{v}</span>
                </div>
              ))}
              <button style={{ ...S.btn(), width: "100%", marginTop: 16 }} onClick={reset}>Upload Another Contract</button>
            </div>
          )}
        </div>

        {/* Right Panel: How it works or Document Viewer */}
        {step === "idle" || step === "error" ? (
          <div style={S.card}>
            <div style={{ ...S.cardTitle, marginBottom: 16 }}>ℹ How It Works</div>
            {[
              { step: "1", title: "Upload PDF, TXT, or DOC", desc: "Drop your SLA contract file. The LLM reads the document and extracts key terms automatically." },
              { step: "2", title: "Review Extraction", desc: "Check the extracted supplier name, material, lead time, and penalty clause. Correct any errors." },
              { step: "3", title: "Confirm & Save", desc: "Once confirmed, the data is converted to RDF triples and stored in the Knowledge Graph for reasoning." },
            ].map((item, i) => (
              <div key={i} style={{ display: "flex", gap: 14, marginBottom: 20 }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: C.accent + "22", border: `2px solid ${C.accent}44`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, color: C.accent, flexShrink: 0 }}>
                  {item.step}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 4 }}>{item.title}</div>
                  <div style={{ fontSize: 13, color: C.muted, lineHeight: 1.5 }}>{item.desc}</div>
                </div>
              </div>
            ))}

            <div style={{ padding: "12px 14px", background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, marginTop: 8 }}>
              <div style={{ fontSize: 12, color: C.muted, marginBottom: 4, fontWeight: 600 }}>SUPPORTED FORMATS</div>
              <div style={{ fontSize: 13, color: C.text }}>PDF · TXT · DOC · DOCX · English language contracts only</div>
            </div>
          </div>
        ) : step === "extracting" ? (
          <div style={{ ...S.card, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 400, textAlign: "center" }}>
            <div className="spin" style={{ fontSize: 32, marginBottom: 16, color: C.accent }}>⚙</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 8 }}>Reading Document</div>
            <div style={{ fontSize: 14, color: C.muted, maxWidth: 300, marginBottom: 6 }}>
              Extracting raw text from <span style={{ color: C.text, fontWeight: 600 }}>{fileName}</span> ({fileSize})
            </div>
            <div style={{ fontSize: 12, color: C.muted + "AA" }}>
              Please wait while the AI processes the document structure...
            </div>
          </div>
        ) : (
          <div style={S.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, borderBottom: `1px solid ${C.border}`, paddingBottom: 12 }}>
              <div>
                <div style={{ ...S.cardTitle, marginBottom: 4 }}>📄 Original SLA Document</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text, display: "flex", alignItems: "center", gap: 10 }}>
                  {fileName}
                  {!fileName.toLowerCase().endsWith(".pdf") && fileUrl && (
                    <a
                      href={fileUrl}
                      download={fileName}
                      title="Download original file to view formatting in Word"
                      style={{
                        background: C.surface,
                        border: `1px solid ${C.border}`,
                        borderRadius: 4,
                        color: C.accent,
                        fontSize: 11,
                        padding: "2px 8px",
                        cursor: "pointer",
                        textDecoration: "none",
                        fontWeight: 600,
                        transition: "all 0.15s",
                      }}
                      onMouseEnter={e => { e.target.style.borderColor = C.accent; }}
                      onMouseLeave={e => { e.target.style.borderColor = C.border; }}
                    >
                      📥 Download Original
                    </a>
                  )}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span style={{ ...S.badge(C.accent), fontSize: 11 }}>{fileSize}</span>
              </div>
            </div>

            {fileName.toLowerCase().endsWith(".pdf") && fileUrl ? (
              <div style={{ position: "relative", background: "#ffffff", borderRadius: 8, border: `1px solid ${C.border}`, padding: 4 }}>
                <iframe
                  src={fileUrl}
                  title="SLA Document Viewer"
                  style={{
                    width: "100%",
                    height: "550px",
                    border: "none",
                    borderRadius: 4,
                    background: "#ffffff",
                  }}
                />
              </div>
            ) : (
              <div style={{ position: "relative" }}>
                <div
                  style={{
                    margin: 0,
                    padding: "24px 32px",
                    background: "#ffffff",
                    border: "1px solid #e5e7eb",
                    borderRadius: 8,
                    maxHeight: 520,
                    overflowY: "auto",
                    color: "#1f2937",
                    fontFamily: "Georgia, Cambria, 'Times New Roman', Times, serif",
                    fontSize: "14px",
                    lineHeight: "1.7",
                    boxShadow: "0 4px 6px -1px rgba(0,0,0,0.05), inset 0 2px 4px rgba(0,0,0,0.03)",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {extraction?.raw_text || "No text extracted from document."}
                </div>

                {extraction?.raw_text && (
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(extraction.raw_text);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }}
                    style={{
                      position: "absolute",
                      top: 10,
                      right: 10,
                      background: copied ? C.green + "22" : "rgba(255,255,255,0.9)",
                      border: `1px solid ${copied ? C.green : "#cbd5e1"}`,
                      borderRadius: 4,
                      color: copied ? C.green : "#4b5563",
                      fontSize: 11,
                      padding: "4px 8px",
                      cursor: "pointer",
                      boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                      transition: "all 0.15s",
                    }}
                  >
                    {copied ? "✓ Copied" : "📋 Copy"}
                  </button>
                )}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14, fontSize: 12, color: C.muted }}>
              <div>
                Character count: <span style={{ color: C.text, fontWeight: 600 }}>{extraction?.raw_text?.length || 0}</span>
              </div>
              <div>
                Word count: <span style={{ color: C.text, fontWeight: 600 }}>{extraction?.raw_text ? extraction.raw_text.split(/\s+/).filter(Boolean).length : 0}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

import { useState, useRef, useEffect } from "react";
import { C, S } from "../styles/theme";
import { sendChatMessage, checkBackendHealth } from "../services/api";

const INITIAL_MESSAGE = {
  role: "assistant",
  text: "Hello! I'm your Supply Chain AI Assistant, connected to the Knowledge Graph via SPARQL.\n\nYou can ask me things like:\n• What deliveries are currently delayed?\n• Which suppliers have SLA violations?\n• What production lines are impacted?\n• Show fallback suppliers for a material",
};

const SUGGESTIONS = [
  "What deliveries are currently delayed?",
  "Which suppliers have SLA violations?",
  "What production lines are impacted by delays?",
  "Show me fallback suppliers for at-risk materials",
  "What is the total penalty owed for current breaches?",
];

export default function ChatAssistant({ user, initialPrompt, clearInitialPrompt }) {
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    checkBackendHealth().then(h => setBackendOnline(h.online));
  }, []);

  useEffect(() => {
    if (initialPrompt) {
      setInput(initialPrompt);
      clearInitialPrompt();
    }
  }, [initialPrompt, clearInitialPrompt]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    if (!text.trim() || loading) return;
    setMessages(p => [...p, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const reply = await sendChatMessage(text);
      setMessages(p => [...p, { role: "assistant", text: reply.answer, sparql: reply.sparql }]);
    } catch (err) {
      setMessages(p => [...p, {
        role: "assistant",
        text: `⚠ Error: ${err.message}\n\nPlease check the backend is running at http://localhost:8001`,
      }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 118px)" }}>
      <div style={{ ...S.pageHeader, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={S.pageTitle}>AI Supply Chain Assistant</div>
          <div style={S.pageDesc}>Powered by DeepSeek LLM · SPARQL Knowledge Graph · OWL Reasoning</div>
        </div>

        {/* Backend status */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 14px", borderRadius: 8,
          background: backendOnline === null ? C.border : backendOnline ? C.green + "18" : C.red + "18",
          border: `1px solid ${backendOnline === null ? C.border : backendOnline ? C.green + "44" : C.red + "44"}`,
        }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: backendOnline === null ? C.muted : backendOnline ? C.green : C.red,
            boxShadow: backendOnline ? `0 0 6px ${C.green}` : "none",
          }} className={backendOnline ? "live-pulse" : ""} />
          <span style={{ fontSize: 12, fontWeight: 600, color: backendOnline === null ? C.muted : backendOnline ? C.green : C.red }}>
            {backendOnline === null ? "Connecting..." : backendOnline ? "AI Connected" : "Backend Offline"}
          </span>
        </div>
      </div>

      {/* Offline warning */}
      {backendOnline === false && (
        <div style={{ marginBottom: 16, padding: "12px 16px", background: C.red + "15", border: `1px solid ${C.red}33`, borderRadius: 8, fontSize: 13, color: C.red }}>
          ⚠ Backend is offline. Start the backend at <strong>http://localhost:8001</strong> to use the AI assistant.
        </div>
      )}

      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0 }}>
        {/* Chat window */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", ...S.card }}>
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, paddingBottom: 8 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{ fontSize: 11, color: C.muted, marginBottom: 5, fontWeight: 600 }}>
                  {m.role === "user" ? (user?.name?.toUpperCase() || "YOU") : "🤖 AI ASSISTANT"}
                </div>
                <div style={S.chatBubble(m.role)}>
                  {m.text.split("\n").map((line, j) => (
                    <div key={j}>{line || "\u00a0"}</div>
                  ))}
                  {m.sparql && (
                    <div style={{ marginTop: 12 }}>
                      <button
                        style={{ ...S.btn("ghost"), fontSize: 11, padding: "4px 8px", background: "rgba(255,255,255,0.1)", color: C.accent }}
                        onClick={() => {
                          setMessages(p => p.map((msg, idx) => idx === i ? { ...msg, showSparql: !msg.showSparql } : msg));
                        }}
                      >
                        {m.showSparql ? "Hide SPARQL" : "View SPARQL"}
                      </button>
                      {m.showSparql && (
                        <pre style={{ marginTop: 8, padding: 12, background: "rgba(0,0,0,0.3)", borderRadius: 6, fontSize: 11, color: "#a8c7fa", overflowX: "auto", whiteSpace: "pre-wrap" }}>
                          {m.sparql}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div style={{ alignSelf: "flex-start" }}>
                <div style={{ fontSize: 11, color: C.muted, marginBottom: 5, fontWeight: 600 }}>🤖 AI ASSISTANT</div>
                <div style={{ ...S.chatBubble("assistant"), color: C.accent, display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="spin">⚙</span> Querying Knowledge Graph via SPARQL...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ marginTop: 12, display: "flex", gap: 8, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
            <input
              style={S.input}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && send(input)}
              placeholder="Ask about suppliers, SLA violations, delivery delays..."
              disabled={backendOnline === false}
            />
            <button
              style={{ ...S.btn(), minWidth: 72, opacity: (loading || backendOnline === false) ? 0.5 : 1 }}
              className="btn-hover"
              onClick={() => send(input)}
              disabled={loading || backendOnline === false}
            >
              {loading ? <span className="spin">⚙</span> : "Send"}
            </button>
          </div>
        </div>

        {/* Suggestions panel */}
        <div style={{ width: 230 }}>
          <div style={S.card}>
            <div style={{ ...S.cardTitle, marginBottom: 14 }}>💡 Try Asking</div>
            {SUGGESTIONS.map((s, i) => (
              <div key={i} className="suggestion-item"
                onClick={() => send(s)}
                style={{
                  fontSize: 13, padding: "10px 12px", marginBottom: 8,
                  background: C.bg, border: `1px solid ${C.border}`,
                  borderRadius: 8, cursor: "pointer", color: C.muted,
                  lineHeight: 1.4, transition: "all 0.15s",
                  opacity: backendOnline === false ? 0.4 : 1,
                  pointerEvents: backendOnline === false ? "none" : "auto",
                }}>
                {s}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

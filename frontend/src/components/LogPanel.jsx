import { useEffect, useRef } from "react";
import "./LogPanel.css";

function formatData(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.text)    return data.text;
  if (data.message) return data.message;
  if (data.result)  return String(data.result).slice(0, 300);
  if (data.tool)    return `${data.tool}(${JSON.stringify(data.path ?? data.command ?? data.query ?? data.url ?? {}).slice(0, 80)})`;
  return JSON.stringify(data).slice(0, 200);
}

const TYPE_LABELS = {
  message:     "MSG",
  checkpoint:  "CHK",
  tool_call:   "TOOL",
  tool_result: "RES",
  start:       "START",
  response:    "RESP",
};

const AGENT_SHORT = {
  sonnet:   "Sonnet",
  nemotron: "Nemo",
  qwen:     "Qwen",
  gemini:   "Gemini",
  system:   "Sys",
};

export default function LogPanel({ logs }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <div className="log-panel" ref={containerRef}>
      {logs.length === 0 && (
        <p className="empty">Submit a task to see agent communication logs…</p>
      )}
      {logs.map((entry, i) => {
        if (entry.type === "usage") {
          const d = entry.data;
          const cost = (d.estimated_cost_usd ?? 0).toFixed(4);
          return (
            <div key={i} className="log-usage" style={{ "--agent-color": entry.color }}>
              <span className="usage-badge" style={{ color: entry.color }}>
                {AGENT_SHORT[entry.agent] ?? entry.agent}
              </span>
              <span className="usage-stats">
                ↓ {d.input_tokens?.toLocaleString() ?? 0} in
                · ↑ {d.output_tokens?.toLocaleString() ?? 0} out
                · ${cost}
              </span>
            </div>
          );
        }

        return (
          <div key={i} className="log-entry" style={{ "--agent-color": entry.color }}>
            <span className="log-ts">{entry.ts}</span>
            <span className="log-badge" style={{ color: entry.color }}>
              {AGENT_SHORT[entry.agent] ?? entry.agent}
            </span>
            <span className="log-type">{TYPE_LABELS[entry.type] ?? entry.type}</span>
            <span className="log-text">{formatData(entry.data)}</span>
          </div>
        );
      })}
    </div>
  );
}

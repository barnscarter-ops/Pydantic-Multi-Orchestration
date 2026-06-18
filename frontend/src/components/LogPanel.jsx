import { useEffect, useRef } from "react";
import "./LogPanel.css";

function formatData(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.text) return data.text;
  if (data.message) return data.message;
  if (data.tool) return `${data.tool}(${JSON.stringify(data.input || {}).slice(0, 80)})`;
  return JSON.stringify(data).slice(0, 120);
}

const TYPE_LABELS = {
  message: "MSG",
  checkpoint: "CHK",
  tool_call: "TOOL",
  tool_result: "RES",
  start: "START",
  response: "RESP",
};

export default function LogPanel({ logs }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="log-panel">
      {logs.length === 0 && (
        <p className="empty">Submit a task to see agent communication logs…</p>
      )}
      {logs.map((entry, i) => (
        <div key={i} className="log-entry" style={{ "--agent-color": entry.color }}>
          <span className="log-ts">{entry.ts}</span>
          <span className="log-badge" style={{ color: entry.color }}>
            {entry.agent.replace("Agent", "")}
          </span>
          <span className="log-type">{TYPE_LABELS[entry.type] || entry.type}</span>
          <span className="log-text">{formatData(entry.data)}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

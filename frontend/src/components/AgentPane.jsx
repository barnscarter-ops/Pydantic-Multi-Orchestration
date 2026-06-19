import { useEffect, useRef } from "react";
import "./AgentPane.css";

function formatData(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.text)    return data.text;
  if (data.message) return data.message;
  if (data.result)  return String(data.result).slice(0, 400);
  if (data.tool)    return `${data.tool}(${JSON.stringify(data.path ?? data.command ?? data.query ?? data.url ?? {}).slice(0, 100)})`;
  return JSON.stringify(data).slice(0, 300);
}

const TYPE_LABELS = {
  message:     "msg",
  checkpoint:  "chk",
  tool_call:   "tool",
  tool_result: "res",
  start:       "start",
  response:    "resp",
};

const AGENT_META = {
  sonnet:   { role: "Planner",  model: "claude-sonnet-4-6",  color: "var(--sonnet)"   },
  nemotron: { role: "Reviewer", model: "Nemotron 550B · NIM", color: "var(--nemotron)" },
  qwen:     { role: "Executor", model: "Qwen3-14B · local",   color: "var(--qwen)"     },
  gemini:   { role: "Designer", model: "Gemini 2.5 Pro",       color: "var(--gemini)"   },
};

function fmt(n) {
  if (n === undefined || n === null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function AgentPane({ name, state, logs, maxIn }) {
  const meta      = AGENT_META[name] || { role: name, model: name, color: "var(--accent)" };
  const agentLogs = logs.filter((l) => l.agent === name);
  const barPct    = state.usage ? Math.min((state.usage.input_tokens / maxIn) * 100, 100) : 0;
  const scrollRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [agentLogs.length]);

  return (
    <div className={`agent-pane ${state.status}`} style={{ "--agent-color": meta.color }}>

      <div className="pane-header">
        <div className="pane-title">
          <span className="pane-role">{meta.role}</span>
          <span className="pane-model">{meta.model}</span>
        </div>
        <div className="pane-meta">
          {state.usage && (
            <span className="pane-cost">${(state.usage.estimated_cost_usd ?? 0).toFixed(4)}</span>
          )}
          <span className={`pane-badge ${state.status}`}>{state.status}</span>
        </div>
      </div>

      <div className="pane-log" ref={scrollRef}>
        {agentLogs.length === 0 ? (
          <p className="pane-empty">waiting for {meta.role.toLowerCase()}…</p>
        ) : (
          agentLogs.map((entry, i) => (
            <div key={i} className="pane-entry">
              <span className="pane-ts">{entry.ts}</span>
              <span className="pane-type">{TYPE_LABELS[entry.type] ?? entry.type}</span>
              <span className="pane-text">{formatData(entry.data)}</span>
            </div>
          ))
        )}
      </div>

      <div className="pane-footer">
        <div className="pane-meter">
          <div className="pane-meter-fill" style={{ width: `${barPct}%` }} />
        </div>
        {state.usage && (
          <div className="pane-stats">
            <span>{fmt(state.usage.input_tokens)} in</span>
            <span>{fmt(state.usage.output_tokens)} out</span>
          </div>
        )}
      </div>

    </div>
  );
}

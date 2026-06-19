import { useState, useEffect, useRef } from "react";
import "./LogPanel.css";

const AGENT_LABELS = {
  sonnet:   "Sonnet",
  nemotron: "Nemotron",
  qwen:     "Qwen",
  gemini:   "Gemini",
  system:   "System",
};

const PHASE_LABELS = {
  debate:    "Debate",
  breakdown: "Breakdown",
  execution: "Execution",
  review:    "Review",
  design:    "Design",
};

// ── Message block — agent prose/reasoning ─────────────────────────────────
function MessageBlock({ entry }) {
  const { data, agent, color, ts } = entry;
  const [collapsed, setCollapsed] = useState(true);

  const isQwen = agent === "qwen";
  const text = data?.text ?? data?.message ?? (typeof data === "string" ? data : "");
  const chunkLabel = data?.chunk != null ? `Chunk ${data.chunk}` : null;
  const roundLabel = data?.round  != null ? `Round ${data.round}` : null;

  const COLLAPSE_AT = 1200;
  const isLong = text.length > COLLAPSE_AT;
  const display = isLong && collapsed ? text.slice(0, COLLAPSE_AT) : text;

  if (isQwen && !text) return null;

  return (
    <div className={`log-msg ${isQwen ? "log-msg--qwen" : ""}`} style={{ "--agent-color": color }}>
      <div className="log-msg-header">
        <span className="log-msg-agent" style={{ color }}>
          {AGENT_LABELS[agent] ?? agent}
        </span>
        {roundLabel && <span className="log-msg-meta">{roundLabel}</span>}
        {chunkLabel && <span className="log-msg-meta">{chunkLabel}</span>}
        <span className="log-msg-ts">{ts}</span>
      </div>
      <div className="log-msg-body">
        {display}
        {isLong && collapsed && <span className="log-msg-fade" />}
      </div>
      {isLong && (
        <button className="log-expand-btn" onClick={() => setCollapsed(c => !c)}>
          {collapsed ? `Show ${text.length - COLLAPSE_AT} more chars ↓` : "Collapse ↑"}
        </button>
      )}
    </div>
  );
}

// ── Checkpoint — phase divider ────────────────────────────────────────────
function CheckpointBlock({ entry }) {
  const { data } = entry;
  const step    = data?.step ?? "";
  const message = data?.message ?? "";
  const label   = PHASE_LABELS[step] ?? step.toUpperCase();

  return (
    <div className="log-checkpoint">
      <div className="log-checkpoint-rule" />
      <span className="log-checkpoint-label">{label}</span>
      <div className="log-checkpoint-rule" />
      {message && <span className="log-checkpoint-msg">{message}</span>}
    </div>
  );
}

// ── Tool call — compact single line ───────────────────────────────────────
function ToolCallBlock({ entry }) {
  const { data, color, ts } = entry;
  const tool = data?.tool ?? "call";
  const arg  = data?.path ?? data?.command ?? data?.query ?? data?.url ?? data?.operation ?? "";

  return (
    <div className="log-tool-row log-tool-row--call" style={{ "--agent-color": color }}>
      <span className="log-tool-icon">↗</span>
      <span className="log-tool-name">{tool}</span>
      {arg && (
        <span className="log-tool-arg" title={String(arg)}>
          {String(arg).slice(0, 100)}
        </span>
      )}
      <span className="log-ts-aside">{ts}</span>
    </div>
  );
}

// ── Tool result — inline, expandable if long ──────────────────────────────
function ToolResultBlock({ entry }) {
  const { data, color } = entry;
  const [expanded, setExpanded] = useState(false);

  const raw    = data?.result ?? data?.chars ?? data?.message ?? "";
  const text   = String(raw);
  const isLong = text.length > 240;
  const display = expanded ? text : text.slice(0, 240);

  return (
    <div className="log-tool-row log-tool-row--result" style={{ "--agent-color": color }}>
      <span className="log-tool-icon log-tool-icon--ok">✓</span>
      <span className="log-tool-result-text">
        {display}
        {isLong && !expanded && "…"}
      </span>
      {isLong && (
        <button className="log-inline-expand" onClick={() => setExpanded(e => !e)}>
          {expanded ? "less" : `+${text.length - 240}`}
        </button>
      )}
    </div>
  );
}

// ── Token usage — compact stats row ───────────────────────────────────────
function UsageBlock({ entry }) {
  const { data, agent, color } = entry;
  const cost = (data?.estimated_cost_usd ?? 0).toFixed(4);
  return (
    <div className="log-usage" style={{ "--agent-color": color }}>
      <span className="usage-badge" style={{ color }}>{AGENT_LABELS[agent] ?? agent}</span>
      <span className="usage-stats">
        ↓ {(data?.input_tokens ?? 0).toLocaleString()} in
        · ↑ {(data?.output_tokens ?? 0).toLocaleString()} out
        · ${cost}
      </span>
    </div>
  );
}

// ── User injection — comment sent mid-run ─────────────────────────────────
function UserInjectBlock({ entry }) {
  const { data, ts } = entry;
  const text = data?.comment ?? data?.text ?? "";
  return (
    <div className="log-inject">
      <span className="log-inject-you">you</span>
      <span className="log-inject-text">{text}</span>
      <span className="log-ts-aside">{ts}</span>
    </div>
  );
}

// ── Streaming block — live text as it generates ───────────────────────────
function StreamBlock({ entry }) {
  const { data, agent, color, ts } = entry;
  const text = data?.text ?? "";
  return (
    <div className="log-msg log-msg--stream" style={{ "--agent-color": color }}>
      <div className="log-msg-header">
        <span className="log-msg-agent" style={{ color }}>{AGENT_LABELS[agent] ?? agent}</span>
        <span className="log-msg-ts">{ts}</span>
      </div>
      <div className="log-msg-body">
        {text}<span className="log-stream-cursor" />
      </div>
    </div>
  );
}

// ── Thinking indicator — shown while waiting for an agent response ─────────
function ThinkingBlock({ entry }) {
  const { agent, color, ts, resolved } = entry;
  return (
    <div className={`log-thinking${resolved ? " log-thinking--done" : ""}`} style={{ "--agent-color": color }}>
      <span className="log-thinking-dots">
        <span /><span /><span />
      </span>
      <span className="log-thinking-agent" style={{ color }}>
        {AGENT_LABELS[agent] ?? agent}
      </span>
      <span className="log-thinking-label">{resolved ? "done" : "thinking"}</span>
      <span className="log-ts-aside">{ts}</span>
    </div>
  );
}

// ── Debrief — post-pipeline Sonnet summary shown as a chat bubble ─────────
function DebriefBlock({ entry }) {
  const { data, color, ts } = entry;
  const text = data?.text ?? "";
  return (
    <div className="log-debrief" style={{ "--agent-color": color }}>
      <div className="log-debrief-header">
        <span className="log-debrief-label" style={{ color }}>Sonnet</span>
        <span className="log-debrief-tag">summary</span>
        <span className="log-msg-ts">{ts}</span>
      </div>
      <div className="log-debrief-body">{text}</div>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────
export default function LogPanel({ logs }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <div className="log-panel" ref={containerRef}>
      {logs.length === 0 && (
        <p className="empty">Submit a task to watch the agents think…</p>
      )}
      {logs.map((entry, i) => {
        switch (entry.type) {
          case "message":     return <MessageBlock    key={i} entry={entry} />;
          case "checkpoint":  return <CheckpointBlock key={i} entry={entry} />;
          case "tool_call":   return <ToolCallBlock   key={i} entry={entry} />;
          case "tool_result": return <ToolResultBlock key={i} entry={entry} />;
          case "usage":       return <UsageBlock      key={i} entry={entry} />;
          case "user_inject": return <UserInjectBlock  key={i} entry={entry} />;
          case "stream":      return <StreamBlock      key={i} entry={entry} />;
          case "start":       return <ThinkingBlock   key={i} entry={entry} />;
          case "debrief":     return <DebriefBlock     key={i} entry={entry} />;
          default:            return null;
        }
      })}
    </div>
  );
}

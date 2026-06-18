import { useState, useEffect, useRef, useCallback } from "react";
import AgentCards from "./components/AgentCards";
import LogPanel from "./components/LogPanel";
import TokenChart from "./components/TokenChart";
import TaskForm from "./components/TaskForm";
import TerminalTab from "./components/TerminalTab";
import PipelineBar from "./components/PipelineBar";
import "./App.css";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/logs`;

const AGENT_COLORS = {
  sonnet:   "var(--sonnet)",
  nemotron: "var(--nemotron)",
  qwen:     "var(--qwen)",
  gemini:   "var(--gemini)",
  system:   "var(--muted)",
};

const INITIAL_AGENTS = {
  sonnet:   { status: "idle", usage: null },
  nemotron: { status: "idle", usage: null },
  qwen:     { status: "idle", usage: null },
  gemini:   { status: "idle", usage: null },
};

const STEP_TO_PHASE = {
  debate:    "debate",
  breakdown: "breakdown",
  execution: "execute",
  review:    "review",
  design:    "design",
};

export default function App() {
  const [agents, setAgents] = useState(INITIAL_AGENTS);
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState("logs");
  const [summary, setSummary] = useState(null);
  const [phase, setPhase] = useState("idle");
  const wsRef = useRef(null);

  const connectWs = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      if (msg.type === "ping") return;

      const ts    = new Date(msg.timestamp * 1000).toLocaleTimeString();
      const color = AGENT_COLORS[msg.agent] || "var(--text)";

      // Usage update → agent card token counts
      if (msg.type === "usage" && msg.data && msg.agent in INITIAL_AGENTS) {
        setAgents((prev) => ({
          ...prev,
          [msg.agent]: { ...prev[msg.agent], usage: msg.data, status: "active" },
        }));
      }

      // Checkpoint → advance pipeline phase
      if (msg.type === "checkpoint" && msg.data?.step) {
        const p = STEP_TO_PHASE[msg.data.step];
        if (p) setPhase(p);
      }

      // Terminal states
      if (["done", "cancelled", "error"].includes(msg.type)) {
        setRunning(false);
        setPhase(msg.type === "done" ? "done" : "idle");
        setAgents((prev) => {
          const next = {};
          for (const k of Object.keys(prev)) {
            next[k] = { ...prev[k], status: prev[k].usage ? "done" : "idle" };
          }
          return next;
        });
        if (msg.data) setSummary(msg.data);
      }

      // Log stream
      if (["message", "checkpoint", "tool_call", "tool_result", "start", "response"].includes(msg.type)) {
        setLogs((prev) => [
          ...prev.slice(-500),
          { ts, agent: msg.agent, type: msg.type, data: msg.data, color },
        ]);
      }
    };

    ws.onclose = () => setTimeout(connectWs, 2000);
  }, []);

  useEffect(() => {
    connectWs();
    return () => wsRef.current?.close();
  }, [connectWs]);

  const handleSubmit = async ({ task, image }) => {
    setRunning(true);
    setSummary(null);
    setLogs([]);
    setPhase("debate");
    setAgents(INITIAL_AGENTS);

    const fd = new FormData();
    fd.append("task", task);
    if (image) fd.append("image", image);

    await fetch("/api/run", { method: "POST", body: fd });
  };

  return (
    <div className="app">
      <header className="header">
        <span className="logo">⚡ Multi-Agent Dashboard</span>
        <span className="subtitle">sonnet · nemotron · qwen · gemini · pydantic-ai</span>
        {running && <span className="running-badge">● RUNNING</span>}
      </header>

      <main className="main">
        <aside className="sidebar">
          <TaskForm onSubmit={handleSubmit} running={running} />
          <AgentCards agents={agents} />
          <PipelineBar phase={phase} />
          {summary && (
            <div className="summary-box">
              <h3>Run Summary</h3>
              <p>
                Rounds: {summary.debate_rounds ?? "—"} ·{" "}
                {summary.passed ? "✅ PASSED" : "⚠️ INCOMPLETE"}
              </p>
              <p>
                {summary.duration_seconds}s ·{" "}
                ${summary.token_totals?.total_estimated_cost_usd?.toFixed(4) ?? "—"}
              </p>
            </div>
          )}
        </aside>

        <section className="content">
          <div className="tabs">
            {["logs", "tokens", "terminal"].map((t) => (
              <button
                key={t}
                className={`tab ${activeTab === t ? "active" : ""}`}
                onClick={() => setActiveTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          <div className="tab-content">
            {activeTab === "logs"     && <LogPanel logs={logs} />}
            {activeTab === "tokens"   && <TokenChart agents={agents} />}
            {activeTab === "terminal" && <TerminalTab />}
          </div>
        </section>
      </main>
    </div>
  );
}

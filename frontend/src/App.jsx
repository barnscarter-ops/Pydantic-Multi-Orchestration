import { useState, useEffect, useRef, useCallback } from "react";
import AgentCards from "./components/AgentCards";
import LogPanel from "./components/LogPanel";
import TokenChart from "./components/TokenChart";
import TaskForm from "./components/TaskForm";
import TerminalTab from "./components/TerminalTab";
import "./App.css";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/logs`;

const AGENT_COLORS = {
  PlanningAgent: "var(--planning)",
  ImplementationAgent: "var(--implementation)",
  ReviewAgent: "var(--review)",
  system: "var(--system)",
};

const INITIAL_AGENTS = {
  PlanningAgent: { status: "idle", usage: null },
  ImplementationAgent: { status: "idle", usage: null },
  ReviewAgent: { status: "idle", usage: null },
};

export default function App() {
  const [agents, setAgents] = useState(INITIAL_AGENTS);
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [activeTab, setActiveTab] = useState("logs");
  const [summary, setSummary] = useState(null);
  const wsRef = useRef(null);

  const connectWs = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      if (msg.type === "ping") return;

      const ts = new Date(msg.timestamp * 1000).toLocaleTimeString();
      const color = AGENT_COLORS[msg.agent] || "var(--text)";

      if (msg.type === "usage" && msg.data) {
        setAgents((prev) => ({
          ...prev,
          [msg.agent]: {
            ...prev[msg.agent],
            usage: msg.data,
            status: "active",
          },
        }));
      }

      if (msg.type === "checkpoint") {
        const step = msg.data?.step;
        if (step) {
          const agentKey =
            step === "planning" ? "PlanningAgent"
            : step === "implementation" ? "ImplementationAgent"
            : step === "review" ? "ReviewAgent"
            : null;
          if (agentKey) {
            setAgents((prev) => ({
              ...prev,
              [agentKey]: { ...prev[agentKey], status: "active" },
            }));
          }
        }
      }

      if (msg.type === "done" || msg.type === "summary") {
        setRunning(false);
        setAgents((prev) => {
          const next = {};
          for (const k of Object.keys(prev)) {
            next[k] = { ...prev[k], status: prev[k].usage ? "done" : "idle" };
          }
          return next;
        });
        if (msg.data) setSummary(msg.data);
      }

      if (["message", "checkpoint", "tool_call", "tool_result", "start", "response"].includes(msg.type)) {
        setLogs((prev) => [
          ...prev.slice(-500),
          { ts, agent: msg.agent, type: msg.type, data: msg.data, color },
        ]);
      }
    };

    ws.onclose = () => {
      setTimeout(connectWs, 2000);
    };
  }, []);

  useEffect(() => {
    connectWs();
    return () => wsRef.current?.close();
  }, [connectWs]);

  const handleSubmit = async ({ task, image }) => {
    setRunning(true);
    setSummary(null);
    setLogs([]);
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
        <span className="subtitle">claude-opus-4-8 · peer-to-peer · token-conscious</span>
      </header>

      <main className="main">
        <aside className="sidebar">
          <TaskForm onSubmit={handleSubmit} running={running} />
          <AgentCards agents={agents} />
          {summary && (
            <div className="summary-box">
              <h3>Run Summary</h3>
              <p>Rounds: {summary.rounds} · {summary.passed ? "✅ PASSED" : "⚠️ INCOMPLETE"}</p>
              <p>{summary.duration_seconds}s</p>
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
            {activeTab === "logs" && <LogPanel logs={logs} />}
            {activeTab === "tokens" && <TokenChart agents={agents} />}
            {activeTab === "terminal" && <TerminalTab />}
          </div>
        </section>
      </main>
    </div>
  );
}

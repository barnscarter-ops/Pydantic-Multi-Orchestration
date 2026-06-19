import { useState, useEffect, useRef, useCallback } from "react";
import LogPanel from "./components/LogPanel";
import BrowserTab from "./components/BrowserTab";
import TerminalTab from "./components/TerminalTab";
import PipelineBar from "./components/PipelineBar";
import AgentSidebar from "./components/AgentSidebar";
import TaskForm from "./components/TaskForm";
import InjectBar from "./components/InjectBar";
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

const VIEWS = ["logs", "browser", "terminal"];

export default function App() {
  const [agents, setAgents]       = useState(INITIAL_AGENTS);
  const [logs, setLogs]           = useState([]);
  const [running, setRunning]     = useState(false);
  const [activeTab, setActiveTab] = useState("logs");
  const [summary, setSummary]     = useState(null);
  const [phase, setPhase]         = useState("idle");
  const [jobId, setJobId]         = useState(null);
  const [tier, setTier]           = useState(null);
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

      if (msg.type === "start" && msg.agent in INITIAL_AGENTS) {
        setAgents((prev) => ({
          ...prev,
          [msg.agent]: { ...prev[msg.agent], status: "thinking" },
        }));
      }

      if (msg.type === "usage" && msg.data && msg.agent in INITIAL_AGENTS) {
        setAgents((prev) => ({
          ...prev,
          [msg.agent]: { ...prev[msg.agent], usage: msg.data, status: "waiting" },
        }));
        // Show token usage inline in the log
        setLogs((prev) => [
          ...prev.slice(-500),
          { ts, agent: msg.agent, type: "usage", data: msg.data, color },
        ]);
      }

      if (msg.type === "checkpoint" && msg.data?.step) {
        if (msg.data.step === "classify" && msg.data.tier) setTier(msg.data.tier);
        const p = STEP_TO_PHASE[msg.data.step];
        if (p) setPhase(p);
      }

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

      // Stream deltas: accumulate into the last stream entry for this agent
      if (msg.type === "stream") {
        if (msg.agent in INITIAL_AGENTS) {
          setAgents((prev) => {
            if (prev[msg.agent]?.status !== "active") {
              return { ...prev, [msg.agent]: { ...prev[msg.agent], status: "active" } };
            }
            return prev;
          });
        }
        setLogs((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.agent === msg.agent && last.type === "stream") {
            return [
              ...prev.slice(0, -1),
              { ...last, data: { text: (last.data?.text ?? "") + (msg.data?.delta ?? "") } },
            ];
          }
          return [
            ...prev.slice(-500),
            { ts, agent: msg.agent, type: "stream", data: { text: msg.data?.delta ?? "" }, color },
          ];
        });
        return;
      }

      if (msg.type === "user_inject") {
        setLogs((prev) => [
          ...prev.slice(-500),
          { ts, agent: "you", type: "user_inject", data: msg.data, color: "var(--accent)" },
        ]);
        return;
      }

      if (["message", "checkpoint", "tool_call", "tool_result", "start", "response"].includes(msg.type)) {
        setLogs((prev) => {
          // When the final message arrives, drop the preceding stream entry to avoid duplication
          let base = prev;
          if (msg.type === "message") {
            const idx = [...prev].reverse().findIndex(e => e.type === "stream" && e.agent === msg.agent);
            if (idx !== -1) base = prev.filter((_, i) => i !== prev.length - 1 - idx);
          }
          return [...base.slice(-500), { ts, agent: msg.agent, type: msg.type, data: msg.data, color }];
        });
      }
    };

    ws.onclose = () => setTimeout(connectWs, 2000);
  }, []);

  useEffect(() => {
    connectWs();
    return () => wsRef.current?.close();
  }, [connectWs]);

  // Session restore: ?session=<job_id> replays stored events on load
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session");
    if (!sessionId) return;
    setJobId(sessionId);

    fetch(`/api/jobs/${sessionId}/events`)
      .then(r => r.ok ? r.json() : [])
      .then(events => {
        if (!events.length) return;
        const replayedLogs = [];
        const replayedAgents = { ...INITIAL_AGENTS };
        let lastPhase   = "idle";
        let lastSummary = null;

        for (const msg of events) {
          if (msg.type === "ping") continue;
          const ts    = new Date(msg.timestamp * 1000).toLocaleTimeString();
          const color = AGENT_COLORS[msg.agent] || "var(--text)";

          if (msg.type === "usage" && msg.agent in INITIAL_AGENTS) {
            replayedAgents[msg.agent] = { status: "done", usage: msg.data };
            replayedLogs.push({ ts, agent: msg.agent, type: "usage", data: msg.data, color });
          } else if (msg.type === "checkpoint" && msg.data?.step) {
            const p = STEP_TO_PHASE[msg.data.step];
            if (p) lastPhase = p;
            replayedLogs.push({ ts, agent: msg.agent, type: "checkpoint", data: msg.data, color });
          } else if (msg.type === "user_inject") {
            replayedLogs.push({ ts, agent: "you", type: "user_inject", data: msg.data, color: "var(--accent)" });
          } else if (["message", "tool_call", "tool_result", "start", "stream"].includes(msg.type)) {
            replayedLogs.push({ ts, agent: msg.agent, type: msg.type, data: msg.data, color });
          } else if (msg.type === "done") {
            lastPhase = "done";
            if (msg.data) lastSummary = msg.data;
          }
        }

        setLogs(replayedLogs.slice(-500));
        setAgents(replayedAgents);
        setPhase(lastPhase);
        if (lastSummary) setSummary(lastSummary);
      })
      .catch(() => {});
  }, []);

  const handleSubmit = async ({ task, image }) => {
    setRunning(true);
    setSummary(null);
    setLogs([]);
    setPhase("idle");
    setTier(null);
    setAgents(INITIAL_AGENTS);

    const fd = new FormData();
    fd.append("task", task);
    if (image) fd.append("image", image);

    const res = await fetch("/api/run", { method: "POST", body: fd });
    const json = await res.json();
    setJobId(json.job_id ?? null);
  };

  const handleInject = async (comment) => {
    if (!comment.trim() || !jobId) return;
    await fetch("/api/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment, job_id: jobId }),
    });
  };

  return (
    <div className="app">

      <header className="header">
        <span className="app-name">Orchestrator</span>
        <nav className="view-switcher">
          {VIEWS.map((v) => (
            <button
              key={v}
              className={`view-btn ${activeTab === v ? "active" : ""}`}
              onClick={() => setActiveTab(v)}
            >
              {v}
            </button>
          ))}
        </nav>
        <div className="header-right">
          {running && <span className="live-pill">● live</span>}
        </div>
      </header>

      <PipelineBar phase={phase} summary={summary} tier={tier} />

      <div className="workspace">
        <AgentSidebar agents={agents} />

        <div className="content-area">
          {activeTab === "logs"     && <LogPanel logs={logs} />}
          {activeTab === "browser"  && <BrowserTab />}
          {activeTab === "terminal" && <TerminalTab />}
        </div>
      </div>

      {running && <InjectBar onInject={handleInject} />}
      <TaskForm onSubmit={handleSubmit} running={running} />

    </div>
  );
}

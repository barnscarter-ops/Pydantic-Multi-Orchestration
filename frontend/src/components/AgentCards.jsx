import "./AgentCards.css";

const AGENT_META = {
  sonnet:   { label: "Planner",  model: "claude-sonnet-4-6",   color: "var(--sonnet)"   },
  nemotron: { label: "Reviewer", model: "Nemotron 550B · NIM", color: "var(--nemotron)" },
  qwen:     { label: "Executor", model: "Qwen3-14B · local",   color: "var(--qwen)"     },
  gemini:   { label: "Designer", model: "Gemini 2.5 Pro",      color: "var(--gemini)"   },
};

function fmt(n) {
  if (n === undefined || n === null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function AgentCards({ agents }) {
  const maxIn = Math.max(
    ...Object.values(agents).map((a) => a.usage?.input_tokens || 0),
    1
  );

  return (
    <div className="agent-bench">
      {Object.entries(agents).map(([name, state], i) => {
        const meta    = AGENT_META[name] || { label: name, model: name, color: "var(--accent)" };
        const barPct  = state.usage ? Math.min((state.usage.input_tokens / maxIn) * 100, 100) : 0;
        const isActive = state.status === "active";

        return (
          <div
            key={name}
            className={`agent-tile ${state.status}`}
            style={{ "--agent-color": meta.color, "--card-i": i }}
          >
            {/* Glow border top */}
            <div className="tile-glow-bar" />

            {/* Scanline sweep when active */}
            {isActive && <div className="tile-scanline" />}

            <div className="tile-head">
              <span className="tile-label">
                {isActive && <span className="hb-dot" />}
                {meta.label}
              </span>
              <span className={`tile-badge ${state.status}`}>
                {state.status.toUpperCase()}
              </span>
            </div>

            <span className="tile-model">{meta.model}</span>

            <div className="tile-meter">
              <div className="tile-meter-fill" style={{ width: `${barPct}%` }} />
            </div>

            <div className="tile-stats">
              {state.usage ? (
                <>
                  <span className="stat-item">
                    <span className="stat-label">in</span>
                    {fmt(state.usage.input_tokens)}
                  </span>
                  <span className="stat-sep">·</span>
                  <span className="stat-item">
                    <span className="stat-label">out</span>
                    {fmt(state.usage.output_tokens)}
                  </span>
                  <span className="stat-sep">·</span>
                  <span className="stat-cost">
                    ${(state.usage.estimated_cost_usd ?? 0).toFixed(4)}
                  </span>
                </>
              ) : (
                <span className="tile-idle">waiting</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

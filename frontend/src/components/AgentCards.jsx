import "./AgentCards.css";

const AGENT_META = {
  sonnet:   { icon: "🧠", color: "var(--sonnet)",   model: "claude-sonnet-4-6",   role: "Planner"  },
  nemotron: { icon: "⚡", color: "var(--nemotron)", model: "Nemotron 550B · NIM",  role: "Reviewer" },
  qwen:     { icon: "🛠️", color: "var(--qwen)",     model: "Qwen3-14B · local",    role: "Executor" },
  gemini:   { icon: "✨", color: "var(--gemini)",   model: "Gemini 2.5 Pro",        role: "Designer" },
};

function fmt(n) {
  if (n === undefined || n === null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function AgentCards({ agents }) {
  return (
    <div className="agent-cards">
      <h3>Agents</h3>
      {Object.entries(agents).map(([name, state]) => {
        const meta = AGENT_META[name] || { icon: "🤖", color: "var(--accent)", model: name, role: name };
        return (
          <div
            key={name}
            className={`agent-card ${state.status}`}
            style={{ "--agent-color": meta.color }}
          >
            <div className="card-header">
              <span className="icon">{meta.icon}</span>
              <div className="agent-info">
                <span className="agent-name">{meta.role}</span>
                <span className="agent-model">{meta.model}</span>
              </div>
              <span className={`badge ${state.status}`}>{state.status}</span>
            </div>
            {state.usage && (
              <div className="usage-grid">
                <span>In</span>   <span>{fmt(state.usage.input_tokens)}</span>
                <span>Out</span>  <span>{fmt(state.usage.output_tokens)}</span>
                <span>Cost</span> <span>${(state.usage.estimated_cost_usd ?? 0).toFixed(4)}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

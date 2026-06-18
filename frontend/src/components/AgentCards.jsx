import "./AgentCards.css";

const AGENT_META = {
  PlanningAgent: { icon: "🗺️", color: "var(--planning)" },
  ImplementationAgent: { icon: "⚙️", color: "var(--implementation)" },
  ReviewAgent: { icon: "🔍", color: "var(--review)" },
};

function fmt(n) {
  if (n === undefined || n === null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function AgentCards({ agents }) {
  return (
    <div className="agent-cards">
      <h3>Agents</h3>
      {Object.entries(agents).map(([name, state]) => {
        const meta = AGENT_META[name] || { icon: "🤖", color: "var(--accent)" };
        return (
          <div
            key={name}
            className={`agent-card ${state.status}`}
            style={{ "--agent-color": meta.color }}
          >
            <div className="card-header">
              <span className="icon">{meta.icon}</span>
              <span className="agent-name">{name.replace("Agent", "")}</span>
              <span className={`badge ${state.status}`}>{state.status}</span>
            </div>
            {state.usage && (
              <div className="usage-grid">
                <span>In</span><span>{fmt(state.usage.input_tokens)}</span>
                <span>Out</span><span>{fmt(state.usage.output_tokens)}</span>
                <span>Cache↓</span><span>{fmt(state.usage.cache_read_input_tokens)}</span>
                <span>Cost</span><span>${state.usage.estimated_cost_usd?.toFixed(4)}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

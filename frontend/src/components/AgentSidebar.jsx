import { PlannerChar, ReviewerChar, ExecutorChar, DesignerChar } from "./AgentCharacters";
import "./AgentSidebar.css";

const AGENT_META = {
  sonnet:   { role: "Planner",  model: "claude-sonnet-4-6",   Char: PlannerChar,  color: "var(--sonnet)",   desc: "Strategizes the plan" },
  nemotron: { role: "Reviewer", model: "Nemotron 550B · NIM", Char: ReviewerChar, color: "var(--nemotron)", desc: "Critiques and audits"   },
  qwen:     { role: "Executor", model: "Qwen3-14B · local",   Char: ExecutorChar, color: "var(--qwen)",     desc: "Builds the solution"   },
  gemini:   { role: "Designer", model: "Gemini 2.5 Pro",      Char: DesignerChar, color: "var(--gemini)",   desc: "Crafts the output"     },
};

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export default function AgentSidebar({ agents }) {
  const maxIn = Math.max(
    ...Object.values(agents).map((a) => a.usage?.input_tokens || 0),
    1
  );

  return (
    <aside className="agent-sidebar">
      {Object.entries(agents).map(([name, state], i) => {
        const meta     = AGENT_META[name];
        const { Char } = meta;
        const isActive   = state.status === "active";
        const isThinking = state.status === "thinking";
        const isDone     = state.status === "done";
        const barPct   = state.usage
          ? Math.min((state.usage.input_tokens / maxIn) * 100, 100)
          : 0;

        return (
          <div
            key={name}
            className={`agent-card ${state.status}`}
            style={{ "--agent-color": meta.color, "--i": i }}
          >
            <div className="card-accent" />
            {isActive && <div className="card-scan" />}

            <div className="card-inner">
              <div className="card-avatar-col">
                <div className="char-wrap">
                  <Char active={isActive || isThinking} />
                </div>
                <span className={`status-dot ${state.status}`} />
              </div>

              <div className="card-info">
                <div className="card-header-row">
                  <span className="card-role">{meta.role}</span>
                  <span className={`card-badge ${state.status}`}>
                    {{ active: "LIVE", thinking: "THINKING", waiting: "WAIT", idle: "IDLE", done: "DONE" }[state.status] ?? state.status.toUpperCase()}
                  </span>
                </div>

                <span className="card-model">{meta.model}</span>

                <div className="card-meter">
                  <div className="meter-fill" style={{ width: `${barPct}%` }} />
                </div>

                <div className="card-stats">
                  {state.usage ? (
                    <>
                      <span>{fmt(state.usage.input_tokens)} in</span>
                      <span className="stat-dot">·</span>
                      <span>{fmt(state.usage.output_tokens)} out</span>
                      <span className="stat-dot">·</span>
                      <span className="stat-cost">
                        ${(state.usage.estimated_cost_usd ?? 0).toFixed(4)}
                      </span>
                    </>
                  ) : (
                    <span className="stat-waiting">{meta.desc}</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </aside>
  );
}

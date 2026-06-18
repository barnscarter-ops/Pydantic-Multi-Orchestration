import "./PipelineBar.css";

const PHASES = [
  { id: "debate",    label: "Debate",    icon: "💬" },
  { id: "breakdown", label: "Breakdown", icon: "📋" },
  { id: "execute",   label: "Execute",   icon: "⚙️" },
  { id: "review",    label: "Review",    icon: "🔍" },
  { id: "design",    label: "Design",    icon: "✨" },
];

export default function PipelineBar({ phase }) {
  const activeIdx = PHASES.findIndex((p) => p.id === phase);
  const isDone    = phase === "done";

  return (
    <div className="pipeline-bar">
      <h3>Pipeline</h3>
      <div className="phases">
        {PHASES.map((p, i) => {
          const done   = isDone || i < activeIdx;
          const active = !isDone && i === activeIdx;
          return (
            <div key={p.id} className={`phase-step ${done ? "done" : active ? "active" : ""}`}>
              <div className="phase-dot">
                {done ? "✓" : active ? <span className="pulse">{p.icon}</span> : p.icon}
              </div>
              <span className="phase-label">{p.label}</span>
              {i < PHASES.length - 1 && (
                <div className={`phase-connector ${done ? "done" : ""}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

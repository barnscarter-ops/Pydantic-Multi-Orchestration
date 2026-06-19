import "./PipelineBar.css";

const PHASES = [
  { id: "debate",    label: "Debate",    color: "var(--sonnet)"   },
  { id: "breakdown", label: "Breakdown", color: "var(--nemotron)" },
  { id: "execute",   label: "Execute",   color: "var(--qwen)"     },
  { id: "review",    label: "Review",    color: "var(--nemotron)" },
  { id: "design",    label: "Design",    color: "var(--gemini)"   },
];

export default function PipelineBar({ phase, summary }) {
  const activeIdx   = PHASES.findIndex((p) => p.id === phase);
  const isDone      = phase === "done";
  const activeColor = isDone
    ? "var(--qwen)"
    : activeIdx >= 0 ? PHASES[activeIdx].color : "var(--border)";

  return (
    <div className="pipeline-strip" style={{ "--active-color": activeColor }}>
      <span className="strip-head">pipeline</span>
      <span className="strip-divider">│</span>
      {PHASES.map((p, i) => {
        const done   = isDone || i < activeIdx;
        const active = !isDone && i === activeIdx;
        return (
          <div key={p.id} className={`strip-step ${done ? "done" : active ? "active" : ""}`}>
            {i > 0 && <span className="strip-sep">·</span>}
            {done && <span className="strip-check" style={{ color: p.color }}>✓</span>}
            <span className="strip-name">{p.label}</span>
          </div>
        );
      })}

      {isDone && summary && (
        <>
          <span className="strip-divider" style={{ marginLeft: "auto" }}>│</span>
          <span className="strip-summary">
            {summary.debate_rounds ?? "—"} rounds · {summary.duration_seconds}s
            · ${summary.token_totals?.total_estimated_cost_usd?.toFixed(4) ?? "—"}
            · <span className={summary.passed ? "sum-pass" : "sum-fail"}>
                {summary.passed ? "✓ passed" : "⚠ incomplete"}
              </span>
          </span>
        </>
      )}
    </div>
  );
}

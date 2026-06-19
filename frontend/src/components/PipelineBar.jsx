import "./PipelineBar.css";

const ALL_PHASES = [
  { id: "debate",    label: "Debate",    color: "var(--sonnet)"   },
  { id: "breakdown", label: "Breakdown", color: "var(--nemotron)" },
  { id: "execute",   label: "Execute",   color: "var(--qwen)"     },
  { id: "review",    label: "Review",    color: "var(--nemotron)" },
  { id: "design",    label: "Design",    color: "var(--gemini)"   },
];

// Which phases are active (non-skipped) for each tier
const TIER_PHASES = {
  trivial:  new Set(["execute"]),
  moderate: new Set(["breakdown", "execute", "review"]),
  complex:  new Set(["debate", "breakdown", "execute", "review", "design"]),
};

const TIER_COLOR = {
  trivial:  "var(--qwen)",
  moderate: "var(--sonnet)",
  complex:  "var(--nemotron)",
};

export default function PipelineBar({ phase, summary, tier }) {
  const activeIdx   = ALL_PHASES.findIndex((p) => p.id === phase);
  const isDone      = phase === "done";
  const activeColor = isDone
    ? "var(--qwen)"
    : activeIdx >= 0 ? ALL_PHASES[activeIdx].color : "var(--border)";

  const activeTierPhases = tier ? TIER_PHASES[tier] : null;

  return (
    <div className="pipeline-strip" style={{ "--active-color": activeColor }}>
      <span className="strip-head">pipeline</span>

      {tier && (
        <span className="strip-tier" style={{ color: TIER_COLOR[tier] }}>
          {tier}
        </span>
      )}

      <span className="strip-divider">│</span>

      {ALL_PHASES.map((p, i) => {
        const skipped = activeTierPhases && !activeTierPhases.has(p.id);
        const done    = !skipped && (isDone || i < activeIdx);
        const active  = !skipped && !isDone && i === activeIdx;
        return (
          <div
            key={p.id}
            className={`strip-step ${done ? "done" : active ? "active" : ""} ${skipped ? "skipped" : ""}`}
          >
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
            {summary.debate_rounds > 0 ? `${summary.debate_rounds} rounds · ` : ""}
            {summary.duration_seconds}s
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

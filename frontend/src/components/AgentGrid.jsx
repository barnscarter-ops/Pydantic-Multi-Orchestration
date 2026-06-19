import AgentPane from "./AgentPane";
import "./AgentGrid.css";

export default function AgentGrid({ agents, logs }) {
  const maxIn = Math.max(
    ...Object.values(agents).map((a) => a.usage?.input_tokens || 0),
    1
  );

  return (
    <div className="agent-grid">
      {Object.entries(agents).map(([name, state]) => (
        <AgentPane
          key={name}
          name={name}
          state={state}
          logs={logs}
          maxIn={maxIn}
        />
      ))}
    </div>
  );
}

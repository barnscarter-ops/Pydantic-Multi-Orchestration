import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import "./TokenChart.css";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

const AGENT_COLORS = {
  PlanningAgent: "#3fb950",
  ImplementationAgent: "#d2a8ff",
  ReviewAgent: "#ffa657",
};

export default function TokenChart({ agents }) {
  const labels = Object.keys(agents);
  const hasData = labels.some((k) => agents[k].usage);

  if (!hasData) {
    return <p className="chart-empty">Token data will appear here once agents start running…</p>;
  }

  const inputData = labels.map((k) => agents[k].usage?.input_tokens || 0);
  const outputData = labels.map((k) => agents[k].usage?.output_tokens || 0);
  const cacheData = labels.map((k) => agents[k].usage?.cache_read_input_tokens || 0);

  const data = {
    labels: labels.map((l) => l.replace("Agent", "")),
    datasets: [
      {
        label: "Input Tokens",
        data: inputData,
        backgroundColor: labels.map((k) => AGENT_COLORS[k] + "99"),
        borderColor: labels.map((k) => AGENT_COLORS[k]),
        borderWidth: 1,
      },
      {
        label: "Output Tokens",
        data: outputData,
        backgroundColor: labels.map((k) => AGENT_COLORS[k] + "55"),
        borderColor: labels.map((k) => AGENT_COLORS[k]),
        borderWidth: 1,
      },
      {
        label: "Cache Hits",
        data: cacheData,
        backgroundColor: "#58a6ff55",
        borderColor: "#58a6ff",
        borderWidth: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: "#e6edf3", font: { size: 11 } },
      },
    },
    scales: {
      x: {
        ticks: { color: "#8b949e" },
        grid: { color: "#30363d" },
      },
      y: {
        ticks: { color: "#8b949e" },
        grid: { color: "#30363d" },
      },
    },
  };

  return (
    <div className="token-chart-wrapper">
      <div className="chart-container">
        <Bar data={data} options={options} />
      </div>
      <div className="cost-table">
        <h3>Estimated Cost (USD)</h3>
        <table>
          <thead>
            <tr><th>Agent</th><th>Input</th><th>Output</th><th>Cache↓</th><th>Total~</th></tr>
          </thead>
          <tbody>
            {labels.map((k) => {
              const u = agents[k].usage;
              if (!u) return null;
              return (
                <tr key={k}>
                  <td style={{ color: AGENT_COLORS[k] }}>{k.replace("Agent", "")}</td>
                  <td>{u.input_tokens?.toLocaleString()}</td>
                  <td>{u.output_tokens?.toLocaleString()}</td>
                  <td>{u.cache_read_input_tokens?.toLocaleString()}</td>
                  <td>${u.estimated_cost_usd?.toFixed(4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

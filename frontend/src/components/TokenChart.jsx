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
  sonnet:   "#58a6ff",
  nemotron: "#ffa657",
  qwen:     "#3fb950",
  gemini:   "#d2a8ff",
};

const AGENT_LABELS = {
  sonnet:   "Sonnet",
  nemotron: "Nemotron",
  qwen:     "Qwen",
  gemini:   "Gemini",
};

const COST_RATES = {
  sonnet:   "In $3 / Out $15 per 1M",
  nemotron: "In $0.99 / Out $3.99 per 1M",
  qwen:     "Free (local inference)",
  gemini:   "In $1.25 / Out $5 per 1M",
};

export default function TokenChart({ agents }) {
  const labels  = Object.keys(agents);
  const hasData = labels.some((k) => agents[k].usage);

  if (!hasData) {
    return <p className="chart-empty">Token data will appear here once agents start running…</p>;
  }

  const inputData  = labels.map((k) => agents[k].usage?.input_tokens  || 0);
  const outputData = labels.map((k) => agents[k].usage?.output_tokens || 0);

  const data = {
    labels: labels.map((l) => AGENT_LABELS[l] || l),
    datasets: [
      {
        label: "Input Tokens",
        data: inputData,
        backgroundColor: labels.map((k) => (AGENT_COLORS[k] || "#8b949e") + "99"),
        borderColor:     labels.map((k) => AGENT_COLORS[k] || "#8b949e"),
        borderWidth: 1,
      },
      {
        label: "Output Tokens",
        data: outputData,
        backgroundColor: labels.map((k) => (AGENT_COLORS[k] || "#8b949e") + "55"),
        borderColor:     labels.map((k) => AGENT_COLORS[k] || "#8b949e"),
        borderWidth: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#e6edf3", font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
      y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
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
            <tr><th>Agent</th><th>In</th><th>Out</th><th>Cost</th><th>Rate</th></tr>
          </thead>
          <tbody>
            {labels.map((k) => {
              const u = agents[k].usage;
              if (!u) return null;
              return (
                <tr key={k}>
                  <td style={{ color: AGENT_COLORS[k] || "#8b949e" }}>
                    {AGENT_LABELS[k] || k}
                  </td>
                  <td>{u.input_tokens?.toLocaleString()}</td>
                  <td>{u.output_tokens?.toLocaleString()}</td>
                  <td>${(u.estimated_cost_usd ?? 0).toFixed(4)}</td>
                  <td className="rate-cell">{COST_RATES[k] || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

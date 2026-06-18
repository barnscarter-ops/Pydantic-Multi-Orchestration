import { useState, useRef } from "react";
import "./TaskForm.css";

export default function TaskForm({ onSubmit, running }) {
  const [task, setTask] = useState("");
  const [image, setImage] = useState(null);
  const fileRef = useRef();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!task.trim()) return;
    onSubmit({ task, image });
  };

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <h2>New Task</h2>
      <textarea
        className="task-input"
        placeholder="Describe the task for the agents…"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        rows={5}
        disabled={running}
      />
      <div className="image-row">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => fileRef.current.click()}
          disabled={running}
        >
          {image ? "📎 " + image.name.slice(0, 20) : "Attach Image"}
        </button>
        {image && (
          <button
            type="button"
            className="btn-clear"
            onClick={() => { setImage(null); fileRef.current.value = ""; }}
          >
            ✕
          </button>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => setImage(e.target.files[0] || null)}
      />
      <button type="submit" disabled={running || !task.trim()}>
        {running ? "Running…" : "Run Agents"}
      </button>
    </form>
  );
}

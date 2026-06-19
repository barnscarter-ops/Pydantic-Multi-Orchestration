import { useState, useRef } from "react";
import "./TaskForm.css";

export default function TaskForm({ onSubmit, running }) {
  const [task, setTask]   = useState("");
  const [image, setImage] = useState(null);
  const fileRef           = useRef();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!task.trim()) return;
    onSubmit({ task, image });
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit(e);
  };

  return (
    <form className="task-dock" onSubmit={handleSubmit}>
      <textarea
        className="dock-input"
        placeholder="Describe the task…  (Ctrl+Enter to run)"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={handleKey}
        rows={2}
        disabled={running}
      />
      <div className="dock-actions">
        <button
          type="button"
          className="dock-attach"
          onClick={() => fileRef.current.click()}
          disabled={running}
          title="Attach image"
        >
          {image ? `📎 ${image.name.slice(0, 14)}` : "attach"}
        </button>
        {image && (
          <button
            type="button"
            className="dock-clear"
            onClick={() => { setImage(null); fileRef.current.value = ""; }}
          >
            ✕
          </button>
        )}
        <button type="submit" className="dock-run" disabled={running || !task.trim()}>
          {running ? "running…" : "run"}
        </button>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => setImage(e.target.files[0] || null)}
      />
    </form>
  );
}

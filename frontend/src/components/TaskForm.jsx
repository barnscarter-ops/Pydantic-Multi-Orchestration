import { useState, useRef } from "react";
import "./TaskForm.css";

export default function TaskForm({ onSubmit, onChat, onNewTask, mode, running }) {
  const [text, setText]   = useState("");
  const [image, setImage] = useState(null);
  const fileRef           = useRef();
  const isChat = mode === "chat";

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    if (isChat) {
      onChat(text.trim());
      setText("");
    } else {
      onSubmit({ task: text, image });
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter") {
      if (isChat && !e.shiftKey) { handleSubmit(e); return; }
      if (!isChat && (e.ctrlKey || e.metaKey)) handleSubmit(e);
    }
  };

  return (
    <form className="task-dock" onSubmit={handleSubmit}>
      <textarea
        className="dock-input"
        placeholder={
          isChat
            ? "Ask a question or request changes…  (Enter to send, Shift+Enter for newline)"
            : "Describe the task…  (Ctrl+Enter to run)"
        }
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKey}
        rows={2}
        disabled={running}
      />
      <div className="dock-actions">
        {isChat ? (
          <button
            type="button"
            className="dock-attach dock-new-task"
            onClick={onNewTask}
            title="Start a new task"
          >
            + new task
          </button>
        ) : (
          <>
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
          </>
        )}
        <button
          type="submit"
          className="dock-run"
          disabled={running || !text.trim()}
        >
          {running ? "running…" : isChat ? "send" : "run"}
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

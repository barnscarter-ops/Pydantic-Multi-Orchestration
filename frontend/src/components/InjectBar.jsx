import { useState } from "react";
import "./InjectBar.css";

export default function InjectBar({ onInject }) {
  const [comment, setComment] = useState("");

  const submit = () => {
    if (!comment.trim()) return;
    onInject(comment.trim());
    setComment("");
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="inject-bar">
      <span className="inject-label">→</span>
      <input
        className="inject-input"
        placeholder="Inject a comment to the agents…  (Enter to send)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        onKeyDown={handleKey}
        autoFocus
      />
      <button className="inject-send" onClick={submit} disabled={!comment.trim()}>
        inject
      </button>
    </div>
  );
}

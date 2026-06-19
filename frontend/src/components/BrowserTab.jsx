import { useState, useRef } from "react";
import "./BrowserTab.css";

const DEFAULT_URL = "http://localhost:8000/api";

export default function BrowserTab() {
  const [src, setSrc]       = useState(DEFAULT_URL);
  const [input, setInput]   = useState(DEFAULT_URL);
  const [loading, setLoading] = useState(false);
  const frameRef = useRef(null);

  const go = (raw) => {
    let url = raw.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) url = "http://" + url;
    setSrc(url);
    setInput(url);
    setLoading(true);
  };

  const handleKey = (e) => {
    if (e.key === "Enter") go(input);
  };

  const tryBack = () => {
    try { frameRef.current?.contentWindow.history.back(); } catch {}
  };

  const tryForward = () => {
    try { frameRef.current?.contentWindow.history.forward(); } catch {}
  };

  const tryReload = () => {
    try {
      frameRef.current?.contentWindow.location.reload();
    } catch {
      setSrc(s => s + "");
    }
  };

  return (
    <div className="browser-tab">
      <div className="browser-bar">
        <button className="nav-btn" onClick={tryBack} title="Back">‹</button>
        <button className="nav-btn" onClick={tryForward} title="Forward">›</button>
        <button className="nav-btn reload" onClick={tryReload} title="Reload">
          {loading ? "×" : "↻"}
        </button>
        <input
          className="url-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          onFocus={e => e.target.select()}
          placeholder="Enter URL…"
          spellCheck={false}
        />
        <button className="go-btn" onClick={() => go(input)}>Go</button>
      </div>
      <iframe
        ref={frameRef}
        src={src}
        className="browser-frame"
        title="Browser"
        onLoad={() => setLoading(false)}
        onError={() => setLoading(false)}
      />
    </div>
  );
}

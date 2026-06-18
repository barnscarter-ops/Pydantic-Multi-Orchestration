import { useEffect, useRef } from "react";
import "./TerminalTab.css";

export default function TerminalTab() {
  const containerRef = useRef(null);
  const termRef = useRef(null);
  const fitRef = useRef(null);

  useEffect(() => {
    let terminal;
    let fitAddon;

    // Lazy-load xterm to avoid SSR issues
    Promise.all([
      import("@xterm/xterm"),
      import("@xterm/addon-fit"),
    ]).then(([{ Terminal }, { FitAddon }]) => {
      terminal = new Terminal({
        theme: {
          background: "#0d1117",
          foreground: "#e6edf3",
          cursor: "#58a6ff",
          selectionBackground: "#264f78",
          black: "#0d1117",
          brightBlack: "#30363d",
          white: "#e6edf3",
          brightWhite: "#ffffff",
        },
        fontFamily: '"Fira Code", "Cascadia Code", monospace',
        fontSize: 13,
        cursorBlink: true,
        scrollback: 1000,
      });

      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);

      if (containerRef.current) {
        terminal.open(containerRef.current);
        fitAddon.fit();

        terminal.writeln("\x1b[1;34m╔══════════════════════════════════════╗\x1b[0m");
        terminal.writeln("\x1b[1;34m║  Multi-Agent Terminal (read-only)    ║\x1b[0m");
        terminal.writeln("\x1b[1;34m╚══════════════════════════════════════╝\x1b[0m");
        terminal.writeln("");
        terminal.writeln("\x1b[90mAgent tool call outputs will appear here.\x1b[0m");
        terminal.writeln("");
      }

      termRef.current = terminal;
      fitRef.current = fitAddon;
    });

    const handleResize = () => fitRef.current?.fit();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      termRef.current?.dispose();
    };
  }, []);

  // Expose a global so the log panel can write to the terminal
  useEffect(() => {
    window.__agentTerminal = (text) => {
      termRef.current?.writeln(text);
    };
    return () => { delete window.__agentTerminal; };
  }, []);

  return (
    <div className="terminal-tab">
      <div className="terminal-header">
        <span className="terminal-dot red" />
        <span className="terminal-dot yellow" />
        <span className="terminal-dot green" />
        <span className="terminal-title">Agent Tool Output</span>
      </div>
      <div ref={containerRef} className="terminal-container" />
    </div>
  );
}

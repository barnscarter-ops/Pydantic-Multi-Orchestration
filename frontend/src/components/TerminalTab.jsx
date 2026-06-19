import { useEffect, useRef } from "react";
import "./TerminalTab.css";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/terminal`;

export default function TerminalTab() {
  const containerRef = useRef(null);
  const termRef      = useRef(null);
  const wsRef        = useRef(null);
  const fitRef       = useRef(null);

  useEffect(() => {
    let terminal;
    let fitAddon;
    let ws;

    Promise.all([
      import("@xterm/xterm"),
      import("@xterm/addon-fit"),
    ]).then(([{ Terminal }, { FitAddon }]) => {
      terminal = new Terminal({
        theme: {
          background:          "#1a1d2e",
          foreground:          "#e4e6f5",
          cursor:              "#818cf8",
          cursorAccent:        "#1a1d2e",
          selectionBackground: "#3e4268",
          black:               "#1a1d2e",
          brightBlack:         "#3e4268",
          red:                 "#f87171",
          green:               "#50d890",
          yellow:              "#ffa060",
          blue:                "#60a0ff",
          magenta:             "#d088ff",
          cyan:                "#818cf8",
          white:               "#e4e6f5",
          brightWhite:         "#ffffff",
        },
        fontFamily: '"IBM Plex Mono", "Fira Code", monospace',
        fontSize: 13,
        cursorBlink: true,
        cursorStyle: "block",
        scrollback: 2000,
        allowTransparency: false,
      });

      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);

      if (containerRef.current) {
        terminal.open(containerRef.current);
        fitAddon.fit();
      }

      termRef.current = terminal;
      fitRef.current  = fitAddon;

      // Connect WebSocket terminal
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        terminal.writeln("\x1b[1;34m─── Orchestrator Shell ─────────────────────\x1b[0m");
        terminal.writeln("\x1b[90mConnected · type commands below\x1b[0m");
        terminal.writeln("");
      };

      ws.onmessage = (evt) => {
        terminal.write(evt.data);
      };

      ws.onclose = () => {
        terminal.writeln("\x1b[33m\r\n─── connection closed ───────────────────────\x1b[0m");
      };

      ws.onerror = () => {
        terminal.writeln("\x1b[31m\r\n─── connection error ────────────────────────\x1b[0m");
      };

      // Send keystrokes to the shell
      terminal.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });
    });

    const handleResize = () => fitRef.current?.fit();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      wsRef.current?.close();
      termRef.current?.dispose();
    };
  }, []);

  return (
    <div className="terminal-tab">
      <div className="terminal-header">
        <span className="terminal-dot red" />
        <span className="terminal-dot yellow" />
        <span className="terminal-dot green" />
        <span className="terminal-title">Shell · cmd.exe</span>
      </div>
      <div ref={containerRef} className="terminal-container" />
    </div>
  );
}

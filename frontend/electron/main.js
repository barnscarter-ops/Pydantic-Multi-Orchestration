'use strict';

const { app, BrowserWindow, shell, Menu, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs   = require('fs');
const http = require('http');

const PORT       = 8000;
const SERVER_URL = `http://localhost:${PORT}`;

// In packaged mode, backend files land in process.resourcesPath/backend.
// In dev mode, they're two levels up from this file (the repo root).
const isPacked   = app.isPackaged;
const BACKEND_ROOT = isPacked
  ? path.join(process.resourcesPath, 'backend')
  : path.join(__dirname, '..', '..');

// Python resolution order:
//   1. ORCHESTRATOR_PYTHON env var (user override)
//   2. pythonw.exe in bundled .venv (no console window on Windows)
//   3. python.exe in bundled .venv
//   4. system pythonw / python on PATH
// pythonw.exe suppresses the console window for the process and all children,
// which is more reliable than windowsHide alone (conhost.exe can still flash briefly).
const VENV_DIR  = path.join(BACKEND_ROOT, '.venv', 'Scripts');
const VENV_PYW  = path.join(VENV_DIR, 'pythonw.exe');
const VENV_PY   = path.join(VENV_DIR, 'python.exe');
const SYS_PYTHONW = process.platform === 'win32' ? 'pythonw' : 'python';
const PYTHON    = process.env.ORCHESTRATOR_PYTHON ||
  (fs.existsSync(VENV_PYW) ? VENV_PYW :
   fs.existsSync(VENV_PY)  ? VENV_PY  : SYS_PYTHONW);

let backendProcess = null;
let mainWindow     = null;

// ── Backend ────────────────────────────────────────────────────────────────

function startBackend() {
  const uvicornArgs = [
    '-m', 'uvicorn', 'server:app',
    '--host', '127.0.0.1',
    '--port', String(PORT),
  ];
  // Only use --reload in dev mode (file watching breaks in packaged asar)
  if (!isPacked) uvicornArgs.push('--reload');

  backendProcess = spawn(PYTHON, uvicornArgs, {
    cwd:         BACKEND_ROOT,
    stdio:       ['ignore', 'pipe', 'pipe'],
    env:         { ...process.env },
    windowsHide: true,
  });
  backendProcess.stdout.on('data', d => process.stdout.write(d));
  backendProcess.stderr.on('data', d => process.stderr.write(d));
  backendProcess.on('error', err => {
    console.error('[backend]', err.message);
    dialog.showErrorBox(
      'Backend failed to start',
      `Could not launch Python backend.\n\nPython: ${PYTHON}\nError: ${err.message}\n\n` +
      'Set the ORCHESTRATOR_PYTHON environment variable to the correct python path and restart.'
    );
  });
  backendProcess.on('exit', code => console.log('[backend] exited with code', code));
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

function waitForBackend(retries = 40, delayMs = 500) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(`${SERVER_URL}/api/health`, res => {
        if (res.statusCode === 200) return resolve();
        retry();
      });
      req.on('error', retry);
      req.setTimeout(1000, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (--retries <= 0) return reject(new Error('Backend did not start in time'));
      setTimeout(attempt, delayMs);
    };
    attempt();
  });
}

// ── Window ─────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width:            1400,
    height:           900,
    minWidth:         800,
    minHeight:        600,
    backgroundColor:  '#0d0d10',
    titleBarStyle:    process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      nodeIntegration:  false,
      contextIsolation: true,
      preload:          path.join(__dirname, 'preload.js'),
    },
  });

  Menu.setApplicationMenu(null);
  mainWindow.loadURL(SERVER_URL);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith('http://localhost') && !url.startsWith('http://127.0.0.1')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── App lifecycle ──────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend();
  try {
    await waitForBackend();
    console.log('[electron] backend ready');
  } catch (err) {
    console.error('[electron]', err.message, '— opening window anyway');
  }
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopBackend);

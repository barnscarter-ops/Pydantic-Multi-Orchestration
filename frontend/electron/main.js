'use strict';

const { app, BrowserWindow, shell, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs   = require('fs');
const http = require('http');

const PORT       = 8000;
const SERVER_URL = `http://localhost:${PORT}`;
const REPO_ROOT  = path.join(__dirname, '..', '..');

// Prefer the project .venv python on Windows
const VENV_PY = path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe');
const PYTHON  = fs.existsSync(VENV_PY) ? VENV_PY : 'python';

let backendProcess = null;
let mainWindow     = null;

// ── Backend ────────────────────────────────────────────────────────────────

function startBackend() {
  backendProcess = spawn(
    PYTHON,
    ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', String(PORT)],
    {
      cwd:   REPO_ROOT,
      stdio: ['ignore', 'pipe', 'pipe'],
      env:   { ...process.env },
    }
  );
  backendProcess.stdout.on('data', d => process.stdout.write(d));
  backendProcess.stderr.on('data', d => process.stderr.write(d));
  backendProcess.on('error', err => console.error('[backend]', err.message));
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

  // Strip the default menu bar (keeps keyboard shortcuts)
  Menu.setApplicationMenu(null);

  mainWindow.loadURL(SERVER_URL);

  // Open external links in default browser, not Electron
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

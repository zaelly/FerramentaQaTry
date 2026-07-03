const { app, BrowserWindow, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn } = require("child_process");

const isDev = process.env.NODE_ENV === "development";
const BACKEND_PORT = process.env.QA_AGENT_PORT || "8756";
const BACKEND_DIR = path.join(__dirname, "..", "..", "backend");

let backendProcess = null;
let mainWindow = null;

function resolvePythonExecutable() {
  const winVenv = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
  const unixVenv = path.join(BACKEND_DIR, ".venv", "bin", "python");
  if (fs.existsSync(winVenv)) return winVenv;
  if (fs.existsSync(unixVenv)) return unixVenv;
  return process.platform === "win32" ? "python" : "python3";
}

function waitForBackend(retries = 60) {
  return new Promise((resolve, reject) => {
    const attempt = (remaining) => {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
        res.resume();
        resolve(true);
      });
      req.on("error", () => {
        if (remaining <= 0) return reject(new Error("Backend não respondeu a tempo."));
        setTimeout(() => attempt(remaining - 1), 1000);
      });
    };
    attempt(retries);
  });
}

function startBackend() {
  const python = resolvePythonExecutable();
  backendProcess = spawn(python, ["run.py"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, QA_AGENT_PORT: BACKEND_PORT },
  });

  backendProcess.stdout.on("data", (data) => process.stdout.write(`[backend] ${data}`));
  backendProcess.stderr.on("data", (data) => process.stderr.write(`[backend] ${data}`));
  backendProcess.on("exit", (code) => {
    console.log(`Backend encerrado (código ${code})`);
    backendProcess = null;
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0b0c10",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev) {
    await mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(async () => {
  startBackend();
  try {
    await waitForBackend();
  } catch (err) {
    console.error("Falha ao iniciar o backend Python:", err.message);
  }
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) backendProcess.kill();
});

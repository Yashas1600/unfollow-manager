const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

let mainWindow;
let backendProcess;
const PORT = 8080;

function getBackendPath() {
  // In dev: run python directly
  // In production: use the PyInstaller binary from resources
  if (app.isPackaged) {
    const resourcePath = process.resourcesPath;
    const binaryName = process.platform === "win32" ? "app.exe" : "app";
    return path.join(resourcePath, "backend", binaryName);
  }
  return null; // dev mode — we'll use python directly
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const binaryPath = getBackendPath();

    // Set browsers path so Playwright can find bundled Chromium
    const browsersPath = app.isPackaged
      ? path.join(process.resourcesPath, "browsers")
      : path.join(__dirname, "..", "browsers");

    const env = {
      ...process.env,
      FLASK_PORT: String(PORT),
      PLAYWRIGHT_BROWSERS_PATH: browsersPath,
    };

    if (binaryPath) {
      // Production: run the bundled binary
      backendProcess = spawn(binaryPath, [], { env });
    } else {
      // Dev: run with python
      const appDir = path.join(__dirname, "..");
      backendProcess = spawn("python3", ["app.py"], { cwd: appDir, env });
    }

    backendProcess.stdout.on("data", (data) => {
      console.log(`[backend] ${data.toString().trim()}`);
    });

    backendProcess.stderr.on("data", (data) => {
      console.log(`[backend] ${data.toString().trim()}`);
    });

    backendProcess.on("error", (err) => {
      reject(new Error(`Failed to start backend: ${err.message}`));
    });

    backendProcess.on("exit", (code) => {
      if (code !== null && code !== 0) {
        console.log(`[backend] exited with code ${code}`);
      }
    });

    // Poll until the server is ready
    let attempts = 0;
    const maxAttempts = 30;
    const check = () => {
      attempts++;
      const req = http.get(`http://127.0.0.1:${PORT}/`, (res) => {
        resolve();
      });
      req.on("error", () => {
        if (attempts >= maxAttempts) {
          reject(new Error("Backend did not start in time"));
        } else {
          setTimeout(check, 500);
        }
      });
      req.end();
    };
    setTimeout(check, 1000);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 600,
    height: 700,
    minWidth: 480,
    minHeight: 500,
    title: "Unfollow Manager",
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0a0a0a",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${PORT}/`);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  try {
    await startBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox(
      "Startup Error",
      `Could not start the app:\n${err.message}`
    );
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  }
});

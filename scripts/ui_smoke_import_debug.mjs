#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { spawn } from "node:child_process";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 1) {
  const key = process.argv[i];
  const value = process.argv[i + 1];
  if (key.startsWith("--")) {
    args.set(key.slice(2), value && !value.startsWith("--") ? value : "true");
    if (value && !value.startsWith("--")) i += 1;
  }
}

const appUrl = args.get("url") ?? "http://127.0.0.1:5173";
const ibtPath = args.get("ibt");
const edgePath = args.get("edge") ?? `${process.env["ProgramFiles(x86)"]}\\Microsoft\\Edge\\Application\\msedge.exe`;
const debugPort = Number(args.get("debug-port") ?? 9222);
const screenshotPath = args.get("screenshot") ?? "data/exports/debug/ui_smoke_platform.png";

if (!ibtPath) {
  console.error("Missing --ibt <path>");
  process.exit(2);
}

function httpJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let raw = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => { raw += chunk; });
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`${url} returned ${res.statusCode}: ${raw}`));
          return;
        }
        resolve(raw ? JSON.parse(raw) : null);
      });
    });
    req.on("error", reject);
    req.end();
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForDevtools() {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      return await httpJson(`http://127.0.0.1:${debugPort}/json/version`);
    } catch {
      await delay(250);
    }
  }
  throw new Error("Edge DevTools did not become ready.");
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
    this.ws.addEventListener("message", (message) => {
      const data = JSON.parse(message.data);
      if (data.id && this.pending.has(data.id)) {
        const { resolve, reject } = this.pending.get(data.id);
        this.pending.delete(data.id);
        if (data.error) reject(new Error(data.error.message));
        else resolve(data.result);
      } else if (data.method) {
        this.events.push(data);
      }
    });
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`${method} timed out`));
        }
      }, 30_000);
    });
  }

  close() {
    this.ws.close();
  }
}

async function evaluate(cdp, expression, timeoutMs = 30_000) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text ?? "Runtime evaluation failed");
  }
  return result.result?.value;
}

async function waitFor(cdp, expression, label, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await evaluate(cdp, expression, 5_000).catch(() => false);
    if (value) return value;
    await delay(500);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function clickText(cdp, text) {
  const escaped = JSON.stringify(text);
  const ok = await evaluate(cdp, `
    (() => {
      const candidates = [...document.querySelectorAll("button")];
      const button = candidates.find((el) => el.textContent && el.textContent.includes(${escaped}));
      if (!button) return false;
      button.click();
      return true;
    })()
  `);
  if (!ok) throw new Error(`Button not found: ${text}`);
}

async function setFile(cdp, filePath) {
  const { root } = await cdp.send("DOM.getDocument", { depth: -1, pierce: true });
  const { nodeId } = await cdp.send("DOM.querySelector", {
    nodeId: root.nodeId,
    selector: "input[type=file]",
  });
  if (!nodeId) throw new Error("Browser fallback file input not found.");
  await cdp.send("DOM.setFileInputFiles", { nodeId, files: [filePath] });
}

function summarizeEvents(events) {
  const consoleErrors = [];
  const failedRequests = [];
  for (const event of events) {
    if (event.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(event.params.type)) {
      consoleErrors.push({
        type: event.params.type,
        text: event.params.args.map((arg) => arg.value ?? arg.description ?? "").join(" "),
      });
    }
    if (event.method === "Runtime.exceptionThrown") {
      consoleErrors.push({ type: "exception", text: event.params.exceptionDetails?.text ?? "Runtime exception" });
    }
    if (event.method === "Network.responseReceived") {
      const { response } = event.params;
      if (response.status >= 400 && !response.url.endsWith("/favicon.ico")) {
        failedRequests.push({ status: response.status, url: response.url });
      }
    }
    if (event.method === "Network.loadingFailed" && !event.params.canceled) {
      failedRequests.push({ status: "failed", url: event.params.requestId, error: event.params.errorText });
    }
  }
  return { consoleErrors, failedRequests };
}

const userDataDir = path.join(process.env.TEMP ?? "C:\\tmp", `racelab-edge-smoke-${Date.now()}`);
const edge = spawn(edgePath, [
  "--headless=new",
  `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${userDataDir}`,
  "--disable-gpu",
  "--no-first-run",
  "about:blank",
], { stdio: "ignore", windowsHide: true });

let cdp = null;

try {
  await waitForDevtools();
  const target = await httpJson(`http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(appUrl)}`, { method: "PUT" });
  cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Network.enable");
  await cdp.send("DOM.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1600,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });

  await waitFor(cdp, "document.body && document.body.innerText.includes('RacerZLab')", "startup branding");
  await clickText(cdp, "New Session");
  await waitFor(cdp, "document.body.innerText.includes('No persisted runs yet') || document.body.innerText.includes('Platform')", "new session workspace");
  await waitFor(cdp, "document.querySelector('input[type=file]') !== null", "browser file input");
  await setFile(cdp, ibtPath);
  await waitFor(cdp, "document.body.innerText.includes('Overview') && document.body.innerText.includes('Platform')", "run opened", 240_000);
  await clickText(cdp, "Platform");
  await waitFor(cdp, "document.body.innerText.includes('Platform Trace Workbench')", "platform tab", 60_000);
  await waitFor(
    cdp,
    "Boolean(document.querySelector('.trace-panel')?.getAttribute('_echarts_instance_') || document.querySelector('.trace-panel canvas') || document.querySelector('.trace-panel svg'))",
    "ECharts render target",
    60_000,
  );

  const bodyText = await evaluate(cdp, "document.body.innerText.slice(0, 4000)");
  const screenshot = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));

  const summary = summarizeEvents(cdp.events);
  console.log(JSON.stringify({
    ok: summary.consoleErrors.length === 0 && summary.failedRequests.length === 0,
    url: appUrl,
    screenshot: screenshotPath,
    consoleErrors: summary.consoleErrors,
    failedRequests: summary.failedRequests,
    visibleTextSample: bodyText,
  }, null, 2));
  cdp.close();
  process.exit(summary.consoleErrors.length === 0 && summary.failedRequests.length === 0 ? 0 : 1);
} catch (error) {
  if (cdp) {
    const summary = summarizeEvents(cdp.events);
    const bodyText = await evaluate(cdp, "document.body?.innerText?.slice(0, 4000) ?? ''").catch(() => "");
    console.error(JSON.stringify({
      ok: false,
      consoleErrors: summary.consoleErrors,
      failedRequests: summary.failedRequests,
      visibleTextSample: bodyText,
    }, null, 2));
    cdp.close();
  }
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exit(1);
} finally {
  edge.kill();
}

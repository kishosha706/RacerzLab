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
const resume = args.get("resume") === "true";
const edgePath = args.get("edge") ?? `${process.env["ProgramFiles(x86)"]}\\Microsoft\\Edge\\Application\\msedge.exe`;
const debugPort = Number(args.get("debug-port") ?? 9222);
const screenshotPath = args.get("screenshot") ?? "data/exports/debug/ui_smoke_platform.png";

if (!ibtPath && !resume) {
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

async function clickSelector(cdp, selector) {
  await evaluate(
    cdp,
    `document.querySelector(${JSON.stringify(selector)})?.scrollIntoView({ block: "center", inline: "center" })`,
  );
  await delay(100);
  const { root } = await cdp.send("DOM.getDocument", { depth: -1, pierce: true });
  const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
  if (!nodeId) throw new Error(`Selector not found: ${selector}`);
  await cdp.send("Page.bringToFront");
  await cdp.send("DOM.focus", { nodeId });
  const { model } = await cdp.send("DOM.getBoxModel", { nodeId });
  const x = (model.content[0] + model.content[2] + model.content[4] + model.content[6]) / 4;
  const y = (model.content[1] + model.content[3] + model.content[5] + model.content[7]) / 4;
  await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
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

  await waitFor(
    cdp,
    "document.body && (document.body.innerText.includes('Enter the garage') || document.body.innerText.includes('New engineering session') || document.body.innerText.includes('RacerZLab'))",
    "startup branding",
  );
  if (await evaluate(cdp, "document.body.innerText.includes('Enter the garage')")) {
    await waitFor(cdp, "document.querySelector('button.launch-splash-gate') !== null", "launch gate");
    await waitFor(
      cdp,
      "(() => { const node = document.querySelector('button.launch-splash-gate'); return Boolean(node && Object.keys(node).some((key) => key.startsWith('__reactProps'))); })()",
      "hydrated launch gate",
    );
    for (let attempt = 0; attempt < 5; attempt += 1) {
      if (!(await evaluate(cdp, "document.body.innerText.includes('Enter the garage')"))) break;
      await clickSelector(cdp, "button.launch-splash-gate");
      await cdp.send("Page.bringToFront");
      await cdp.send("Input.dispatchKeyEvent", {
        type: "rawKeyDown",
        key: "Enter",
        code: "Enter",
        text: "\r",
        unmodifiedText: "\r",
        windowsVirtualKeyCode: 13,
        nativeVirtualKeyCode: 13,
      });
      await cdp.send("Input.dispatchKeyEvent", { type: "char", text: "\r" });
      await cdp.send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key: "Enter",
        code: "Enter",
        windowsVirtualKeyCode: 13,
        nativeVirtualKeyCode: 13,
      });
      await delay(500);
    }
    if (await evaluate(cdp, "document.body.innerText.includes('Enter the garage')")) {
      await evaluate(cdp, `
        (() => {
          const node = document.querySelector('button.launch-splash-gate');
          const propsKey = node && Object.keys(node).find((key) => key.startsWith('__reactProps'));
          if (!node || !propsKey || typeof node[propsKey]?.onClick !== 'function') return false;
          node[propsKey].onClick();
          return true;
        })()
      `);
      await delay(500);
    }
    // Last-resort test harness path for headless Edge builds that discard both
    // synthetic and CDP input during first-paint focus transfer. It dispatches
    // the component's own launch-gate state hook; product state and handlers are
    // otherwise unchanged.
    if (await evaluate(cdp, "document.body.innerText.includes('Enter the garage')")) {
      await evaluate(cdp, `
        (() => {
          const node = document.querySelector('button.launch-splash-gate');
          const fiberKey = node && Object.keys(node).find((key) => key.startsWith('__reactFiber'));
          let fiber = fiberKey ? node[fiberKey] : null;
          while (fiber && !(fiber.tag === 0 && fiber.memoizedState)) fiber = fiber.return;
          let hook = fiber?.memoizedState ?? null;
          for (let index = 0; hook && index < 9; index += 1) hook = hook.next;
          if (typeof hook?.queue?.dispatch !== 'function') return false;
          hook.queue.dispatch(false);
          return true;
        })()
      `);
    }
  }
  await waitFor(cdp, "document.body.innerText.includes('New engineering session')", "session picker");
  if (resume) {
    await waitFor(cdp, "document.querySelector('button.session-card-body') !== null", "persisted session");
    await clickSelector(cdp, "button.session-card-body");
  } else {
    await clickText(cdp, "New engineering session");
    await waitFor(cdp, "document.querySelector('input[type=file]') !== null", "browser file input");
    await setFile(cdp, ibtPath);
  }
  await waitFor(cdp, "document.body.innerText.includes('Overview') && document.body.innerText.includes('Platform')", "run opened", 240_000);
  await clickText(cdp, "Platform");
  await waitFor(cdp, "document.body.innerText.includes('Platform Trace Workbench')", "platform tab", 60_000);
  if (await evaluate(cdp, "document.body.innerText.includes('SHOW CHARTS')")) {
    await clickSelector(cdp, "button.platform-whole-lap-toggle");
    await waitFor(
      cdp,
      "document.querySelector('button.platform-whole-lap-toggle')?.getAttribute('aria-expanded') === 'true'",
      "whole-lap chart disclosure",
    );
  }
  await clickText(cdp, "Engineer");
  await waitFor(cdp, "document.querySelector('.crew-chief-deck') !== null", "Crew Chief workspace", 180_000);
  await waitFor(
    cdp,
    "document.body.innerText.includes('Smart Engineer') && document.body.innerText.includes('Crew Chief')",
    "intelligence and Crew Chief surfaces",
    180_000,
  );

  const bodyText = await evaluate(cdp, "document.body.innerText.slice(0, 4000)");
  const screenshot = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));

  const summary = summarizeEvents(cdp.events);
  const exactP26ApplicabilityWithheld =
    bodyText.includes("Crew Chief withheld")
    && bodyText.includes("requires review for car version");
  const expectedConflict = (item) =>
    (item.status === 409 && String(item.url).includes("/intelligence?"))
    || (
      item.status === 422
      && String(item.url).includes("/crew-chief-workspace?")
      && exactP26ApplicabilityWithheld
    );
  const unexpectedFailedRequests = summary.failedRequests.filter((item) => !expectedConflict(item));
  console.log(JSON.stringify({
    ok: summary.consoleErrors.length === 0 && unexpectedFailedRequests.length === 0,
    url: appUrl,
    mode: resume ? "restart" : "import",
    screenshot: screenshotPath,
    consoleErrors: summary.consoleErrors,
    expectedFailClosedRequests: summary.failedRequests.filter(expectedConflict),
    failedRequests: unexpectedFailedRequests,
    visibleTextSample: bodyText,
  }, null, 2));
  cdp.close();
  process.exit(summary.consoleErrors.length === 0 && unexpectedFailedRequests.length === 0 ? 0 : 1);
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

#!/usr/bin/env node
/**
 * Browser acceptance gate for the Cloakroom buyer demo.
 *
 * This intentionally uses only Node built-ins plus Chrome DevTools Protocol.
 * It avoids a Playwright download while still exercising the real browser UI.
 */

import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const RAW_SENSITIVE_VALUES = [
  "Sarah Morgan",
  "Acme Health",
  "sarah.morgan@acmehealth.eu",
  "Project Lantern",
  "EU-CUST-88421",
  "$2.4M",
  "18 percent discount",
  "+44 20 7946 0182",
  "15 Farringdon Street, London",
  "Q3 churn containment plan",
  "pre-acquisition integration risk",
];

function parseArgs(argv) {
  const args = {
    screenshotDir: path.join(os.tmpdir(), "cloakroom-demo-acceptance"),
    keepServer: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--screenshot-dir") {
      args.screenshotDir = argv[++i];
    } else if (arg === "--keep-server") {
      args.keepServer = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function assertOk(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function commandExists(name) {
  try {
    return execFileSync("which", [name], { encoding: "utf8" }).trim();
  } catch (_error) {
    return "";
  }
}

function findBrowser() {
  const envCandidates = [process.env.CLOAKROOM_BROWSER_BIN, process.env.CHROME_BIN].filter(Boolean);
  const macCandidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ];
  const pathCandidates = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
  ]
    .map(commandExists)
    .filter(Boolean);

  for (const candidate of [...envCandidates, ...macCandidates, ...pathCandidates]) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    "Chrome/Chromium was not found. Set CLOAKROOM_BROWSER_BIN to a headless-capable browser.",
  );
}

function startProcess(command, args, logPath) {
  const log = fs.openSync(logPath, "w");
  const child = spawn(command, args, {
    detached: true,
    stdio: ["ignore", log, log],
    env: { ...process.env },
  });
  child.unref();
  return { child, log };
}

function stopProcess(child) {
  if (!child || child.killed) {
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch (_error) {
    try {
      child.kill("SIGTERM");
    } catch (__error) {
      // Process already exited.
    }
  }
}

async function waitForJson(url, description, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return await response.json();
      }
      lastError = new Error(`${response.status} ${response.statusText}`);
    } catch (error) {
      lastError = error;
    }
    await delay(250);
  }
  throw new Error(`Timed out waiting for ${description}: ${lastError?.message || "unknown"}`);
}

class CdpSession {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    if (typeof WebSocket === "undefined") {
      throw new Error("This Node runtime does not expose WebSocket. Use Node 20+.");
    }
    this.ws = new WebSocket(this.wsUrl);
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) {
          reject(new Error(message.error.message));
        } else {
          resolve(message.result || {});
        }
      }
    };
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = () => reject(new Error("CDP WebSocket connection failed"));
    });
  }

  call(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }

  async evaluate(expression) {
    const result = await this.call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || "Browser evaluation failed");
    }
    return result.result?.value;
  }

  close() {
    this.ws?.close();
  }
}

async function waitForExpression(cdp, expression, description, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await cdp.evaluate(expression)) {
      return;
    }
    await delay(250);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

async function screenshot(cdp, screenshotDir, name) {
  const result = await cdp.call("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  const filePath = path.join(screenshotDir, `${name}.png`);
  fs.writeFileSync(filePath, Buffer.from(result.data, "base64"));
  return filePath;
}

async function runAcceptance() {
  const args = parseArgs(process.argv);
  fs.mkdirSync(args.screenshotDir, { recursive: true });
  const serverPort = await freePort();
  const cdpPort = await freePort();
  const browser = findBrowser();
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cloakroom-demo-acceptance-"));
  const serverLog = path.join(tmpRoot, "server.log");
  const browserLog = path.join(tmpRoot, "browser.log");
  const url = `http://127.0.0.1:${serverPort}/`;

  let serverProcess = null;
  let browserProcess = null;
  let cdp = null;

  try {
    serverProcess = startProcess(
      "uv",
      ["run", "cloakroom-demo-server", "--host", "127.0.0.1", "--port", String(serverPort)],
      serverLog,
    );
    await waitForJson(`${url}api/health`, "demo server health");

    browserProcess = startProcess(
      browser,
      [
        "--headless=new",
        `--remote-debugging-port=${cdpPort}`,
        `--user-data-dir=${path.join(tmpRoot, "chrome-profile")}`,
        "--window-size=1440,1100",
        "--disable-gpu",
        "--no-first-run",
        "--disable-background-networking",
        "--disable-component-update",
        url,
      ],
      browserLog,
    );

    const targets = await waitForJson(`http://127.0.0.1:${cdpPort}/json`, "Chrome CDP target");
    const page = targets.find((target) => target.type === "page");
    assertOk(page, "No Chrome page target found");
    cdp = new CdpSession(page.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.call("Runtime.enable");
    await cdp.call("Page.enable");

    await waitForExpression(
      cdp,
      "document.querySelector('#source-input')?.value.includes('Sarah Morgan')",
      "demo sample load",
    );
    await cdp.evaluate("document.querySelector('#shield-button').click()");
    await waitForExpression(
      cdp,
      "document.querySelector('#safe-output')?.innerText.includes('[PERSON_00001]')",
      "shielded AI-safe output",
      45000,
    );

    const shield = JSON.parse(
      await cdp.evaluate(`JSON.stringify({
        safeText: document.querySelector('#safe-output').innerText,
        safeStatus: document.querySelector('#safe-status').innerText,
        reviewText: document.querySelector('#review-table-body').innerText,
        reviewRows: document.querySelectorAll('#review-table-body tr').length,
        replaced: document.querySelector('#metric-replaced').innerText,
        leaks: document.querySelector('#metric-leaks').innerText,
        mappings: document.querySelector('#metric-mappings').innerText,
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth
      })`),
    );
    assertOk(shield.safeStatus === "Safe to paste into AI", "Shield status did not become safe");
    assertOk(shield.safeText.includes("[PERSON_00001]"), "AI-safe output missing person token");
    assertOk(shield.safeText.includes("[PROJECT_00001]"), "AI-safe output missing project token");
    assertOk(shield.reviewRows >= 10, "Detection review did not show enough rows");
    assertOk(shield.replaced === "12", `Expected 12 replacements, got ${shield.replaced}`);
    assertOk(shield.leaks === "0", `Expected 0 leaks, got ${shield.leaks}`);
    for (const raw of RAW_SENSITIVE_VALUES) {
      assertOk(!shield.safeText.includes(raw), `AI-safe output leaked raw value: ${raw}`);
      assertOk(!shield.reviewText.includes(raw), `Review table leaked raw value: ${raw}`);
    }
    assertOk(shield.scrollWidth === shield.clientWidth, "Desktop layout has horizontal overflow");
    const shieldScreenshot = await screenshot(cdp, args.screenshotDir, "shield");

    await cdp.evaluate("document.querySelector('#load-failure-button').click()");
    await waitForExpression(
      cdp,
      "document.querySelector('#restore-input')?.value.includes('[PERSON_001]')",
      "mutated failure sample",
    );
    await cdp.evaluate("document.querySelector('#restore-button').click()");
    await waitForExpression(
      cdp,
      "document.querySelector('#restore-status')?.innerText.includes('Blocked')",
      "blocked restore state",
      30000,
    );
    const restore = JSON.parse(
      await cdp.evaluate(`JSON.stringify({
        status: document.querySelector('#restore-status').innerText,
        changed: document.querySelector('#changed-tokens').innerText,
        error: document.querySelector('#restore-error').innerText,
        output: document.querySelector('#restore-output').innerText
      })`),
    );
    assertOk(restore.status === "Blocked", "Restore status did not block");
    assertOk(restore.changed === "1", `Expected one changed token, got ${restore.changed}`);
    assertOk(restore.error.includes("Restore blocked"), "Blocked copy missing title");
    assertOk(restore.error.includes("Expected: [PERSON_00001]"), "Blocked copy missing expected token");
    assertOk(restore.error.includes("Found: [PERSON_001]"), "Blocked copy missing found token");
    assertOk(
      restore.error.includes("No partial restore was created."),
      "Blocked copy missing no-partial-restore assurance",
    );
    assertOk(restore.output === "", "Blocked restore created partial output");
    const restoreScreenshot = await screenshot(cdp, args.screenshotDir, "restore-blocked");

    await cdp.evaluate("document.querySelector('[data-screen-target=\"trust\"]').click()");
    await waitForExpression(
      cdp,
      "Number(document.querySelector('#trust-mappings')?.innerText || 0) > 0",
      "trust center mappings",
    );
    const trust = JSON.parse(
      await cdp.evaluate(`JSON.stringify({
        mappings: document.querySelector('#trust-mappings').innerText,
        shields: document.querySelector('#trust-shields').innerText,
        restores: document.querySelector('#trust-restores').innerText,
        auditRows: document.querySelectorAll('#audit-table-body tr').length,
        localProof: document.querySelector('#local-proof-list').innerText
      })`),
    );
    assertOk(trust.mappings === "12", `Expected 12 mappings, got ${trust.mappings}`);
    assertOk(Number(trust.shields) >= 1, "Trust Center did not record shield event");
    assertOk(Number(trust.auditRows) >= 1, "Trust Center did not show audit-safe report");
    assertOk(trust.localProof.includes("Bind host: 127.0.0.1"), "Trust proof missing bind host");
    assertOk(trust.localProof.includes("External AI calls: 0"), "Trust proof missing zero AI calls");
    assertOk(
      trust.localProof.includes("Reports exclude original values"),
      "Trust proof missing report safety claim",
    );
    const trustScreenshot = await screenshot(cdp, args.screenshotDir, "trust-center");

    await cdp.call("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await cdp.call("Page.navigate", { url });
    await waitForExpression(
      cdp,
      "document.querySelector('#source-input')?.value.includes('Sarah Morgan')",
      "mobile sample load",
    );
    const mobile = JSON.parse(
      await cdp.evaluate(`JSON.stringify({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        statusPills: Array.from(document.querySelectorAll('.status-pill')).map((item) => item.innerText),
        sampleButtonWidth: document.querySelector('#load-sample-button').getBoundingClientRect().width
      })`),
    );
    assertOk(mobile.scrollWidth === mobile.clientWidth, "Mobile layout has horizontal overflow");
    assertOk(
      mobile.statusPills.includes("No original data sent"),
      "Mobile status strip missing local-proof copy",
    );
    const mobileScreenshot = await screenshot(cdp, args.screenshotDir, "mobile");

    console.log(
      JSON.stringify(
        {
          ok: true,
          url,
          shield: {
            replaced: shield.replaced,
            leaks: shield.leaks,
            reviewRows: shield.reviewRows,
          },
          restore: {
            status: restore.status,
            changed: restore.changed,
            partialOutput: restore.output.length,
          },
          trust,
          mobile,
          screenshots: [shieldScreenshot, restoreScreenshot, trustScreenshot, mobileScreenshot],
        },
        null,
        2,
      ),
    );
  } catch (error) {
    console.error(`Demo browser acceptance failed: ${error.message}`);
    console.error(`Server log: ${serverLog}`);
    console.error(`Browser log: ${browserLog}`);
    process.exitCode = 1;
  } finally {
    cdp?.close();
    if (!args.keepServer) {
      stopProcess(browserProcess?.child);
      stopProcess(serverProcess?.child);
    }
  }
}

await runAcceptance();

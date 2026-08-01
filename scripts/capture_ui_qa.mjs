#!/usr/bin/env node

/** Dependency-free Chrome DevTools screenshot helper for local visual QA. */

import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const [, , endpoint = "http://127.0.0.1:9223", pageUrl = "http://127.0.0.1:4173/app/", rawOut = "tmp/ui-qa"] = process.argv;
const outDir = resolve(rawOut);
await mkdir(outDir, { recursive: true });

const targets = await fetch(`${endpoint}/json/list`).then((response) => response.json());
const target = targets.find((item) => item.type === "page");
if (!target?.webSocketDebuggerUrl) throw new Error("Nessuna pagina Chrome disponibile via CDP");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolveOpen, rejectOpen) => {
  socket.addEventListener("open", resolveOpen, { once: true });
  socket.addEventListener("error", rejectOpen, { once: true });
});

let sequence = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id) return;
  const request = pending.get(message.id);
  if (!request) return;
  pending.delete(message.id);
  if (message.error) request.reject(new Error(message.error.message));
  else request.resolve(message.result ?? {});
});

function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolveRequest, rejectRequest) => {
    pending.set(id, { resolve: resolveRequest, reject: rejectRequest });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

const pause = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

async function viewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
  });
}

async function navigate() {
  await send("Page.navigate", { url: pageUrl });
  await pause(900);
}

async function clickButton(label) {
  const expression = `(() => {
    const target = [...document.querySelectorAll('button')]
      .find((button) => button.textContent.trim().includes(${JSON.stringify(label)}));
    if (!target) return false;
    target.click();
    return true;
  })()`;
  const result = await send("Runtime.evaluate", { expression, returnByValue: true });
  if (!result.result?.value) throw new Error(`Pulsante non trovato: ${label}`);
  await pause(250);
}

async function evaluate(expression) {
  await send("Runtime.evaluate", { expression });
  await pause(100);
}

async function screenshot(name) {
  const result = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(resolve(outDir, name), Buffer.from(result.data, "base64"));
}

await send("Page.enable");
await send("Runtime.enable");

await viewport(1440, 1100);
await navigate();
await screenshot("desktop-reference.png");
await clickButton("Modifica target");
await evaluate("document.activeElement?.blur(); window.scrollTo(0, 0)");
await screenshot("desktop-estimand-editor.png");

await navigate();
await clickButton("Modifica grafo");
await evaluate("document.activeElement?.blur(); document.querySelector('#graph-panel')?.scrollIntoView({block: 'start'}); window.scrollBy(0, -70)");
await screenshot("desktop-graph-editor.png");

await viewport(390, 844, true);
await navigate();
await screenshot("mobile-reference.png");

socket.close();
console.log(outDir);

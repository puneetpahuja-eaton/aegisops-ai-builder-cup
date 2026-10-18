import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const media = path.join(here, "media");
await mkdir(media, { recursive: true });
const live = process.argv.includes("--live");
const url = process.env.KAIROS_URL || (live ? "https://kairos-ai-498775210896.asia-south1.run.app" : "http://localhost:8503");
const executablePath = [
  path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(existsSync);
if (!executablePath) throw new Error("Install Chrome or Edge.");
const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(90_000);
const settled = async () => {
  await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 180_000 });
  await page.waitForTimeout(800);
  const exceptions = await page.locator('[data-testid="stException"]').allTextContents();
  assert.deepEqual(exceptions, [], `UI exceptions: ${exceptions.join("; ")}`);
};
const click = async (label) => {
  await page.getByRole("button", { name: label, exact: true }).last().click();
  await settled();
};
const tab = async (label) => {
  await page.getByRole("tab", { name: label, exact: true }).last().click();
};
const download = async (label) => {
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: label, exact: true }).last().click(),
  ]);
  return readFile(await file.path(), "utf8");
};
const audit = async () => {
  await tab("Agent trace & audit");
  return JSON.parse(await download("Download fleet audit JSON"));
};
const step = async (count) => {
  await click("Process next timestamp");
  await page.getByText(`${count}/12 timestamps processed`, { exact: true }).last().waitFor();
  await settled();
};
try {
  await page.goto(url);
  await page.getByRole("button", { name: "Load built-in synthetic fleet", exact: true }).waitFor();
  await settled();
  const template = JSON.parse(await download("Download fleet JSON template"));
  await click("Load built-in synthetic fleet");
  await step(1);
  await step(2);
  let result = await audit();
  if (result.cases[0]?.status === "ERROR") {
    await tab("Cases & approvals");
    await click("Retry fleet diagnosis");
    result = await audit();
  }
  assert.equal(result.cases.length, 1);
  const caseResult = result.cases[0];
  assert.equal(caseResult.root_asset_id, "FEEDER-01");
  assert.deepEqual(caseResult.symptom_asset_ids, ["MTR-07", "PMP-03"]);
  if (live) assert.match(caseResult.diagnosis._source, /^gemini:/);
  else assert.match(caseResult.diagnosis._source, /^offline-rules/);
  await tab("Cases & approvals");
  if (caseResult.status === "AWAITING_APPROVAL") {
    await page.getByRole("textbox", { name: "Fleet reviewer name", exact: true }).fill("Browser test supervisor");
    await click("Approve fleet sandbox");
    await step(3);
    await step(4);
    result = await audit();
    assert.equal(result.cases[0].verification.status, "simulated_recovery");
  } else {
    assert.equal(caseResult.status, "ESCALATED", "Unexpected case state");
    if (!live) throw new Error("Offline approval path unexpectedly escalated.");
  }
  await page.getByRole("heading", { name: "Fleet replay | synthetic", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(media, live ? "fleet-cloud.png" : "fleet-local.png") });
  if (live) {
    await tab("Agent trace & audit");
    await click("Save fleet case summaries to BigQuery");
    await page.getByText(/Saved 1 case summaries to BigQuery/).waitFor();
  }
  // Replace all IDs, not just a selected incident. The uploaded source field must not enable mutation.
  const idMap = new Map(template.assets.map(asset => [asset.id, `UPLOADED-${asset.id}`]));
  for (const asset of template.assets) {
    asset.id = idMap.get(asset.id);
    if (asset.parent_id) asset.parent_id = idMap.get(asset.parent_id);
  }
  for (const row of [...template.history, ...template.telemetry]) row.asset_id = idMap.get(row.asset_id);
  template.source = "synthetic";
  const inputPanel = page.locator("details").filter({ hasText: "Telemetry inputs, templates and privacy" }).first();
  if (!(await inputPanel.getAttribute("open"))) await inputPanel.locator("summary").first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "replacement-fleet.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(template)),
  });
  await settled();
  if (!(await inputPanel.getAttribute("open"))) await inputPanel.locator("summary").first().click();
  if (live) {
    const checkbox = page.getByRole("checkbox", { name: "I am authorized to send this non-confidential uploaded telemetry to Google Vertex AI.", exact: true });
    await checkbox.focus();
    await page.keyboard.press("Space");
    await settled();
  }
  await click("Load replacement telemetry");
  await page.getByRole("heading", { name: "Fleet replay | uploaded", exact: true }).waitFor();
  await step(1);
  await step(2);
  result = await audit();
  assert.equal(result.source, "uploaded");
  assert.ok(result.training.every(row => row.asset_id.startsWith("UPLOADED-")));
  assert.equal(result.cases[0].root_asset_id, "UPLOADED-FEEDER-01");
  if (result.cases[0].status === "ERROR") {
    await tab("Cases & approvals");
    await click("Retry fleet diagnosis");
    result = await audit();
  }
  if (live) assert.match(result.cases[0].diagnosis._source, /^gemini:/);
  if (result.cases[0].status === "AWAITING_APPROVAL") {
    await tab("Cases & approvals");
    await page.getByRole("textbox", { name: "Fleet reviewer name", exact: true }).fill("Uploaded-data observer");
    await click("Approve fleet sandbox");
    await step(3);
    await step(4);
    await step(5);
    result = await audit();
    assert.equal(result.cases[0].status, "FAILED", "Approval must not fabricate recovery in uploaded measurements.");
    const samples = result.samples.filter(row => row.asset_id === "UPLOADED-FEEDER-01");
    assert.equal(samples.at(-1).voltage_v, 330);
  }
  await tab("Live operations");
  await page.getByRole("heading", { name: "Fleet replay | uploaded", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(media, live ? "fleet-upload-cloud.png" : "fleet-upload-local.png") });
  const uploadedRun = result.run_id;
  if (!(await inputPanel.getAttribute("open"))) await inputPanel.locator("summary").first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "invalid-replacement.json", mimeType: "application/json", buffer: Buffer.from('{"assets":[],"history":[],"telemetry":[]}'),
  });
  await settled();
  if (!(await inputPanel.getAttribute("open"))) await inputPanel.locator("summary").first().click();
  await click("Load replacement telemetry");
  await page.getByText(/Replacement rejected; existing replay is unchanged/).waitFor();
  assert.equal((await audit()).run_id, uploadedRun, "An invalid upload replaced the current replay.");
  if (!live) {
    await click("Reset this replay");
    await click("Play replay");
    await page.getByText("2/12 timestamps processed", { exact: true }).waitFor();
    await settled();
    assert.ok(await page.getByRole("button", { name: "Play replay", exact: true }).isVisible(), "Replay did not pause for named approval.");
    assert.equal((await audit()).ticks_processed, 2);
  }
  await writeFile(path.join(media, live ? "fleet-cloud-result.json" : "fleet-local-result.json"), JSON.stringify({
    url, realGemini: live, replacementConfirmed: true, source: result.source,
    cases: result.cases.map(item => ({ root: item.root_asset_id, status: item.status, source: item.diagnosis._source })),
    toolCalls: result.tool_calls.length, testedAt: new Date().toISOString(),
  }, null, 2));
  console.log(JSON.stringify({ success: true, live, uploadedRoot: result.cases[0].root_asset_id,
    uploadedStatus: result.cases[0].status, toolCalls: result.tool_calls.length }));
} catch (error) {
  await page.screenshot({ path: path.join(media, live ? "fleet-cloud-failure.png" : "fleet-local-failure.png") });
  console.error((await page.locator('[data-testid="stException"]').allTextContents()).join("\n"));
  throw error;
} finally {
  await context.close();
  await browser.close();
}

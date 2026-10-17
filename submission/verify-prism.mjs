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
const url = process.env.AEGIS_URL || (live ? "https://aegis-ops-498775210896.asia-south1.run.app" : "http://localhost:8505");
const executablePath = [
  path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(existsSync);
if (!executablePath) throw new Error("Chrome or Edge is required.");
const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 }, acceptDownloads: true,
  ...(process.argv.includes("--record") ? { recordVideo: { dir: media, size: { width: 1440, height: 1000 } } } : {}),
});
const page = await context.newPage();
page.setDefaultTimeout(120_000);
const settled = async () => {
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 180_000 });
  await page.waitForTimeout(300);
  assert.deepEqual(await page.locator('[data-testid="stException"]').allTextContents(), []);
};
const click = async (label) => {
  await page.getByRole("button", { name: label, exact: true }).last().click();
  await settled();
};
const step = async (expected) => {
  await click("Step once");
  await page.getByText(new RegExp(`sample ${expected}/96`)).last().waitFor();
  await settled();
};
const expand = async (label) => {
  const panel = page.locator("details").filter({ has: page.locator("summary").filter({ hasText: label }) }).last();
  if ((await panel.getAttribute("open")) === null) await panel.locator("summary").first().click();
  return panel;
};
const tab = async (label) => {
  await page.getByRole("tab", { name: label, exact: true }).click();
  await settled();
};
const download = async (label) => {
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: label, exact: true }).click(),
  ]);
  return readFile(await file.path(), "utf8");
};
const audit = async () => {
  await tab("Cases");
  await expand("Cloud audit & full agent trace");
  return JSON.parse(await download("Download PRISM audit JSON"));
};
try {
  await page.goto(url);
  await page.getByRole("button", { name: "Step once", exact: true }).waitFor();
  await settled();
  const originalTabs = ["Live Operations", "Cases", "Counterfactual (value)", "Power Topology", "Models & Data", "How it works"];
  assert.deepEqual(await page.getByRole("tab").allTextContents(), originalTabs);
  for (const label of ["Play", "Pause", "Reset", "Step once"]) assert.ok(await page.getByRole("button", { name: label, exact: true }).count());
  await page.screenshot({ path: path.join(media, live ? "prism-cloud-home.png" : "prism-local-home.png") });
  console.log("Original tabs and controls verified.");
  // First supply fault begins at sample index 12 in the ORIGINAL simulator.
  for (let index = 0; index < 14; index++) await step(index + 1);
  let result = await audit();
  console.log("Original simulation reached sample 14; downloaded audit.");
  assert.ok(result.cases.length >= 1);
  assert.equal(result.cases[0].root_asset_id, "XFMR-1");
  const source = result.cloud_cases[result.cases[0].case_id]?.diagnosis?._source;
  if (live) assert.match(source, /^gemini:/);
  else {
    assert.equal(result.cases[0].decision, "AUTO_REMEDIATE");
    assert.equal(result.cases[0].status, "RESOLVED");
  }
  assert.equal(result.equipment_commands_sent, false);
  if (live) {
    await click("Save PRISM audit to BigQuery");
    await page.getByText(/Saved \d+ PRISM case summaries to BigQuery/).waitFor();
    await click("Refresh PRISM audit history");
  }
  for (const label of originalTabs) {
    await tab(label);
    await page.screenshot({ path: path.join(media, `prism-${live ? "cloud" : "local"}-${label.replace(/[^a-z]+/gi, "-").toLowerCase()}.png`) });
  }
  await tab("Models & Data");
  await expand("Replace telemetry / download original fleet fields");
  await click("Prepare PRISM telemetry templates");
  await expand("Replace telemetry / download original fleet fields");
  const data = JSON.parse(await download("Download PRISM fleet JSON"));
  console.log("Downloaded original fleet template.");
  assert.equal(data.assets.length, 22);
  assert.ok(data.assets.every(asset => ["id", "type", "name", "site", "rated_kw", "criticality", "parent_id"].every(key => key in asset)));
  const mapping = new Map(data.assets.map(asset => [asset.id, `USER-${asset.id}`]));
  for (const asset of data.assets) {
    asset.id = mapping.get(asset.id);
    if (asset.parent_id) asset.parent_id = mapping.get(asset.parent_id);
  }
  for (const reading of [...data.history, ...data.telemetry]) reading.asset_id = mapping.get(reading.asset_id);
  const payload = Buffer.from(JSON.stringify(data));
  assert.ok(payload.length < 2_000_000);
  await page.locator('input[type="file"]').setInputFiles({ name: "my-fleet.json", mimeType: "application/json", buffer: payload });
  await settled();
  console.log("Replacement fleet loaded.");
  await expand("Replace telemetry / download original fleet fields");
  if (live) {
    const consent = page.getByRole("checkbox", { name: "I authorize sending this uploaded telemetry to Vertex AI.", exact: true });
    await consent.focus();
    await page.keyboard.press("Space");
    await settled();
  }
  await click("Replace entire fleet");
  const replaced = await audit();
  assert.equal(replaced.source, "uploaded");
  assert.equal(replaced.summary.current_idx, -1);
  await tab("Live Operations");
  for (let index = 0; index < 14; index++) await step(index + 1);
  result = await audit();
  console.log("Uploaded fleet reached sample 14; downloaded audit.");
  assert.equal(result.source, "uploaded");
  assert.ok(result.cases.length >= 1);
  assert.ok(result.cases.every(item => item.root_asset_id.startsWith("USER-")));
  assert.ok(result.cases.every(item => item.decision === "ESCALATE" && item.status === "ESCALATED"));
  assert.ok(result.cases.every(item => item.cost_avoided_usd === 0));
  assert.equal(result.summary.diagnosis_accuracy, null);
  if (live) {
    assert.ok(Object.values(result.cloud_cases).some(item => item.diagnosis?._source.startsWith("gemini:")));
  }
  await page.screenshot({ path: path.join(media, live ? "prism-cloud-upload.png" : "prism-local-upload.png") });
  await tab("Models & Data");
  await expand("Replace telemetry / download original fleet fields");
  await page.locator('input[type="file"]').setInputFiles({
    name: "invalid-fleet.json", mimeType: "application/json", buffer: Buffer.from('{"assets":[],"history":[],"telemetry":[]}'),
  });
  await settled();
  await expand("Replace telemetry / download original fleet fields");
  await click("Replace entire fleet");
  await page.getByText(/Replacement rejected; existing fleet is unchanged/).waitFor();
  assert.equal((await audit()).run_id, result.run_id);
  await writeFile(path.join(media, live ? "prism-cloud-result.json" : "prism-local-result.json"), JSON.stringify({
    url, realGemini: live, originalTabs, originalFieldParity: true, replacementConfirmed: true,
    uploadObservationOnly: true, acceptedSource: source, cases: result.cases.map(item => ({
      asset: item.root_asset_id, decision: item.decision, status: item.status,
    })), testedAt: new Date().toISOString(),
  }, null, 2));
  console.log(JSON.stringify({ success: true, live, originalTabs: originalTabs.length,
    originalAssets: data.assets.length, source, uploadObservationOnly: true }));
} catch (error) {
  await page.screenshot({ path: path.join(media, live ? "prism-cloud-failure.png" : "prism-local-failure.png") });
  console.error((await page.locator('[data-testid="stException"]').allTextContents()).join("\n"));
  throw error;
} finally {
  const video = page.video();
  await context.close();
  if (video) console.log("Raw browser recording:", await video.path());
  await browser.close();
}

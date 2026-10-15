import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const media = path.join(here, "media");
await mkdir(media, { recursive: true });
const executable = [
  path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find(existsSync);
if (!executable) throw new Error("Chrome or Edge is required.");
const browser = await chromium.launch({ executablePath: executable, headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: media, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();
page.setDefaultTimeout(30_000);
const capture = async (name, locator) => {
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 90_000 });
  if (locator) await locator.last().evaluate(el => el.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(media, name) });
};
const run = async (asset) => {
  await page.getByRole("button", { name: "Run reliability loop", exact: true }).click();
  await page.getByRole("heading", { name: new RegExp(`^${asset} \\|`) }).waitFor({ timeout: 180_000 });
  await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 180_000 });
  for (let attempt = 0; attempt < 2; attempt++) {
    const retry = page.getByRole("button", { name: "Retry this incident", exact: true });
    if (!(await retry.count())) break;
    await retry.click();
    await page.waitForTimeout(1000);
    await page.getByRole("heading", { name: new RegExp(`^${asset} \\|`) }).waitFor({ timeout: 180_000 });
    await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 180_000 });
  }
  const errors = await page.locator('[data-testid="stAlert"]').allTextContents();
  if (errors.some(text => /Diagnosis unavailable|Audit persistence failed|Work order unavailable/.test(text))) {
    throw new Error(`Live ${asset} failed: ${errors.filter(text => /unavailable|failed/.test(text)).join("; ")}`);
  }
  if (!(await page.getByText(/^Source: gemini:/).count())) throw new Error("No accepted real Gemini diagnosis.");
};

try {
  await page.goto("https://aegis-ops-498775210896.asia-south1.run.app");
  await page.getByRole("button", { name: "Run reliability loop", exact: true }).waitFor();
  await capture("home.png");
  await run("MTR-07");
  const monitor = page.locator("summary").filter({ hasText: "1. Monitor" }).first();
  await monitor.click();
  await capture("motor-evidence.png", monitor);
  await capture("motor-diagnosis.png", page.locator("summary").filter({ hasText: "2. Diagnostician" }).first());
  const approve = page.getByRole("button", { name: "Approve sandbox simulation", exact: true });
  if (!(await approve.count())) throw new Error("Motor conservatively escalated; approval scene cannot be fabricated.");
  await page.getByRole("textbox", { name: "Reviewer name (demo alias allowed)" }).fill("Demo supervisor");
  await approve.click();
  await page.getByText("Sandbox approved by Demo supervisor. No real equipment action.", { exact: true }).waitFor();
  const verifier = page.locator("summary").filter({ hasText: "5. Verifier" }).first();
  await verifier.click();
  await capture("approval.png", verifier);
  await page.getByRole("button", { name: "Clear all", exact: true }).click();
  await page.getByRole("combobox", { name: "Synthetic incidents" }).click();
  await page.getByRole("option", { name: "PMP-03", exact: true }).click();
  await page.keyboard.press("Escape");
  await run("PMP-03");
  const actuator = page.locator("summary").filter({ hasText: "4. Actuator" }).first();
  await actuator.click();
  await page.getByText("Status: draft_for_review", { exact: true }).waitFor();
  await capture("pump-work-order.png", actuator);
  const history = page.locator("summary").filter({ hasText: "Operational audit history" }).last();
  await history.click();
  await page.getByRole("button", { name: "Refresh audit history", exact: true }).click();
  const historyPanel = page.locator("details").filter({ hasText: "Operational audit history" }).last();
  await historyPanel.locator('[data-testid="stDataFrame"]').waitFor({ state: "attached", timeout: 60_000 });
  if (!(await historyPanel.getAttribute("open"))) {
    await historyPanel.locator("summary").click();
  }
  await historyPanel.locator('[data-testid="stDataFrame"]').waitFor({ timeout: 60_000 });
  await page.getByRole("button", { name: "Stop", exact: true }).waitFor({ state: "hidden", timeout: 90_000 });
  const errors = await page.locator('[data-testid="stAlert"]').allTextContents();
  if (errors.some(text => /History query failed|Audit persistence failed/.test(text))) throw new Error("Audit verification failed.");
  await capture("audit-history.png", history);
  await writeFile(path.join(media, "capture-result.json"), JSON.stringify({
    realGemini: true, namedApproval: true, syntheticRecovery: true,
    engineerWorkOrder: true, auditHistory: true,
    note: "Two separate real live runs; all equipment data synthetic.",
  }, null, 2));
  console.log("Live motor approval, pump work order and BigQuery history verified and captured.");
} finally {
  const video = page.video();
  await context.close();
  if (video) console.log("Raw browser recording:", await video.path());
  await browser.close();
}

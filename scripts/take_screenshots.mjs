/**
 * Automated screenshot capture for README documentation.
 * Requires: npx playwright install chromium
 * Usage:    node scripts/take_screenshots.mjs
 */
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(__dirname, "..", "docs", "screenshots");
mkdirSync(OUT_DIR, { recursive: true });

const BASE = "http://localhost:3000";

const pages = [
  { name: "dashboard", path: "/", title: "Dashboard" },
  {
    name: "indicator-detail",
    path: "/indicators/ping",
    title: "Indicator Detail (Ping)",
  },
  { name: "devices", path: "/devices", title: "Devices" },
  { name: "comparison", path: "/comparison", title: "Comparison" },
  { name: "settings", path: "/settings", title: "Settings" },
];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });

  for (const page of pages) {
    const tab = await context.newPage();
    const url = `${BASE}${page.path}`;
    console.log(`Capturing: ${page.title} (${url})`);

    await tab.goto(url, { waitUntil: "networkidle" });
    // Extra wait for ECharts / async data
    await tab.waitForTimeout(2000);

    const filePath = resolve(OUT_DIR, `${page.name}.png`);
    await tab.screenshot({ path: filePath, fullPage: true });
    console.log(`  -> ${filePath}`);
    await tab.close();
  }

  await browser.close();
  console.log("\nDone! Screenshots saved to docs/screenshots/");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

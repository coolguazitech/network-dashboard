/**
 * NETORA Automated Screenshot Script
 *
 * Takes screenshots of all major pages with red-box annotations
 * for documentation (USER_AND_DEV_GUIDE.md + PPT_OUTLINE.md).
 */
import { chromium } from 'playwright';
import { mkdir } from 'fs/promises';
import { join } from 'path';

const BASE_URL = 'http://localhost:8000';
const SCREENSHOT_DIR = join(process.cwd(), 'docs', 'screenshots');
const VIEWPORT = { width: 1440, height: 900 };

const USERNAME = 'root';
const PASSWORD = 'admin123';

async function main() {
  await mkdir(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    locale: 'zh-TW',
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);

  // ── 1. Login page ──
  console.log('1/13 Login page...');
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input[placeholder="請輸入帳號"]', USERNAME);
  await page.fill('input[placeholder="請輸入密碼"]', PASSWORD);
  await addRedBox(page, 'input[placeholder="請輸入帳號"]');
  await addRedBox(page, 'input[placeholder="請輸入密碼"]');
  await addRedBox(page, 'button[type="submit"]');
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'login.png') });
  await clearRedBoxes(page);
  console.log('  ✓ login.png');

  // Actually log in
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(4000);

  // ── 2. Dashboard overview ──
  console.log('2/13 Dashboard overview...');
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'dashboard.png') });
  console.log('  ✓ dashboard.png');

  // ── 3. Dashboard full page with annotations ──
  console.log('3/13 Dashboard detail (full page)...');
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'dashboard_detail.png'), fullPage: true });
  console.log('  ✓ dashboard_detail.png');

  // ── 4. Threshold config modal ──
  console.log('4/13 Threshold config...');
  let thresholdCaptured = false;
  try {
    // Look for gear/config icon buttons (small icon buttons on indicator cards)
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const box = await btn.boundingBox();
      if (box && box.width < 45 && box.width > 15 && box.height < 45 && box.height > 15) {
        // Small button, likely an icon button
        const text = await btn.textContent();
        if (!text || text.trim().length <= 2) {
          await btn.click();
          await page.waitForTimeout(1500);
          const modal = await page.$('[class*="modal"], [role="dialog"], [class*="overlay"], [class*="fixed"]');
          if (modal) {
            const modalBox = await modal.boundingBox();
            if (modalBox && modalBox.width > 200) {
              await page.screenshot({ path: join(SCREENSHOT_DIR, 'threshold_config.png') });
              thresholdCaptured = true;
              await page.keyboard.press('Escape');
              await page.waitForTimeout(500);
              break;
            }
          }
          // If no modal, press Escape and continue
          await page.keyboard.press('Escape');
          await page.waitForTimeout(300);
        }
      }
    }
  } catch (e) { /* continue */ }
  if (!thresholdCaptured) {
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'threshold_config.png') });
  }
  console.log(`  ✓ threshold_config.png${thresholdCaptured ? '' : ' (fallback - no modal found)'}`);

  // ── 5. Comparison page ──
  console.log('5/13 Comparison...');
  await page.goto(`${BASE_URL}/comparison`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'comparison.png'), fullPage: true });
  console.log('  ✓ comparison.png');

  // ── 6. Devices page ──
  console.log('6/13 Devices...');
  await page.goto(`${BASE_URL}/devices`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'devices.png') });
  console.log('  ✓ devices.png');

  // ── 7. Client list (tab on Devices page) ──
  console.log('7/13 Client list...');
  const tabs = await page.$$('button, [role="tab"]');
  let clientTabClicked = false;
  for (const tab of tabs) {
    const text = await tab.textContent();
    if (text && (text.includes('Client') || text.includes('MAC') || text.includes('用戶端'))) {
      await tab.click();
      await page.waitForTimeout(2000);
      clientTabClicked = true;
      break;
    }
  }
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'client_list.png') });
  console.log(`  ✓ client_list.png${clientTabClicked ? '' : ' (fallback)'}`);

  // ── 8. Settings page ──
  console.log('8/13 Settings...');
  await page.goto(`${BASE_URL}/settings`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'settings.png') });
  console.log('  ✓ settings.png');

  // ── 9. Report preview ──
  console.log('9/13 Report preview...');
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  let reportCaptured = false;
  try {
    // Listen for popup (new tab for report)
    const popupPromise = context.waitForEvent('page', { timeout: 5000 });
    const btns = await page.$$('button');
    for (const btn of btns) {
      const text = await btn.textContent();
      if (text && (text.includes('匯出') || text.includes('報告') || text.includes('Report'))) {
        await btn.click();
        try {
          const reportPage = await popupPromise;
          await reportPage.waitForLoadState('networkidle');
          await reportPage.waitForTimeout(2000);
          await reportPage.screenshot({ path: join(SCREENSHOT_DIR, 'report_preview.png'), fullPage: true });
          reportCaptured = true;
          await reportPage.close();
        } catch (e) {
          // No popup, maybe it's a download or modal
          await page.waitForTimeout(2000);
          await page.screenshot({ path: join(SCREENSHOT_DIR, 'report_preview.png') });
          reportCaptured = true;
        }
        break;
      }
    }
  } catch (e) { /* continue */ }
  if (!reportCaptured) {
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'report_preview.png') });
  }
  console.log('  ✓ report_preview.png');

  // ── 10. Contacts page ──
  console.log('10/13 Contacts...');
  await page.goto(`${BASE_URL}/contacts`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'contacts.png') });
  console.log('  ✓ contacts.png');

  // ── 11. User management ──
  console.log('11/13 User management...');
  await page.goto(`${BASE_URL}/users`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'user_management.png') });
  console.log('  ✓ user_management.png');

  // ── 12. System logs ──
  console.log('12/13 System logs...');
  await page.goto(`${BASE_URL}/system-logs`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'system_logs.png') });
  console.log('  ✓ system_logs.png');

  // Expand a log entry for detail
  try {
    const firstRow = await page.$('tbody tr');
    if (firstRow) {
      await firstRow.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: join(SCREENSHOT_DIR, 'system_logs_detail.png') });
      console.log('  ✓ system_logs_detail.png');
    }
  } catch (e) { /* no log entries */ }

  // ── 13. Meal status sidebar ──
  console.log('13/13 Meal status...');
  await page.goto(`${BASE_URL}/`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  // Find and capture the meal status sidebar (it might be always visible or toggled)
  try {
    // Check if meal sidebar is visible
    const mealSidebar = await page.$('[class*="meal"]');
    if (mealSidebar) {
      await addRedBox(page, '[class*="meal"]');
    }
  } catch (e) { /* skip */ }
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'meal_status.png') });
  await clearRedBoxes(page);
  console.log('  ✓ meal_status.png');

  // ── Bonus: Indicator detail ──
  console.log('Bonus: Indicator detail...');
  await page.goto(`${BASE_URL}/indicators/transceiver`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: join(SCREENSHOT_DIR, 'indicator_detail.png'), fullPage: true });
  console.log('  ✓ indicator_detail.png');

  await browser.close();
  console.log('\n✅ All screenshots saved to docs/screenshots/');
}

async function addRedBox(page, selector) {
  try {
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (el) {
        el.setAttribute('data-redbox', 'true');
        el.style.outline = '3px solid #FF0000';
        el.style.outlineOffset = '3px';
      }
    }, selector);
  } catch (e) { /* skip */ }
}

async function clearRedBoxes(page) {
  try {
    await page.evaluate(() => {
      document.querySelectorAll('[data-redbox]').forEach(el => {
        el.style.outline = '';
        el.style.outlineOffset = '';
        el.removeAttribute('data-redbox');
      });
    });
  } catch (e) { /* skip */ }
}

main().catch(err => {
  console.error('Screenshot failed:', err);
  process.exit(1);
});

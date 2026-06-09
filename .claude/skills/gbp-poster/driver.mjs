import { chromium } from 'playwright';
import xlsx from 'xlsx';
import fs from 'fs';
import path from 'path';
import os from 'os';

const DEFAULT_CONFIG = 'C:\\Users\\carte\\.codex\\plugins\\grizzly-gbp-poster\\config.local.json';
const USER_DATA_DIR = path.join(os.homedir(), '.claude', 'gbp-session');

function parseArgs(argv) {
    const args = { dryRun: false, auth: false, headless: false, date: null, config: DEFAULT_CONFIG };
    for (let i = 0; i < argv.length; i += 1) {
        const arg = argv[i];
        if (arg === '--dry-run') args.dryRun = true;
        else if (arg === '--auth') args.auth = true;
        else if (arg === '--headless') args.headless = true;
        else if (arg === '--date') args.date = argv[++i];
        else if (arg.startsWith('--date=')) args.date = arg.slice('--date='.length);
        else if (arg === '--config') args.config = argv[++i];
        else if (arg.startsWith('--config=')) args.config = arg.slice('--config='.length);
    }
    args.date ||= new Date().toISOString().slice(0, 10);
    return args;
}

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function excelDateToIso(value) {
    if (value instanceof Date) return value.toISOString().slice(0, 10);
    if (typeof value === 'number') {
        const parsed = xlsx.SSF.parse_date_code(value);
        if (parsed) {
            return `${parsed.y}-${String(parsed.m).padStart(2, '0')}-${String(parsed.d).padStart(2, '0')}`;
        }
    }
    return String(value || '').slice(0, 10);
}

function parseSchedule(filePath, targetDate) {
    const workbook = xlsx.readFile(filePath);
    const sheetName = workbook.SheetNames.includes('Posts') ? 'Posts' : workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];
    const data = xlsx.utils.sheet_to_json(sheet, { defval: '' });
    const post = data.find((row) => excelDateToIso(row.Date || row.date) === targetDate);
    if (!post) throw new Error(`No post found for date: ${targetDate}`);
    return post;
}

function buildPayload(post) {
    const caption = String(post.CaptionDraft || post.Body || post.Caption || '').trim();
    const imagePath = String(post.AssetIdOrDescription || post['Related Picture'] || '').trim();
    return {
        date: excelDateToIso(post.Date || post.date),
        status: String(post.Status || '').trim(),
        topic: String(post.Topic || post.Title || '').trim(),
        caption,
        imagePath,
        posted: Boolean(post.Posted),
    };
}

async function clickFirst(page, selectors, label) {
    for (const selector of selectors) {
        const locator = page.locator(selector).first();
        if (await locator.count()) {
            await locator.click({ timeout: 10000 });
            return selector;
        }
    }
    throw new Error(`Could not find ${label}. Tried: ${selectors.join(', ')}`);
}

async function fillFirst(page, selectors, value, label) {
    for (const selector of selectors) {
        const locator = page.locator(selector).first();
        if (await locator.count()) {
            await locator.fill(value, { timeout: 10000 });
            return selector;
        }
    }
    throw new Error(`Could not find ${label}. Tried: ${selectors.join(', ')}`);
}

async function openUpdateComposer(page) {
    await page.goto('https://business.google.com/', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);

    const directAddUpdate = page.locator('button:has-text("Add update")').first();
    if (await directAddUpdate.count()) {
        await directAddUpdate.scrollIntoViewIfNeeded({ timeout: 10000 });
        await directAddUpdate.click({ timeout: 10000 });
    } else {
        await clickFirst(page, [
            'button:has-text("Posts")',
            'text="Posts"',
        ], 'posts button');
        await page.waitForTimeout(3000);
        await clickFirst(page, [
            'button:has-text("Add post")',
            'div[role="button"]:has-text("Add a post")',
            'button:has-text("Add update")',
            'text="Add post"',
        ], 'add post button');
    }

    await page.waitForURL(/promote\/updates\/add|#mpd=.*updates\/add/, { timeout: 15000 }).catch(() => {});
    await page.locator('text="Add post"').first().waitFor({ timeout: 15000 }).catch(() => {});
}

async function attachImage(page, imagePath) {
    const existingInput = page.locator('input[type="file"]').first();
    if (await existingInput.count()) {
        await existingInput.setInputFiles(imagePath, { timeout: 15000 });
        await page.waitForTimeout(3000);
        return;
    }
    const chooserPromise = page.waitForEvent('filechooser', { timeout: 15000 });
    const selectText = page.getByText('Select images and videos', { exact: true }).first();
    if (await selectText.count()) {
        await selectText.click({ timeout: 10000 });
    } else {
        await page.mouse.click(795, 355);
    }
    const chooser = await chooserPromise;
    await chooser.setFiles(imagePath);
    await page.waitForTimeout(3000);
}

async function fillComposerDescription(page, value) {
    const descriptionText = page.getByText('Description', { exact: true }).first();
    if (await descriptionText.count()) {
        await descriptionText.click({ timeout: 10000 });
    } else {
        await page.mouse.click(360, 230);
    }
    await page.keyboard.press('Control+A').catch(() => {});
    await page.keyboard.insertText(value);
    await page.waitForTimeout(500);
}

async function clickComposerPost(page) {
    const clicked = await page.evaluate(() => {
        const candidates = [...document.querySelectorAll('button')]
            .map((button) => ({ button, rect: button.getBoundingClientRect(), text: (button.innerText || button.textContent || '').trim() }))
            .filter(({ rect, text }) => text === 'Post' && rect.width > 0 && rect.height > 0 && rect.x > 500 && rect.y > 300);
        const target = candidates.sort((a, b) => b.rect.y - a.rect.y)[0]?.button;
        if (!target) return false;
        target.click();
        return true;
    });
    if (!clicked) {
        await page.mouse.click(935, 680);
    }
    await page.waitForTimeout(5000);
}

async function saveFailureArtifacts(page) {
    const outDir = 'C:\\Workspace\\Active\\SEO-Agents-App\\outputs\\gbp-debug';
    fs.mkdirSync(outDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const screenshot = path.join(outDir, `failure-${stamp}.png`);
    const textFile = path.join(outDir, `failure-${stamp}.json`);
    await page.screenshot({ path: screenshot, fullPage: true }).catch(() => {});
    const texts = await page.locator('a,button,div[role="button"],span,h1,h2,h3,textarea,[contenteditable="true"],input')
        .evaluateAll(nodes => [...new Set(nodes.map(n => (
            n.innerText || n.textContent || n.getAttribute('aria-label') || n.getAttribute('placeholder') || ''
        ).trim()).filter(Boolean).slice(0, 300))])
        .catch(() => []);
    fs.writeFileSync(textFile, JSON.stringify({ url: page.url(), texts }, null, 2));
    return { screenshot, textFile };
}

async function main() {
    const args = parseArgs(process.argv.slice(2));

    const config = readJson(args.config);

    if (args.auth) {
        const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
            headless: false,
            viewport: { width: 1365, height: 900 },
        });
        const page = await context.newPage();
        console.log('AUTH MODE: Log into Google Business Profile, then close this browser window.');
        await page.goto('https://business.google.com/', { waitUntil: 'domcontentloaded' });
        await page.waitForEvent('close', { timeout: 0 }).catch(() => {});
        await context.close();
        return;
    }

    const workbookPath = config.workbook_path;
    if (!workbookPath || !fs.existsSync(workbookPath)) {
        throw new Error(`Workbook not found: ${workbookPath || '(missing workbook_path)'}`);
    }

    const postData = parseSchedule(workbookPath, args.date);
    const payload = buildPayload(postData);
    if (!payload.caption) throw new Error(`Post ${args.date} has no caption/body text.`);
    if (payload.imagePath && !fs.existsSync(payload.imagePath)) {
        throw new Error(`Post image not found: ${payload.imagePath}`);
    }
    if (!args.dryRun && payload.status !== 'Approved') {
        throw new Error(`Post ${args.date} is not Approved. Current status: ${payload.status || '(blank)'}`);
    }
    if (!args.dryRun && payload.posted) {
        throw new Error(`Post ${args.date} is already marked Posted in the workbook.`);
    }

    const preview = {
        date: payload.date,
        status: payload.status,
        topic: payload.topic,
        caption_chars: payload.caption.length,
        image_path: payload.imagePath,
        image_exists: payload.imagePath ? fs.existsSync(payload.imagePath) : false,
        workbook_path: workbookPath,
    };
    console.log(JSON.stringify({ mode: args.dryRun ? 'dry-run' : 'live', payload: preview }, null, 2));

    if (args.dryRun) return;

    const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
        headless: args.headless,
        viewport: { width: 1280, height: 800 }
    });
    const page = await context.newPage();

    try {
        await openUpdateComposer(page);
        await fillComposerDescription(page, payload.caption);
        if (payload.imagePath) {
            await attachImage(page, payload.imagePath);
        }
        await clickComposerPost(page);
        console.log('Post successfully submitted to GBP.');
    } catch (e) {
        const artifacts = await saveFailureArtifacts(page);
        console.error('Error during GBP posting:', e.message || e);
        console.error(`Debug artifacts: ${JSON.stringify(artifacts)}`);
        process.exitCode = 1;
    } finally {
        await context.close();
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});

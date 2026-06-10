import { chromium } from 'playwright';
import xlsx from 'xlsx';
import fs from 'fs';
import path from 'path';
import os from 'os';

const DEFAULT_CONFIG = 'C:\\Users\\carte\\.codex\\plugins\\grizzly-gbp-poster\\config.local.json';
const USER_DATA_DIR = path.join(os.homedir(), '.claude', 'gbp-session');
const VIEWPORT = { width: 1365, height: 900 };

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

async function assertLoggedIn(page) {
    if (/accounts\.google\.com/.test(page.url())) {
        throw new Error('GBP session expired (redirected to Google sign-in). Re-authenticate with: node driver.mjs --auth');
    }
    const signIn = page.locator('a:has-text("Sign in"), button:has-text("Sign in")').first();
    if (await signIn.isVisible({ timeout: 1000 }).catch(() => false)) {
        throw new Error('GBP session is logged out (Sign in button visible). Re-authenticate with: node driver.mjs --auth');
    }
}

async function openUpdateComposer(page) {
    await page.goto('https://business.google.com/', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await assertLoggedIn(page);

    const directAddUpdate = page.locator('button:has-text("Add update")').first();
    const postsButton = page.locator('button:has-text("Posts"), text="Posts"').first();
    await directAddUpdate.or(postsButton).first().waitFor({ timeout: 20000 });

    if (await directAddUpdate.count()) {
        await directAddUpdate.scrollIntoViewIfNeeded({ timeout: 10000 });
        await directAddUpdate.click({ timeout: 10000 });
    } else {
        await clickFirst(page, [
            'button:has-text("Posts")',
            'text="Posts"',
        ], 'posts button');
        const addPost = page.locator(
            'button:has-text("Add post"), div[role="button"]:has-text("Add a post"), button:has-text("Add update")'
        ).first();
        await addPost.waitFor({ timeout: 15000 });
        await addPost.click({ timeout: 10000 });
    }

    // Composer is ready when the description surface exists.
    await composerInput(page).waitFor({ timeout: 20000 });
}

function composerInput(page) {
    return page.locator('div[role="dialog"] [contenteditable="true"], div[role="dialog"] textarea, [contenteditable="true"], textarea').first();
}

async function attachImage(page, imagePath) {
    const existingInput = page.locator('input[type="file"]').first();
    if (await existingInput.count()) {
        await existingInput.setInputFiles(imagePath, { timeout: 15000 });
    } else {
        const selectText = page.getByText('Select images and videos', { exact: true }).first();
        await selectText.waitFor({ timeout: 15000 });
        const chooserPromise = page.waitForEvent('filechooser', { timeout: 15000 });
        await selectText.click({ timeout: 10000 });
        const chooser = await chooserPromise;
        await chooser.setFiles(imagePath);
    }
    // Wait for the upload to render a thumbnail instead of sleeping blind.
    await page.locator('div[role="dialog"] img, img[src^="blob:"], img[src^="data:"]').first()
        .waitFor({ timeout: 30000 })
        .catch(() => {});
    await page.waitForTimeout(1500);
}

async function fillComposerDescription(page, value) {
    const input = composerInput(page);
    await input.waitFor({ timeout: 15000 });
    await input.click({ timeout: 10000 });
    await page.keyboard.press('Control+A').catch(() => {});
    await page.keyboard.insertText(value);
    // Confirm the text actually landed.
    const typed = (await input.innerText().catch(() => '')) || (await input.inputValue().catch(() => ''));
    if (!typed || !typed.includes(value.slice(0, 30))) {
        throw new Error('Caption text did not register in the composer description field.');
    }
}

async function clickComposerPost(page) {
    const dialog = page.locator('div[role="dialog"]').last();
    let postButton = dialog.getByRole('button', { name: 'Post', exact: true }).last();
    if (!(await postButton.count())) {
        postButton = page.getByRole('button', { name: 'Post', exact: true }).last();
    }
    if (!(await postButton.count())) {
        throw new Error('Could not find the Post submit button in the composer.');
    }
    await postButton.click({ timeout: 10000 });

    // The composer closing is the signal that GBP accepted the submission.
    await composerInput(page).waitFor({ state: 'hidden', timeout: 30000 });

    const errorBanner = page.locator('text=/something went wrong|couldn’t be posted|could not be posted|try again/i').first();
    if (await errorBanner.isVisible({ timeout: 1000 }).catch(() => false)) {
        throw new Error(`GBP showed an error after submitting: ${(await errorBanner.innerText().catch(() => '')).trim()}`);
    }
}

function captionSnippet(caption) {
    const firstLine = caption.split('\n').map((line) => line.trim()).find(Boolean) || caption;
    return firstLine.replace(/\s+/g, ' ').slice(0, 60).trim();
}

async function verifyPosted(page, caption) {
    const snippet = captionSnippet(caption);
    await page.goto('https://business.google.com/', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    const postsButton = page.locator('button:has-text("Posts"), text="Posts"').first();
    if (await postsButton.count()) {
        await postsButton.click({ timeout: 10000 }).catch(() => {});
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    }
    const match = page.getByText(snippet, { exact: false }).first();
    const visible = await match.isVisible({ timeout: 15000 }).catch(() => false);
    if (!visible) return { verified: false, postUrl: null };

    // Best-effort: pull a canonical post link near the matched card if one exists.
    const postUrl = await page.evaluate(() => {
        const anchor = [...document.querySelectorAll('a[href*="localPost"], a[href*="/posts/"]')][0];
        return anchor ? anchor.href : null;
    }).catch(() => null);
    return { verified: true, postUrl };
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

function emitResult(result) {
    console.log(JSON.stringify(result));
}

async function main() {
    const args = parseArgs(process.argv.slice(2));

    const config = readJson(args.config);

    if (args.auth) {
        const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
            headless: false,
            viewport: VIEWPORT,
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

    if (args.dryRun) {
        emitResult({ result: 'dry_run', date: payload.date, verified: false, postUrl: null });
        return;
    }

    const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
        headless: args.headless,
        viewport: VIEWPORT,
    });
    const page = await context.newPage();

    try {
        await openUpdateComposer(page);
        await fillComposerDescription(page, payload.caption);
        if (payload.imagePath) {
            await attachImage(page, payload.imagePath);
        }
        await clickComposerPost(page);
        const { verified, postUrl } = await verifyPosted(page, payload.caption);
        emitResult({ result: 'posted', date: payload.date, verified, postUrl });
        if (verified) {
            console.log('Post submitted and verified on GBP.');
        } else {
            console.error('Post was submitted (composer closed cleanly) but could not be verified in the Posts list. Check GBP manually before retrying — retrying may create a duplicate.');
            process.exitCode = 3;
        }
    } catch (e) {
        const artifacts = await saveFailureArtifacts(page);
        emitResult({ result: 'failed', date: payload.date, verified: false, postUrl: null, error: String(e.message || e) });
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

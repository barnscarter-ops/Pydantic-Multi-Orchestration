---
name: gbp-poster
description: Post daily updates to Google Business Profile from an Excel schedule. Handles image retrieval from Google Photos and uses a persistent browser session to bypass Google login.
---

# GBP Poster Skill

This skill automates approved Google Business Profile (GBP) posts from the shared Grizzly GBP workbook.

## Overview
The skill uses a Node.js Playwright driver that reads the shared workbook configured in the GBP poster config, uses local shared photo paths, and publishes through a persistent browser session. It does not use the Google Business Profile API.

**Driver Path:** `.claude/skills/gbp-poster/driver.mjs`
**Session Storage:** `C:\\Users\\carte\\.claude\\gbp-session\\`
**Default Config:** `C:\\Users\\carte\\.codex\\plugins\\grizzly-gbp-poster\\config.local.json`
**Workbook Source:** `workbook_path` from config, usually `C:\\Workspace\\Shared\\Operations\\Grizzly\\GBP\\Grizzly GBP Schedule.xlsx`

## Prerequisites

Install the required automation and parsing libraries:
```powershell
npm install playwright xlsx
npx playwright install chromium
```

## Setup: Initial Authentication
Google blocks automated logins. You must perform a one-time manual login to create the persistent session:

1. Run the driver in "auth" mode:
   ```powershell
   node C:\Users\carte\.claude\skills\gbp-poster\driver.mjs --auth
   ```
2. A browser window will open. Log into your Google Account and navigate to your Google Business Profile manager.
3. Once you are fully logged in and see your business dashboard, close the browser.
4. Your session is now saved in `.claude/gbp-session/`.

## Run: Agent Path (Daily Posting)

To dry-run a specific approved post:
```powershell
node C:\Users\carte\.claude\skills\gbp-poster\driver.mjs --date 2026-06-09 --dry-run
```

To execute the post for today's date after owner approval:
```powershell
node C:\Users\carte\.claude\skills\gbp-poster\driver.mjs
```

### Options
- `--dry-run`: Logs exactly what will be posted without opening a browser or clicking "Publish".
- `--date YYYY-MM-DD`: Post for a specific date instead of today.
- `--config <path>`: Use a specific GBP poster config JSON.
- `--headless`: Run without opening a visible browser window.

## Gotchas & Troubleshooting

- **Image Resolution:** The driver uses `AssetIdOrDescription` from the workbook as a local file path. If the image cannot be found, the post will be skipped.
- **Session Expiry:** If Google forces a password change or session logout, simply re-run the `--auth` command.
- **Selector Changes:** Google updates their UI frequently. If the driver fails to find the "Add Update" button, the `driver.mjs` selectors may need updating.
- **Excel Format:** The driver expects the shared `Posts` sheet with `Date`, `Status`, `Topic`, `CaptionDraft`, and `AssetIdOrDescription`.

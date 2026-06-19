#!/usr/bin/env pwsh
# build-win.ps1 — Builds the Orchestrator Windows installer without relying on
# electron-builder's electron extraction step (which fails on Windows Defender).
# Instead we assemble win-unpacked manually from the already-cached binary, then
# call electron-builder --prepackaged to produce the NSIS .exe.

$ErrorActionPreference = "Stop"

$FRONT          = $PSScriptRoot                # frontend/
$ROOT           = Split-Path $FRONT -Parent    # repo root
$OUT            = "$FRONT\dist-electron\win-unpacked"
$E_VERSION      = "31.7.7"
$ELECTRON_CACHE = "$env:LOCALAPPDATA\electron-builder\Cache\electron\electron-$E_VERSION-win32-x64"

Write-Host "`n=== 1/5  Vite build ===" -ForegroundColor Cyan
Set-Location $FRONT
npm run build

Write-Host "`n=== 2/5  Assemble win-unpacked ===" -ForegroundColor Cyan

# Clean previous output
if (Test-Path "$FRONT\dist-electron") {
    Remove-Item -Recurse -Force "$FRONT\dist-electron"
}
New-Item -ItemType Directory -Force $OUT | Out-Null

# Verify cache is present
if (-not (Test-Path "$ELECTRON_CACHE\electron.exe")) {
    Write-Error "Electron cache not found at $ELECTRON_CACHE — run `npm install` first."
    exit 1
}

# Copy electron binary from cache (already Defender-approved, no rename needed)
Copy-Item -Recurse -Force "$ELECTRON_CACHE\*" $OUT

# Rename electron.exe → Orchestrator.exe
Rename-Item "$OUT\electron.exe" "Orchestrator.exe" -Force

Write-Host "`n=== 3/5  Bundle app source ===" -ForegroundColor Cyan

$APP = "$OUT\resources\app"
New-Item -ItemType Directory -Force "$APP\electron" | Out-Null

# Copy electron main process files
Copy-Item -Recurse -Force "$FRONT\electron\*" "$APP\electron\"

# Write minimal package.json understood by Electron (CommonJS, correct main)
$pkgJson = @{
    name    = "orchestrator"
    version = "0.1.0"
    main    = "electron/main.js"
} | ConvertTo-Json -Depth 2
Set-Content -Path "$APP\package.json" -Value $pkgJson -Encoding UTF8

Write-Host "`n=== 4/5  Copy backend resources ===" -ForegroundColor Cyan

$BACKEND = "$OUT\resources\backend"
New-Item -ItemType Directory -Force $BACKEND | Out-Null

# Python source files
Get-ChildItem "$ROOT\*.py" | ForEach-Object { Copy-Item $_.FullName $BACKEND }

# requirements and .env (best-effort — .env may not exist in repo)
foreach ($f in @("requirements.txt", ".env")) {
    $src = "$ROOT\$f"
    if (Test-Path $src) { Copy-Item $src $BACKEND }
}

# Built frontend (served by FastAPI from the packaged backend)
$DIST_DST = "$BACKEND\frontend\dist"
New-Item -ItemType Directory -Force $DIST_DST | Out-Null
Copy-Item -Recurse -Force "$FRONT\dist\*" "$DIST_DST\"

Write-Host "`n=== 5/5  NSIS installer via electron-builder --prepackaged ===" -ForegroundColor Cyan

$EB = "node `"$FRONT\node_modules\electron-builder\out\cli\cli.js`""
$cmd = "$EB --win nsis --prepackaged `"$OUT`" --projectDir `"$FRONT`""
Write-Host "Running: $cmd"
Invoke-Expression $cmd

$installer = Get-ChildItem "$FRONT\dist-electron" -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($installer) {
    Write-Host "`nInstaller: $($installer.FullName)" -ForegroundColor Green
} else {
    Write-Host "`nNSIS step complete — check dist-electron/ for output." -ForegroundColor Yellow
}

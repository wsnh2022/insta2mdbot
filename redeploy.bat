@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set TOKEN_FILE=%~dp0.cloudflare-token

if not exist "!TOKEN_FILE!" (
    echo ERROR: .cloudflare-token file not found.
    echo.
    echo Create a file named .cloudflare-token in the project root
    echo and paste your Cloudflare API token as the only content.
    echo.
    pause >nul
    exit /b 1
)

set /p CLOUDFLARE_API_TOKEN=<"!TOKEN_FILE!"

if "!CLOUDFLARE_API_TOKEN!"=="" (
    echo ERROR: .cloudflare-token is empty.
    pause >nul
    exit /b 1
)

echo Deploying Cloudflare Worker...
echo.

cd /d "%~dp0worker"
npx wrangler deploy

echo.
echo ==============================
echo  Done. Press any key to close.
echo ==============================
pause >nul

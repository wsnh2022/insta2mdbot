@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set TOKEN_FILE=%~dp0.cloudflare-token
set LOG_FILE=%~dp0redeploy.log

if not exist "!TOKEN_FILE!" (
    echo ERROR: .cloudflare-token file not found.
    echo.
    echo Create a file named .cloudflare-token in the project root
    echo and paste your Cloudflare API token as the only content.
    echo.
    cmd /k
    exit /b 1
)

set /p CLOUDFLARE_API_TOKEN=<"!TOKEN_FILE!"

if "!CLOUDFLARE_API_TOKEN!"=="" (
    echo ERROR: .cloudflare-token is empty.
    cmd /k
    exit /b 1
)

echo Deploying Cloudflare Worker...
echo. > "!LOG_FILE!"
echo [%date% %time%] Deploying... >> "!LOG_FILE!"

cd /d "%~dp0worker"
npx wrangler deploy 2>&1 | tee "!LOG_FILE!"

echo.
echo Output saved to redeploy.log
echo Press any key to close...
pause >nul

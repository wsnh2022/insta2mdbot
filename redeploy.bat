@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set TOKEN_FILE=%~dp0.cloudflare-token

echo.
echo ===================================
echo  Cloudflare Worker - Redeploy
echo ===================================
echo.

:: Check .cloudflare-token exists
if not exist "!TOKEN_FILE!" (
    echo [FAIL] .cloudflare-token not found in project root.
    echo.
    echo  Create it and paste your Cloudflare API token as the only line.
    echo.
    goto :error
)

:: Read token
set /p CLOUDFLARE_API_TOKEN=<"!TOKEN_FILE!"
if "!CLOUDFLARE_API_TOKEN!"=="" (
    echo [FAIL] .cloudflare-token is empty.
    echo.
    goto :error
)

:: Check npx is available
where npx >nul 2>&1
if !errorlevel! neq 0 (
    echo [FAIL] npx not found. Is Node.js installed and on PATH?
    echo.
    echo  Download from: https://nodejs.org
    echo.
    goto :error
)

:: Deploy
echo [INFO] Deploying worker...
echo.
cd /d "%~dp0worker"
npx wrangler deploy
set DEPLOY_EXIT=!errorlevel!

echo.
if !DEPLOY_EXIT! equ 0 (
    echo ===================================
    echo  SUCCESS - Worker deployed.
    echo ===================================
) else (
    echo ===================================
    echo  FAILED - Exit code: !DEPLOY_EXIT!
    echo  Scroll up to read the error.
    echo ===================================
)

echo.
echo Press any key to close...
pause >nul
exit /b !DEPLOY_EXIT!

:error
echo Press any key to close...
pause >nul
exit /b 1

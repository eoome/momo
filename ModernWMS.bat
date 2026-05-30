@echo off
title ModernWMS

set ROOT=%~dp0
set FRONTEND=%ROOT%frontend
set BACKEND=%ROOT%backend
set PUBLISH=%ROOT%publish
set PORT=20011

:: ---- Check if already built ----
if exist "%PUBLISH%\backend\ModernWMS.dll" goto :START

:: ---- First time build ----
echo ========================================
echo   First run, building... (3-5 min)
echo ========================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Node.js not found & pause & exit /b 1 )
where dotnet >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] .NET 7 SDK not found & pause & exit /b 1 )
where yarn >nul 2>&1 || call npm install -g yarn

echo [1/3] Install frontend deps...
cd /d "%FRONTEND%" && call yarn
if %errorlevel% neq 0 ( echo [ERROR] yarn failed & pause & exit /b 1 )

echo [2/3] Build frontend...
cd /d "%FRONTEND%" && call npx vite build
if %errorlevel% neq 0 ( echo [ERROR] frontend build failed & pause & exit /b 1 )

echo [3/3] Build backend...
cd /d "%BACKEND%" && call dotnet publish ModernWMS\ModernWMS.csproj -c Release -o "%PUBLISH%\backend"
if %errorlevel% neq 0 ( echo [ERROR] backend build failed & pause & exit /b 1 )

xcopy /E /Y /Q "%FRONTEND%\dist\*" "%PUBLISH%\frontend\" >nul
if exist "%BACKEND%\ModernWMS\wms.db" copy /Y "%BACKEND%\ModernWMS\wms.db" "%PUBLISH%\backend\" >nul

echo.
echo   Build done! Next time will start directly.
echo ========================================

:: ---- Start ----
:START
taskkill /F /IM dotnet.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1

echo.
echo   Starting ModernWMS...
echo.

:: Start backend
cd /d "%PUBLISH%\backend"
start "ModernWMS-Backend" /MIN dotnet ModernWMS.dll --urls "http://0.0.0.0:%PORT%"

timeout /t 3 /nobreak >nul

:: Start frontend (node proxy)
cd /d "%ROOT%"
start "ModernWMS-Frontend" /MIN node server.js

timeout /t 2 /nobreak >nul

echo ========================================
echo   Ready!
echo   Browser: http://127.0.0.1
echo   Login:   admin / 1
echo.
echo   Close this window to stop.
echo ========================================

start http://127.0.0.1

:LOOP
timeout /t 5 /nobreak >nul
goto :LOOP

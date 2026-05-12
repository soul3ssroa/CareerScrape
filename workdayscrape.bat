@echo off
setlocal
cd /d "%~dp0"

if /i "%SCORCHED_USE_POSTGRES%"=="1" (
    if not defined POSTGRES_DB set "POSTGRES_DB=scorched_search"
    if not defined POSTGRES_USER set "POSTGRES_USER=postgres"
    if not defined POSTGRES_PASSWORD set "POSTGRES_PASSWORD=postgres"
    if not defined POSTGRES_HOST set "POSTGRES_HOST=localhost"
)

set PYTHON_EXE=
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo Could not find Python. Install Python, recreate .venv, or run from an activated environment.
    exit /b 1
)

"%PYTHON_EXE%" --version >nul 2>nul
if errorlevel 1 (
    echo Python exists but cannot run: "%PYTHON_EXE%"
    echo Your .venv appears to point at the broken Windows Store Python shim.
    echo Install Python from python.org, then recreate the venv:
    echo   rmdir /s /q .venv
    echo   py -3.11 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install django selenium webdriver-manager psycopg2-binary
    exit /b 1
)

"%PYTHON_EXE%" manage.py migrate
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" manage.py scrape_jobs --interval 43200%*

"%PYTHON_EXE%" manage.py cleanup_jobs --duplicates %*

"%PYTHON_EXE%" manage.py cleanup_jobs --older-than-days 21%*




@echo off
title YouTube Downloader - Install Dependencies
echo Installing YouTube Downloader Dependencies...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found. Installing dependencies...
echo.

REM Install yt-dlp
echo Installing yt-dlp...
pip install yt-dlp
if errorlevel 1 (
    echo Failed to install yt-dlp. Trying with --user flag...
    pip install --user yt-dlp
    if errorlevel 1 (
        echo Failed to install yt-dlp. Please run as administrator or check your internet connection.
        pause
        exit /b 1
    )
)

echo.
echo Dependencies installed successfully!
echo You can now run the application with: python youtube_downloader.py
echo.
pause 
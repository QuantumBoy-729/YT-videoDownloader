param(
    [string]$Version = "1.0.3"
)

$ErrorActionPreference = 'Stop'

Write-Host "=== Building YouTubeDownloader $Version (cx_Freeze) ===" -ForegroundColor Cyan

# 1) Create venv and install deps
if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt cx-Freeze

# 2) Build EXE and MSI with cx_Freeze
Write-Host "Building EXE and MSI with cx_Freeze..." -ForegroundColor Cyan
try {
    python setup_cx_final.py build_exe bdist_msi
    Write-Host "\nSuccess! Output:" -ForegroundColor Green
    Write-Host "- EXE: build\exe.win-amd64-3.x\YouTubeDownloader.exe" -ForegroundColor Yellow
    Write-Host "- MSI: build\bdist\YouTubeDownloader.msi" -ForegroundColor Yellow
    
    # Copy the MSI to current directory with version
    if (Test-Path "build\bdist\YouTubeDownloader.msi") {
        Copy-Item "build\bdist\YouTubeDownloader.msi" "YouTubeDownloader-$Version-cx.msi"
        Write-Host "- MSI (copied): YouTubeDownloader-$Version-cx.msi" -ForegroundColor Green
    }
} catch {
    Write-Host "cx_Freeze build failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "\nFalling back to PyInstaller..." -ForegroundColor Yellow
    
    # Fallback to PyInstaller
    python -m pip install pyinstaller
    pyinstaller --name YouTubeDownloader --windowed --onefile youtube_downloader.py
    Write-Host "\nPyInstaller EXE created: dist\YouTubeDownloader.exe" -ForegroundColor Yellow
} 
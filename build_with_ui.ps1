param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = 'Stop'

Write-Host "=== Building YouTubeDownloader $Version (with UI) ===" -ForegroundColor Cyan

# 1) Create venv and install deps
if (-not (Test-Path .venv)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

# 2) Build exe with PyInstaller
Write-Host "Building EXE with PyInstaller..." -ForegroundColor Cyan
pyinstaller --name YouTubeDownloader --windowed --onefile youtube_downloader.py

# 3) Try to find WiX tools
$wixPaths = @(
    "C:\Program Files (x86)\WiX Toolset v3.14\bin",
    "C:\Program Files\WiX Toolset v3.14\bin",
    "C:\Program Files (x86)\WiX Toolset v3.13\bin",
    "C:\Program Files\WiX Toolset v3.13\bin"
)

$wixBinPath = $null
foreach ($path in $wixPaths) {
    if (Test-Path $path) {
        $wixBinPath = $path
        break
    }
}

if ($wixBinPath) {
    Write-Host "Found WiX at: $wixBinPath" -ForegroundColor Green
    $env:PATH = "$wixBinPath;$env:PATH"
    
    # Use the UI WiX file
    $wxsMain = "installer\product_with_ui.wxs"
    if (Test-Path $wxsMain -PathType Leaf) {
        try {
            # Harvest files from dist into a component group
            Write-Host "Harvesting files from dist..." -ForegroundColor Cyan
            $distDir = Join-Path (Get-Location) "dist"
            if (Test-Path $distDir) {
                & "$wixBinPath\heat.exe" dir "$distDir" -cg AppFiles -dr INSTALLDIR -srd -gg -sfrag -var var.DistDir -out installer\files.wxs
                
                # Compile WiX
                Write-Host "Compiling WiX..." -ForegroundColor Cyan
                & "$wixBinPath\candle.exe" -dVersion=$Version -dDistDir="$distDir" -o installer\ installer\product_with_ui.wxs installer\files.wxs
                
                # Link MSI
                Write-Host "Linking MSI..." -ForegroundColor Cyan
                & "$wixBinPath\light.exe" installer\product_with_ui.wixobj installer\files.wixobj -o "YouTubeDownloader-$Version-UI.msi"
                
                if (Test-Path "YouTubeDownloader-$Version-UI.msi") {
                    Write-Host "\nSuccess! Output: YouTubeDownloader-$Version-UI.msi" -ForegroundColor Green
                    Write-Host "File size: $((Get-Item 'YouTubeDownloader-$Version-UI.msi').Length / 1MB) MB" -ForegroundColor Yellow
                } else {
                    Write-Host "MSI creation failed" -ForegroundColor Red
                }
                exit 0
            }
        } catch {
            Write-Host "WiX build failed: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host "WiX build failed or not available" -ForegroundColor Yellow
Write-Host "You can still use the PyInstaller EXE: dist\YouTubeDownloader.exe" -ForegroundColor Cyan 
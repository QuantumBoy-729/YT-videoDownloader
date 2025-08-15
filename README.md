# YouTube Downloader

A simple and user-friendly YouTube downloader application with a graphical user interface built using Python and Tkinter.

## Features

- **Easy-to-use GUI**: Clean and intuitive interface
- **Multiple formats**: Download videos in MP4, WebM, or extract audio as MP3
- **Quality selection**: Choose from various quality options (144p to 1080p or best available)
- **Custom download location**: Select where to save your downloads
- **Real-time progress**: See download progress and logs in real-time
- **Automatic dependency management**: Automatically installs yt-dlp if not present
- **Professional installer**: MSI installer built with WiX and PyInstaller

## Requirements

- Python 3.6 or higher
- Internet connection

## Installation

1. **Install Python**: If you don't have Python installed, download and install it from [python.org](https://www.python.org/downloads/). Make sure to check "Add Python to PATH" during installation.

2. **Clone or download this repository**:
   ```bash
   git clone <repository-url>
   cd youtube-downloader
   ```

3. **Install dependencies** (optional - the app will auto-install yt-dlp):
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Run the application**:
   ```bash
   python youtube_downloader.py
   ```

2. **Using the interface**:
   - Paste a YouTube URL in the "YouTube URL" field
   - Select your preferred format (MP4, MP3, WebM)
   - Choose video quality (144p to 1080p, or "best" for highest available)
   - Select download location or use the default Downloads folder
   - Click "Download" to start the download

3. **Monitor progress**:
   - Watch the status updates in the status bar
   - View detailed logs in the log area at the bottom
   - The progress bar shows download activity

## Building the Installer

To build the MSI installer:

```powershell
.\build_final.ps1 -Version 1.0.0
```

This will create:
- `dist\YouTubeDownloader.exe` - Standalone executable
- `YouTubeDownloader-1.0.0.msi` - Professional Windows installer

## Supported URLs

The app supports:
- Individual YouTube videos
- YouTube Shorts
- Most YouTube video formats

## File Naming

Downloaded files are automatically named using the video title and appropriate file extension.

## Troubleshooting

### Python not found
If you get "Python was not found" error:
1. Install Python from [python.org](https://www.python.org/downloads/)
2. Make sure to check "Add Python to PATH" during installation
3. Restart your command prompt/terminal

### yt-dlp installation fails
If automatic yt-dlp installation fails:
1. Open command prompt as administrator
2. Run: `pip install yt-dlp`
3. Restart the application

### Download fails
- Check your internet connection
- Verify the YouTube URL is correct and accessible
- Some videos may be geo-restricted or have download limitations
- Check the log area for detailed error messages

## Legal Notice

This tool is for personal use only. Please respect YouTube's Terms of Service and copyright laws. Only download content that you have permission to download.

## Technical Details

- **Backend**: yt-dlp (modern fork of youtube-dl)
- **GUI**: Python Tkinter
- **Threading**: Uses separate threads for downloads to keep UI responsive
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Build tools**: PyInstaller for EXE, WiX for MSI installer

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve this application.

## License

This project is open source. Please check the license file for details.

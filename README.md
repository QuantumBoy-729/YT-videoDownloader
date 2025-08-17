# YouTube Downloader with Download Controls

A professional YouTube downloader application with **pause/resume/stop** functionality and a modern graphical interface built using Python and Tkinter.

## 🚀 **READY TO USE - Single File Executable Available!**

**Download the ready-to-use executable:** [`YouTubeDownloader-Single.exe`](./YouTubeDownloader-Single.exe) (21.3 MB)
- ✅ **Zero dependencies** - No Python installation required
- ✅ **Copy & Run** - Works on any Windows machine
- ✅ **Complete features** - All download controls included

## 🎯 Enhanced Features

- **🎮 Download Controls**: Pause, Resume, and Stop downloads mid-process
- **📊 Real-time Progress**: Live progress bars and status updates
- **🎯 Smart State Management**: Intelligent button enabling/disabling
- **🖥️ Easy-to-use GUI**: Clean and intuitive interface with modern controls
- **📺 Multiple formats**: Download videos in MP4, WebM, or extract audio as MP3
- **🎬 Quality selection**: Choose from various quality options (144p to 1080p or best available)
- **📁 Custom download location**: Select where to save your downloads
- **⚡ Real-time feedback**: See download progress and logs in real-time
- **🔧 Automatic dependency management**: Automatically installs yt-dlp if not present
- **📦 Professional distribution**: Both MSI installer and single-file executable

## 🚀 Quick Start Options

### Option 1: Ready-to-Use Executable (Recommended)
1. **Download**: [`YouTubeDownloader-Single.exe`](./YouTubeDownloader-Single.exe) (21.3 MB)
2. **Run**: Double-click the executable - that's it!
3. **No installation required** - works on any Windows machine

### Option 2: Run from Source
**Requirements:**
- Python 3.6 or higher
- Internet connection

**Installation:**
1. **Install Python**: Download from [python.org](https://www.python.org/downloads/)
2. **Clone this repository**:
   ```bash
   git clone https://github.com/QuantumBoy-729/YT-videoDownloader.git
   cd YT-videoDownloader
   ```
3. **Install dependencies** (optional - auto-installed):
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 Usage

### Using the Executable
1. **Download** the [`YouTubeDownloader-Single.exe`](./YouTubeDownloader-Single.exe)
2. **Double-click** to launch the application
3. **Enter** a YouTube URL and start downloading!

### Running from Source
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

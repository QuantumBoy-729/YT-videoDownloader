"""
PyInstaller setup script for YouTube Downloader
Creates a true single-file standalone executable
"""
import PyInstaller.__main__
import sys
import os
import certifi

def build_single_exe():
    """Build a single-file executable using PyInstaller"""
    
    # Get the certificate bundle path
    cert_bundle = certifi.where()
    
    # PyInstaller arguments for single-file build
    args = [
        'youtube_downloader.py',
        '--onefile',  # Create single executable file
        '--windowed',  # Hide console window (for GUI)
        '--name=YouTubeDownloader-Single',
        '--icon=icon.ico' if os.path.exists('icon.ico') else '--noconfirm',
        
        # Include SSL certificates
        f'--add-data={cert_bundle};.',
        
        # Include yt-dlp and dependencies
        '--hidden-import=yt_dlp',
        '--hidden-import=yt_dlp.extractor',
        '--hidden-import=yt_dlp.downloader',
        '--hidden-import=yt_dlp.postprocessor',
        
        # Include tkinter modules
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.scrolledtext',
        
        # Include other required modules
        '--hidden-import=threading',
        '--hidden-import=queue',
        '--hidden-import=signal',
        '--hidden-import=subprocess',
        '--hidden-import=pathlib',
        '--hidden-import=json',
        '--hidden-import=ssl',
        '--hidden-import=certifi',
        '--hidden-import=urllib3',
        '--hidden-import=requests',
        
        # Output directory
        '--distpath=build/single',
        '--workpath=build/work',
        '--specpath=build/specs',
        
        # Clean previous builds
        '--clean',
        '--noconfirm',
        
        # Optimize
        '--optimize=2',
    ]
    
    print("Building single-file executable with PyInstaller...")
    print("This may take several minutes...")
    
    # Run PyInstaller
    PyInstaller.__main__.run(args)
    
    print("\n" + "="*60)
    print("BUILD COMPLETE!")
    print("="*60)
    print(f"Single executable created at: build/single/YouTubeDownloader-Single.exe")
    print(f"File size: ~50-100MB (includes Python runtime and all dependencies)")
    print("\nThis is a TRUE single-file executable:")
    print("- No external dependencies required")
    print("- Can be copied and run on any Windows machine")
    print("- Includes Python runtime, yt-dlp, and SSL certificates")
    print("="*60)

if __name__ == "__main__":
    build_single_exe()

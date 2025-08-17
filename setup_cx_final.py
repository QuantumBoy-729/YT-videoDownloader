"""
cx_Freeze setup script for YouTube Downloader
Builds both EXE and MSI installer
"""
import sys
import os
from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["tkinter", "pathlib", "subprocess", "threading", "json", "yt_dlp"],
    "excludes": [],
    "include_files": [],
    "include_msvcr": True,
}

# GUI applications require a different base on Windows
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# MSI options
bdist_msi_options = {
    'add_to_path': False,
    'initial_target_dir': r'[ProgramFilesFolder]\YouTubeDownloader',
    'target_name': 'YouTubeDownloader.msi',
    'data': {
        'Shortcut': [
            ('DesktopShortcut',        # Shortcut
             'DesktopFolder',          # Directory_
             'YouTube Downloader',     # Name
             'TARGETDIR',              # Component_
             '[TARGETDIR]YouTubeDownloader.exe',  # Target
             None,                     # Arguments
             None,                     # Description
             None,                     # Hotkey
             None,                     # Icon
             None,                     # IconIndex
             None,                     # ShowCmd
             'TARGETDIR'               # WkDir
             ),
            ('StartMenuShortcut',      # Shortcut
             'ProgramMenuFolder',      # Directory_
             'YouTube Downloader',     # Name
             'TARGETDIR',              # Component_
             '[TARGETDIR]YouTubeDownloader.exe',  # Target
             None,                     # Arguments
             None,                     # Description
             None,                     # Hotkey
             None,                     # Icon
             None,                     # IconIndex
             None,                     # ShowCmd
             'TARGETDIR'               # WkDir
             )
        ]
    }
}

setup(
    name="YouTubeDownloader",
    version="1.0.3",
    description="YouTube Downloader Application",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options
    },
    executables=[
        Executable(
            "youtube_downloader.py",
            base=base,
            target_name="YouTubeDownloader.exe",
            shortcut_name="YouTube Downloader",
            shortcut_dir="DesktopFolder"
        )
    ]
) 
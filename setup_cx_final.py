"""
cx_Freeze setup script for YouTube Downloader
Builds both EXE and MSI installer with SSL certificate support
"""
import sys
import os
import certifi
from cx_Freeze import setup, Executable

# Get version from main file
def get_version():
    try:
        with open("youtube_downloader.py", "r", encoding="utf-8") as f:
            content = f.read()
            # Look for version in various common patterns
            import re
            patterns = [
                r'version\s*=\s*["\']([^"\']+)["\']',
                r'__version__\s*=\s*["\']([^"\']+)["\']',
                r'VERSION\s*=\s*["\']([^"\']+)["\']'
            ]
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return "1.0.3"

VERSION = get_version()

# Enhanced standalone configuration with SSL certificates
build_exe_options = {
    "packages": [
        # Core packages that we know work
        "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "tkinter.scrolledtext",
        "pathlib", "subprocess", "threading", "json", "sys", "os", "re",
        "yt_dlp",  # Main yt-dlp package will auto-include its dependencies
        # SSL and certificate packages
        "ssl", "certifi", "urllib3", "requests",
    ],
    "excludes": [
        # Remove test and development packages to reduce size
        "test", "tests", "unittest", "distutils", "setuptools", "pip", "wheel",
        "pytest", "coverage", "tox", "mypy", "black", "flake8",
        # Remove heavy scientific packages we don't need
        "numpy", "matplotlib", "scipy", "pandas", "sklearn", "tensorflow", "torch",
        # Remove development tools
        "IPython", "jupyter", "notebook", "sphinx", "docutils"
    ],
    "include_files": [
        # Include SSL certificate bundle for HTTPS connections
        (certifi.where(), "lib/cacert.pem"),
        # Include any additional configuration files if needed
    ],
    "include_msvcr": True,
    "optimize": 2,  # Maximum bytecode optimization
    "build_exe": "build/standalone",  # Separate standalone build directory
    "silent": False,  # Show build progress
}

# GUI applications require a different base on Windows
base = None
if sys.platform == "win32":
    base = "Win32GUI"

# MSI options with enhanced completion message
bdist_msi_options = {
    'add_to_path': False,
    'initial_target_dir': r'[ProgramFilesFolder]\YouTubeDownloader',
    'target_name': f'YouTubeDownloader-{VERSION}.msi',
    'summary_data': {
        'author': 'QuantumBoy-729',
        'comments': 'YouTube Downloader with support for 1000+ sites including HiAnime.to',
        'keywords': 'YouTube, video, downloader, HiAnime'
    },
    'data': {
        'Property': [
            ('ARPPRODUCTICON', 'icon.ico'),
            ('ARPHELPLINK', 'https://github.com/QuantumBoy-729/YT-videoDownloader'),
            ('ARPURLINFOABOUT', 'https://github.com/QuantumBoy-729/YT-videoDownloader'),
            ('WIXUI_EXITDIALOGOPTIONALTEXT', 
             'Thank you for installing YouTube Downloader! You can now download videos from YouTube, HiAnime.to, and 1000+ other sites with support for multiple formats and quality options including 4K.'),
        ],
        'Shortcut': [
            ('DesktopShortcut',        # Shortcut
             'DesktopFolder',          # Directory_
             'YouTube Downloader',     # Name
             'TARGETDIR',              # Component_
             '[TARGETDIR]YouTubeDownloader.exe',  # Target
             None,                     # Arguments
             'Download videos from YouTube, HiAnime.to, and 1000+ sites',  # Description
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
             'Download videos from YouTube, HiAnime.to, and 1000+ sites',  # Description
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
    version=VERSION,
    description="YouTube Downloader Application - Download from YouTube, HiAnime.to, and 1000+ sites",
    author="QuantumBoy-729",
    url="https://github.com/QuantumBoy-729/YT-videoDownloader",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options
    },
    executables=[
        Executable(
            "youtube_downloader.py",
            base=base,
            target_name="YouTubeDownloader-Standalone.exe",
            shortcut_name="YouTube Downloader Standalone",
            shortcut_dir="DesktopFolder",
            copyright="Copyright (C) 2025 QuantumBoy-729",
            # Add icon and metadata for professional appearance
            uac_admin=False,  # No admin rights needed
            # Embed everything into the executable
        )
    ]
) 
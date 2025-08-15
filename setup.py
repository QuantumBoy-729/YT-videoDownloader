"""
Setup script for YouTube Downloader
"""
import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    requirements = [
        'yt-dlp>=2023.7.6'
    ]
    
    print("Installing YouTube Downloader dependencies...")
    print("=" * 50)
    
    for package in requirements:
        try:
            print(f"Installing {package}...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', package], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ {package} installed successfully")
            else:
                print(f"✗ Failed to install {package}: {result.stderr}")
                return False
        except Exception as e:
            print(f"✗ Error installing {package}: {str(e)}")
            return False
    
    print("\n" + "=" * 50)
    print("✓ All dependencies installed successfully!")
    print("You can now run the application with: python youtube_downloader.py")
    return True

if __name__ == "__main__":
    print("YouTube Downloader Setup")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 6):
        print("✗ Python 3.6 or higher is required")
        sys.exit(1)
    
    print(f"✓ Python {sys.version} detected")
    
    # Install requirements
    if install_requirements():
        print("\nSetup completed successfully!")
        input("Press Enter to exit...")
    else:
        print("\nSetup failed. Please check the error messages above.")
        input("Press Enter to exit...")
        sys.exit(1)

"""
Test script for YouTube Downloader
Tests basic functionality without requiring GUI interaction
"""
import sys
import subprocess
import importlib.util

def test_imports():
    """Test if required modules can be imported"""
    print("Testing imports...")
    
    try:
        import tkinter as tk
        print("✓ tkinter imported successfully")
    except ImportError:
        print("✗ tkinter import failed - GUI won't work")
        return False
    
    try:
        from pathlib import Path
        print("✓ pathlib imported successfully")
    except ImportError:
        print("✗ pathlib import failed")
        return False
    
    return True

def test_yt_dlp():
    """Test if yt-dlp is available or can be installed"""
    print("\nTesting yt-dlp availability...")
    
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print(f"✓ yt-dlp is available: {result.stdout.strip()}")
            return True
        else:
            print("yt-dlp not found, testing installation...")
            return test_yt_dlp_install()
    except Exception as e:
        print("yt-dlp not found, testing installation...")
        return test_yt_dlp_install()

def test_yt_dlp_install():
    """Test yt-dlp installation"""
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ yt-dlp installed successfully")
            return True
        else:
            print(f"✗ yt-dlp installation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Error installing yt-dlp: {str(e)}")
        return False

def test_app_import():
    """Test if the main application can be imported"""
    print("\nTesting main application import...")
    
    try:
        spec = importlib.util.spec_from_file_location("youtube_downloader", "youtube_downloader.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("✓ Main application imports successfully")
        return True
    except Exception as e:
        print(f"✗ Main application import failed: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("YouTube Downloader - Test Suite")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 6):
        print("✗ Python 3.6 or higher is required")
        return False
    
    print(f"✓ Python {sys.version} is compatible")
    
    # Run tests
    tests = [
        test_imports,
        test_yt_dlp,
        test_app_import
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"Test failed: {test.__name__}")
    
    print("\n" + "=" * 50)
    print(f"Tests passed: {passed}/{len(tests)}")
    
    if passed == len(tests):
        print("✓ All tests passed! The application should work correctly.")
        print("\nTo run the application:")
        print("1. Double-click 'run_app.bat' (Windows)")
        print("2. Or run: python youtube_downloader.py")
    else:
        print("✗ Some tests failed. Please check the error messages above.")
    
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    input("\nPress Enter to exit...")
    sys.exit(0 if success else 1)

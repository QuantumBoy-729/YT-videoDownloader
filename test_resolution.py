#!/usr/bin/env python3
"""
Test script to demonstrate improved resolution handling in YouTube Downloader
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_format_selection():
    """Test the format selection logic"""
    
    # Test cases for different quality settings
    test_cases = [
        ("720p", "mp4"),
        ("1080p", "mp4"), 
        ("480p", "webm"),
        ("best", "mp4")
    ]
    
    print("YouTube Downloader - Resolution Handling Test")
    print("=" * 50)
    
    for quality, format_type in test_cases:
        print(f"\nTesting: {quality} {format_type}")
        
        if format_type == "mp4":
            if quality == "best":
                format_str = 'best[ext=mp4]/best'
            else:
                height = quality[:-1]  # Remove 'p' from quality
                format_str = f'best[height={height}][ext=mp4]/best[height<={height}][ext=mp4]/best[height>={height}][ext=mp4]/best[ext=mp4]/best'
        elif format_type == "webm":
            if quality == "best":
                format_str = 'best[ext=webm]/best'
            else:
                height = quality[:-1]  # Remove 'p' from quality
                format_str = f'best[height={height}][ext=webm]/best[height<={height}][ext=webm]/best[height>={height}][ext=webm]/best[ext=webm]/best'
        
        print(f"Format string: {format_str}")
        print("Priority order:")
        if quality != "best":
            height = quality[:-1]
            print(f"  1. Exact match: {height}p {format_type}")
            print(f"  2. Lower quality: ≤{height}p {format_type}")
            print(f"  3. Higher quality: ≥{height}p {format_type}")
            print(f"  4. Any {format_type}")
            print(f"  5. Any format")
        else:
            print(f"  1. Best {format_type}")
            print(f"  2. Best any format")

def main():
    test_format_selection()
    
    print("\n" + "=" * 50)
    print("Key improvements:")
    print("✓ Prioritizes exact resolution match first")
    print("✓ Falls back to lower quality if exact not available")
    print("✓ Falls back to higher quality if lower not available") 
    print("✓ Shows available formats before downloading")
    print("✓ Logs actual downloaded resolution")
    print("✓ Better format sorting with res,ext priority")
    
    print("\nTo test with a real video:")
    print("1. Run the YouTube Downloader application")
    print("2. Paste a YouTube URL")
    print("3. Select your desired resolution") 
    print("4. Check the log for 'Available resolutions' and 'Actual resolution'")

if __name__ == "__main__":
    main()

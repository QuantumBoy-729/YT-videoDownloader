import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
import subprocess
import json
from pathlib import Path

# Configure SSL certificates for standalone executable
def setup_ssl_for_standalone():
    """Configure SSL certificates for standalone executable"""
    if getattr(sys, 'frozen', False):
        # We're running as a frozen executable
        executable_dir = Path(sys.executable).parent
        cacert_path = executable_dir / 'lib' / 'cacert.pem'
        
        if cacert_path.exists():
            # Set environment variables for SSL certificate verification
            os.environ['SSL_CERT_FILE'] = str(cacert_path)
            os.environ['REQUESTS_CA_BUNDLE'] = str(cacert_path)
            os.environ['CURL_CA_BUNDLE'] = str(cacert_path)
            print(f"SSL certificates configured: {cacert_path}")
        else:
            print(f"Warning: SSL certificate bundle not found at {cacert_path}")

# Initialize SSL configuration
setup_ssl_for_standalone()

class YouTubeDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        # Variables
        self.download_path = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.url_var = tk.StringVar()
        self.format_var = tk.StringVar(value="mp4")
        self.quality_var = tk.StringVar(value="720p")
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # URL input
        ttk.Label(main_frame, text="Video URL:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=50)
        url_entry.grid(row=0, column=1, sticky="we", pady=(0, 5), padx=(10, 0))
        
        # Supported sites info
        sites_label = ttk.Label(main_frame, text="Supports: YouTube, HiAnime.to, and 1000+ other sites", 
                               font=("TkDefaultFont", 8), foreground="gray")
        sites_label.grid(row=1, column=1, sticky="w", padx=(10, 0))
        
        # Format selection
        format_frame = ttk.Frame(main_frame)
        format_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=5)
        
        ttk.Label(format_frame, text="Format:").pack(side=tk.LEFT)
        format_combo = ttk.Combobox(format_frame, textvariable=self.format_var, values=["mp4", "mp3", "webm"], state="readonly", width=10)
        format_combo.pack(side=tk.LEFT, padx=(10, 20))
        
        ttk.Label(format_frame, text="Quality:").pack(side=tk.LEFT)
        quality_combo = ttk.Combobox(format_frame, textvariable=self.quality_var,
                                     values=["144p", "240p", "360p", "480p", "720p", "1080p", "best"],
                                     state="readonly", width=10)
        quality_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Download path
        path_frame = ttk.Frame(main_frame)
        path_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=5)
        path_frame.columnconfigure(0, weight=1)
        
        ttk.Label(main_frame, text="Download Path:").grid(row=3, column=0, sticky=tk.W, pady=5)
        path_entry = ttk.Entry(main_frame, textvariable=self.download_path, width=40)
        path_entry.grid(row=4, column=0, columnspan=2, sticky="we", pady=(0, 5))
        
        browse_btn = ttk.Button(main_frame, text="Browse", command=self.browse_folder)
        browse_btn.grid(row=5, column=1, sticky=tk.E, pady=(0, 10))
        
        # Download button
        self.download_btn = ttk.Button(main_frame, text="Download", command=self.start_download)
        self.download_btn.grid(row=6, column=0, columnspan=2, pady=10)
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, text="Status:").grid(row=7, column=0, sticky=tk.W, pady=(10, 0))
        self.status_label = ttk.Label(main_frame, textvariable=self.progress_var)
        self.status_label.grid(row=7, column=1, sticky=tk.W, pady=(10, 0), padx=(10, 0))
        
        self.progress_bar = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress_bar.grid(row=8, column=0, columnspan=2, sticky="we", pady=5)
        
        # Log area
        ttk.Label(main_frame, text="Log:").grid(row=9, column=0, sticky=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(main_frame, height=10, width=70)
        self.log_text.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        
        # Configure row weight for log area to expand
        main_frame.rowconfigure(10, weight=1)
        
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path.get())
        if folder:
            self.download_path.set(folder)
    
    def log_message(self, message):
        """Add message to log area"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def get_ytdlp_path(self):
        """Return path to yt-dlp executable if bundled, otherwise command name.
        Prefers a local yt-dlp.exe next to the executable (for frozen builds).
        """
        try:
            candidates = []
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
                candidates.append(app_dir / 'yt-dlp.exe')
                temp_dir = getattr(sys, '_MEIPASS', None)
                if temp_dir:
                    candidates.append(Path(temp_dir) / 'yt-dlp.exe')
            else:
                script_dir = Path(__file__).resolve().parent
                candidates.append(script_dir / 'yt-dlp.exe')
            for c in candidates:
                if c.exists():
                    return str(c)
        except Exception:
            pass
        
        # For frozen executables, try to use yt-dlp as a module through the bundled Python
        if getattr(sys, 'frozen', False):
            try:
                import yt_dlp
                # In frozen apps, use the current executable with -m yt_dlp
                return [sys.executable, '-c', 'import yt_dlp; yt_dlp.main()']
            except ImportError:
                pass
        else:
            # For non-frozen apps, check if we're in a virtual environment and yt-dlp is available as a module
            try:
                import yt_dlp
                # If yt-dlp is available as a module, use Python -m yt_dlp
                return [sys.executable, '-m', 'yt_dlp']
            except ImportError:
                pass
            
        return 'yt-dlp'
    
    def check_dependencies(self):
        """Check if yt-dlp is installed"""
        try:
            # First try importing yt-dlp module (preferred for frozen executables)
            import yt_dlp
            self.log_message(f"yt-dlp module available (version: {yt_dlp.version.__version__})")
            return True
        except ImportError:
            pass
        
        # Fallback to checking command-line version
        try:
            ytdlp_cmd = self.get_ytdlp_path()
            if isinstance(ytdlp_cmd, list):
                cmd = ytdlp_cmd + ['--version']
            else:
                cmd = [ytdlp_cmd, '--version']
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.log_message(f"yt-dlp version: {result.stdout.strip()}")
                return True
            else:
                return False
        except Exception as e:
            return False
    
    def install_ytdlp(self):
        """Install yt-dlp using pip"""
        try:
            self.log_message("Installing yt-dlp...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                self.log_message("yt-dlp installed successfully!")
                return True
            else:
                self.log_message(f"Failed to install yt-dlp: {result.stderr}")
                return False
        except Exception as e:
            self.log_message(f"Error installing yt-dlp: {str(e)}")
            return False
    
    def start_download(self):
        """Start download in a separate thread"""
        if not self.url_var.get().strip():
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return
            
        # Disable download button
        self.download_btn.config(state="disabled")
        self.progress_bar.start()
        self.progress_var.set("Downloading...")
        
        # Start download thread
        thread = threading.Thread(target=self.download_video)
        thread.daemon = True
        thread.start()
    
    def get_best_format_for_quality(self, url, format_type, quality):
        """Get the best format ID that matches the requested quality"""
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'listformats': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                
                if quality == "best":
                    # For best quality, target 4K (2160p) and find the closest available resolution
                    target_height = 2160  # 4K resolution as benchmark for "best"
                    best_format = None
                    closest_height = 0
                    closest_diff = float('inf')
                    
                    self.log_message(f"Looking for best quality (targeting {target_height}p - 4K)")
                    
                    # First, try to find formats with the preferred extension
                    for fmt in formats:
                        height = fmt.get('height', 0)
                        if (fmt.get('ext') == format_type and 
                            height > 0 and
                            fmt.get('vcodec') != 'none'):  # Has video
                            
                            # Calculate difference from target (4K)
                            diff = abs(height - target_height)
                            
                            # Prefer formats closer to 4K, but if equal distance, prefer higher resolution
                            if (diff < closest_diff or 
                                (diff == closest_diff and height > closest_height)):
                                best_format = fmt['format_id']
                                closest_height = height
                                closest_diff = diff
                                self.log_message(f"Found {format_type} format: {fmt['format_id']} ({height}p)")
                    
                    # If no format found with preferred extension, find the best available format
                    if not best_format:
                        self.log_message(f"No {format_type} format found, looking for best available format")
                        closest_diff = float('inf')  # Reset for second search
                        
                        for fmt in formats:
                            height = fmt.get('height', 0)
                            if (height > 0 and
                                fmt.get('vcodec') != 'none' and  # Has video
                                fmt.get('ext') in ['mp4', 'webm', 'mkv', 'avi']):  # Common video formats
                                
                                # Calculate difference from target (4K)
                                diff = abs(height - target_height)
                                
                                # Prefer formats closer to 4K, but if equal distance, prefer higher resolution
                                if (diff < closest_diff or 
                                    (diff == closest_diff and height > closest_height)):
                                    best_format = fmt['format_id']
                                    closest_height = height
                                    closest_diff = diff
                                    self.log_message(f"Found format: {fmt['format_id']} ({height}p)")
                    
                    if best_format:
                        self.log_message(f"Selected best format: {best_format} ({closest_height}p) - closest to 4K target")
                    else:
                        self.log_message("No suitable video format found for 'best' quality")
                    
                    return best_format
                else:
                    # For specific quality, find exact match or closest
                    target_height = int(quality[:-1])
                    exact_match = None
                    closest_match = None
                    closest_diff = float('inf')
                    
                    for fmt in formats:
                        if (fmt.get('ext') == format_type and 
                            fmt.get('height') and
                            fmt.get('vcodec') != 'none'):  # Has video
                            
                            height = fmt['height']
                            
                            # Check for exact match
                            if height == target_height:
                                exact_match = fmt['format_id']
                                self.log_message(f"Found exact match: {fmt['format_id']} ({height}p)")
                                break
                            
                            # Check for closest match
                            diff = abs(height - target_height)
                            if diff < closest_diff:
                                closest_diff = diff
                                closest_match = fmt['format_id']
                    
                    if exact_match:
                        return exact_match
                    elif closest_match:
                        self.log_message(f"No exact match found, using closest: {closest_match}")
                        return closest_match
                    
        except Exception as e:
            self.log_message(f"Error finding best format: {str(e)}")
        
        return None

    def check_available_formats(self, url):
        """Check available formats for the given URL"""
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                
                available_resolutions = set()
                for fmt in formats:
                    if fmt.get('height') and fmt.get('ext') in ['mp4', 'webm'] and fmt.get('vcodec') != 'none':
                        available_resolutions.add(f"{fmt['height']}p")
                
                return sorted(available_resolutions, key=lambda x: int(x[:-1]), reverse=True)
        except Exception as e:
            self.log_message(f"Could not fetch available formats: {str(e)}")
            return []
    
    def download_video(self):
        """Download video using yt-dlp"""
        try:
            # Check if yt-dlp is available
            if not self.check_dependencies():
                self.log_message("yt-dlp not found. Attempting to install...")
                if not self.install_ytdlp():
                    self.progress_var.set("Error: Could not install yt-dlp")
                    return
            
            url = self.url_var.get().strip()
            format_type = self.format_var.get()
            quality = self.quality_var.get()
            download_path = self.download_path.get()
            
            # Detect site type
            if "hianime.to" in url or "9anime" in url:
                self.log_message("Detected HiAnime URL - using hianime extractor plugin")
                self.progress_var.set("Connecting to HiAnime...")
            else:
                self.log_message("Detected standard video URL")
            
            # Check available formats first
            self.log_message("Checking available formats...")
            self.progress_var.set("Checking available formats...")
            available_formats = self.check_available_formats(url)
            if available_formats:
                self.log_message(f"Available resolutions: {', '.join(available_formats)}")
                if quality != "best" and quality not in available_formats:
                    self.log_message(f"Warning: Requested {quality} not available. Will try closest match.")
            
            # Try to use yt-dlp directly as a Python module (better for frozen executables)
            try:
                import yt_dlp
                self.log_message("Using yt-dlp Python module directly")
                self.download_with_ytdlp_module(url, format_type, quality, download_path)
                return
            except ImportError:
                self.log_message("yt-dlp module not available, falling back to subprocess")
            
            # Fallback to subprocess method
            self.download_with_subprocess(url, format_type, quality, download_path)
            
        except Exception as e:
            self.progress_var.set("Error occurred!")
            self.log_message(f"Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        
        finally:
            # Re-enable download button and stop progress bar
            self.root.after(0, self.reset_ui)
    
    def download_with_ytdlp_module(self, url, format_type, quality, download_path):
        """Download using yt-dlp module directly"""
        import yt_dlp
        
        # Build yt-dlp options
        ydl_opts = {
            'outtmpl': f'{download_path}/%(title)s.%(ext)s',
        }
        
        # Set format based on selection with improved logic
        if format_type == "mp3":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            })
        elif format_type in ["mp4", "webm"]:
            if quality == "best":
                # Use our custom format selection for best quality
                best_format_id = self.get_best_format_for_quality(url, format_type, quality)
                if best_format_id:
                    ydl_opts['format'] = best_format_id
                    self.log_message(f"Using specific format ID for best quality: {best_format_id}")
                else:
                    # Fallback to generic best with multiple options
                    format_options = [
                        f'best[ext={format_type}]',  # Best in preferred format
                        'best[height>=720]',         # At least 720p
                        'best',                      # Absolute best available
                    ]
                    ydl_opts['format'] = '/'.join(format_options)
                    self.log_message(f"Using fallback format selection for best quality")
            else:
                height = quality[:-1]  # Remove 'p' from quality
                
                # More aggressive format selection to get the right resolution
                format_options = [
                    f'best[height={height}][ext={format_type}]',  # Exact match with format
                    f'best[height={height}]',                     # Exact match any format
                    f'bestvideo[height={height}]+bestaudio/best[height={height}]',  # Separate video+audio
                    f'best[height<={int(height)+50}][height>={int(height)-50}][ext={format_type}]',  # Close range with format
                    f'best[height<={int(height)+50}][height>={int(height)-50}]',  # Close range any format
                    f'best[ext={format_type}]',                   # Best in format
                    'best'                                        # Absolute fallback
                ]
                
                ydl_opts['format'] = '/'.join(format_options)
        
        # Force format sorting to prioritize resolution
        if quality != "best":
            ydl_opts['format_sort'] = [f'res:{quality[:-1]}', 'ext']
        else:
            ydl_opts['format_sort'] = ['res', 'ext']
        
        # Add verbose format selection to see what's happening
        ydl_opts['listformats'] = False
        
        # Custom progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    percent = d.get('_percent_str', 'N/A')
                    speed = d.get('_speed_str', 'N/A')
                    self.log_message(f"Downloading... {percent} at {speed}")
                    self.progress_var.set(f"Downloading... {percent}")
                except:
                    self.log_message("Downloading...")
                    self.progress_var.set("Downloading...")
            elif d['status'] == 'finished':
                filename = d.get('filename', 'Unknown')
                self.log_message(f"Downloaded: {filename}")
                self.progress_var.set("Processing...")
        
        ydl_opts['progress_hooks'] = [progress_hook]
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            self.log_message(f"Starting download: {url}")
            self.log_message(f"Requested quality: {quality}")
            self.log_message(f"Format selector: {ydl_opts.get('format', 'default')}")
            
            # First, get detailed format information
            try:
                self.log_message("Fetching video information...")
                info = ydl.extract_info(url, download=False)
                
                if 'formats' in info:
                    self.log_message("Available formats:")
                    relevant_formats = []
                    for fmt in info['formats']:
                        if fmt.get('height') and fmt.get('ext') in ['mp4', 'webm', 'm4a', 'webm']:
                            format_info = f"  {fmt.get('format_id', 'unknown')}: {fmt['height']}p ({fmt['ext']}) - {fmt.get('filesize_approx', 'unknown size')}"
                            if fmt.get('vcodec') != 'none':  # Has video
                                relevant_formats.append(format_info)
                                self.log_message(format_info)
                    
                    # Check if our requested resolution is actually available
                    if quality != "best":
                        height = int(quality[:-1])
                        available_heights = [f.get('height') for f in info['formats'] if f.get('height')]
                        closest_height = min(available_heights, key=lambda x: abs(x - height)) if available_heights else None
                        if closest_height:
                            self.log_message(f"Closest available to {quality}: {closest_height}p")
                            
                            # If the closest is significantly different, warn the user
                            if abs(closest_height - height) > 100:
                                self.log_message(f"WARNING: Large difference between requested ({height}p) and available ({closest_height}p)")
                
                # Perform the actual download
                self.log_message("Starting actual download...")
                info = ydl.extract_info(url, download=True)
                
                # Log the actual format that was selected
                if 'format' in info:
                    actual_height = info.get('height', 'unknown')
                    actual_width = info.get('width', 'unknown')
                    actual_ext = info.get('ext', 'unknown')
                    self.log_message(f"✓ Successfully downloaded: {actual_width}x{actual_height} ({actual_ext})")
                
            except Exception as e:
                self.log_message(f"Error during info extraction: {str(e)}")
                # Fallback to direct download
                ydl.download([url])
            
            self.log_message("Download completed successfully!")
            self.progress_var.set("Download completed successfully!")
            messagebox.showinfo("Success", "Video downloaded successfully!")
    
    def download_with_subprocess(self, url, format_type, quality, download_path):
        """Download using yt-dlp subprocess (fallback method)"""
        # Build yt-dlp command
        ytdlp_path = self.get_ytdlp_path()
        if isinstance(ytdlp_path, list):
            cmd = ytdlp_path.copy()
        else:
            cmd = [ytdlp_path]
        
        # Set format based on selection with improved logic
        if format_type == "mp3":
            cmd.extend(['-x', '--audio-format', 'mp3'])
        elif format_type in ["mp4", "webm"]:
            if quality == "best":
                # Try to get specific format ID for best quality
                try:
                    best_format_id = self.get_best_format_for_quality(url, format_type, quality)
                    if best_format_id:
                        cmd.extend(['-f', best_format_id])
                        self.log_message(f"Using specific format ID for best quality: {best_format_id}")
                    else:
                        # Fallback to format selection string
                        format_options = [
                            f'best[ext={format_type}]',  # Best in preferred format
                            'best[height>=720]',         # At least 720p
                            'best',                      # Absolute best available
                        ]
                        format_str = '/'.join(format_options)
                        cmd.extend(['-f', format_str])
                        self.log_message("Using fallback format selection for best quality")
                except Exception as e:
                    self.log_message(f"Error getting best format ID: {str(e)}, using fallback")
                    cmd.extend(['-f', f'best[ext={format_type}]/best[height>=720]/best'])
            else:
                height = quality[:-1]  # Remove 'p' from quality
                
                # More aggressive format selection to get the right resolution
                format_options = [
                    f'best[height={height}][ext={format_type}]',  # Exact match with format
                    f'best[height={height}]',                     # Exact match any format
                    f'bestvideo[height={height}]+bestaudio/best[height={height}]',  # Separate video+audio
                    f'best[height<={int(height)+50}][height>={int(height)-50}][ext={format_type}]',  # Close range with format
                    f'best[height<={int(height)+50}][height>={int(height)-50}]',  # Close range any format
                    f'best[ext={format_type}]',                   # Best in format
                    'best'                                        # Absolute fallback
                ]
                
                format_str = '/'.join(format_options)
                cmd.extend(['-f', format_str])
        
        # Add format sorting and verbose output
        cmd.extend(['--format-sort', f'res:{quality[:-1]}' if quality != "best" else 'res'])
        cmd.extend(['--print', 'Selected format: %(format_id)s - %(width)sx%(height)s (%(ext)s)'])
        
        # Set output directory
        cmd.extend(['-o', f'{download_path}/%(title)s.%(ext)s'])
        
        # Add URL
        cmd.append(url)
        
        self.log_message(f"Executing: {' '.join(cmd)}")
        self.log_message(f"Requested quality: {quality}")
        
        # Execute download
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                     text=True, universal_newlines=True)
            
            # Read output in real-time
            if process.stdout:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_message(line)
                        # Look for format selection information
                        if 'Selected format:' in line:
                            self.log_message(f"✓ {line}")
            
            process.wait()
        except FileNotFoundError:
            self.log_message("Error: yt-dlp command not found. Please ensure yt-dlp is installed.")
            self.progress_var.set("Error: yt-dlp not found")
            return
        except Exception as e:
            self.log_message(f"Error executing yt-dlp: {str(e)}")
            self.progress_var.set("Error executing command")
            return
        
        if process.returncode == 0:
            self.progress_var.set("Download completed successfully!")
            self.log_message("Download completed successfully!")
            messagebox.showinfo("Success", "Video downloaded successfully!")
        else:
            self.progress_var.set("Download failed!")
            self.log_message("Download failed!")
            messagebox.showerror("Error", "Download failed. Check the log for details.")
    
    def reset_ui(self):
        """Reset UI elements after download"""
        self.download_btn.config(state="normal")
        self.progress_bar.stop()

def main():
    root = tk.Tk()
    app = YouTubeDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

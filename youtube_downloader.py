import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
import subprocess
import json
from pathlib import Path

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
        ttk.Label(main_frame, text="YouTube URL:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        url_entry = ttk.Entry(main_frame, textvariable=self.url_var, width=50)
        url_entry.grid(row=0, column=1, sticky="we", pady=(0, 5), padx=(10, 0))
        
        # Format selection
        format_frame = ttk.Frame(main_frame)
        format_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=5)
        
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
        path_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=5)
        path_frame.columnconfigure(0, weight=1)
        
        ttk.Label(main_frame, text="Download Path:").grid(row=2, column=0, sticky=tk.W, pady=5)
        path_entry = ttk.Entry(main_frame, textvariable=self.download_path, width=40)
        path_entry.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 5))
        
        browse_btn = ttk.Button(main_frame, text="Browse", command=self.browse_folder)
        browse_btn.grid(row=4, column=1, sticky=tk.E, pady=(0, 10))
        
        # Download button
        self.download_btn = ttk.Button(main_frame, text="Download", command=self.start_download)
        self.download_btn.grid(row=5, column=0, columnspan=2, pady=10)
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, text="Status:").grid(row=6, column=0, sticky=tk.W, pady=(10, 0))
        self.status_label = ttk.Label(main_frame, textvariable=self.progress_var)
        self.status_label.grid(row=6, column=1, sticky=tk.W, pady=(10, 0), padx=(10, 0))
        
        self.progress_bar = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress_bar.grid(row=7, column=0, columnspan=2, sticky="we", pady=5)
        
        # Log area
        ttk.Label(main_frame, text="Log:").grid(row=8, column=0, sticky=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(main_frame, height=10, width=70)
        self.log_text.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        
        # Configure row weight for log area to expand
        main_frame.rowconfigure(9, weight=1)
        
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
        return 'yt-dlp'
    
    def check_dependencies(self):
        """Check if yt-dlp is installed"""
        try:
            result = subprocess.run([self.get_ytdlp_path(), '--version'], capture_output=True, text=True)
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
            
            # Build yt-dlp command
            cmd = [self.get_ytdlp_path()]
            
            # Set format based on selection
            if format_type == "mp3":
                cmd.extend(['-x', '--audio-format', 'mp3'])
            elif format_type == "mp4":
                if quality == "best":
                    cmd.extend(['-f', 'best[ext=mp4]/best'])
                else:
                    height = quality[:-1]  # Remove 'p' from quality
                    cmd.extend(['-f', f'best[height<={height}][ext=mp4]/best[height<={height}]/best'])
            elif format_type == "webm":
                if quality == "best":
                    cmd.extend(['-f', 'best[ext=webm]/best'])
                else:
                    height = quality[:-1]  # Remove 'p' from quality
                    cmd.extend(['-f', f'best[ext=webm][height<={height}]/best[height<={height}]/best'])
            
            # Set output directory
            cmd.extend(['-o', f'{download_path}/%(title)s.%(ext)s'])
            
            # Add URL
            cmd.append(url)
            
            self.log_message(f"Executing: {' '.join(cmd)}")
            
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
                
        except Exception as e:
            self.progress_var.set("Error occurred!")
            self.log_message(f"Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        
        finally:
            # Re-enable download button and stop progress bar
            self.root.after(0, self.reset_ui)
    
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

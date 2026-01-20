
import os
import time
import json
import subprocess
import threading
from pynput import mouse
from audio_recorder import AudioRecorder
from utils.locale_manager import locale_manager
from utils.path_utils import get_ffmpeg_path

class FFmpegRecordEngine:
    """
    High performance recording engine using FFmpeg for video and system audio capture.
    """
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        
        # Parameters (mirrors RecordEngine)
        self.zoom_max = 1.3
        self.smooth_speed = 0.15
        self.zoom_duration = 1.0
        self.fps = 30.0
        self.output_file = ""
        self.save_path = ""
        self.video_quality = "medium"
        self.audio_mode = AudioRecorder.MODE_NONE
        
        self.system_volume = 1.0
        self.mic_volume = 2.0
        self.record_region = None
        
        # Audio components
        self.audio_recorder = None
        self.audio_file = ""
        
        # Internal state
        self.start_time = None
        self.click_log = []
        self.click_log_file = ""
        self.video_temp = ""
        self.ffmpeg_process = None
        self.mouse_listener = None
        self.log_lock = threading.Lock()
        
    def on_click(self, x, y, button, pressed):
        if pressed and self.is_running and not self.is_paused and self.start_time is not None:
            with self.log_lock:
                timestamp = time.time() - self.start_time
                
                # Normalize coordinates if recording a region
                eff_x = int(x)
                eff_y = int(y)
                if self.record_region:
                    eff_x -= self.record_region.get('left', 0)
                    eff_y -= self.record_region.get('top', 0)
                
                self.click_log.append({
                    "time": timestamp,
                    "x": eff_x,
                    "y": eff_y,
                    "button": str(button),
                    "type": "click"
                })

    def on_move(self, x, y):
        if self.is_running and not self.is_paused and self.start_time is not None:
             with self.log_lock:
                timestamp = time.time() - self.start_time
                
                # Normalize coordinates if recording a region
                eff_x = int(x)
                eff_y = int(y)
                if self.record_region:
                    eff_x -= self.record_region.get('left', 0)
                    eff_y -= self.record_region.get('top', 0)

                self.click_log.append({
                    "time": timestamp,
                    "x": eff_x,
                    "y": eff_y,
                    "type": "move"
                })

    def run(self):
        """Start the recording process"""
        self.is_running = True
        self.is_paused = False
        timestamp = int(time.time())
        
        # Prepare file paths
        filename = f"Record_{timestamp}.mp4"
        if self.save_path and os.path.exists(self.save_path):
            self.output_file = os.path.join(self.save_path, filename)
        else:
            self.output_file = filename
            
        self.video_temp = self.output_file.replace(".mp4", "_raw.mkv")
        self.click_log_file = self.output_file.replace(".mp4", "_clicks.json")
        
        # Audio Setup
        if self.audio_mode != AudioRecorder.MODE_NONE:
            self.audio_file = self.output_file.replace(".mp4", "_audio.wav")
            self.audio_recorder = AudioRecorder(
                mode=self.audio_mode,
                sample_rate=48000,
                system_volume=self.system_volume,
                mic_volume=self.mic_volume
            )
            if not self.audio_recorder.start_recording(self.audio_file):
                print(locale_manager.get_text("log_audio_start_fail"))
                self.audio_mode = AudioRecorder.MODE_NONE

        # Start mouse listener (monitor both click and move)
        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_move=self.on_move)
        self.mouse_listener.start()
        
        # Start FFmpeg
        ffmpeg_cmd = self._build_ffmpeg_command()
        print(f"Starting FFmpeg: {' '.join(ffmpeg_cmd)}")
        
        try:
            # Creation flags for Windows to hide console window
            creationflags = 0
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
                
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                creationflags=creationflags
            )
            
            # Record start time for sync
            # Give FFmpeg a moment to initialize
            time.sleep(0.5) 
            self.start_time = time.time()
            
            # Record initial mouse position at time 0
            try:
                import pyautogui
                init_x, init_y = pyautogui.position()
                eff_x = int(init_x)
                eff_y = int(init_y)
                if self.record_region:
                    eff_x -= self.record_region.get('left', 0)
                    eff_y -= self.record_region.get('top', 0)
                
                with self.log_lock:
                    self.click_log.append({
                        "time": 0.0,
                        "x": eff_x,
                        "y": eff_y,
                        "type": "move"
                    })
            except Exception as e:
                print(f"Failed to record initial mouse position: {e}")

            if self.audio_recorder:
                self.audio_recorder.set_start_time()
            
            # Main loop to monitor process and handle pause
            while self.is_running:
                if self.ffmpeg_process.poll() is not None:
                    print("FFmpeg process exited unexpectedly")
                    self.is_running = False
                    break
                
                # If paused, we effectively just wait. 
                # FFmpeg continues recording, but we might mark this period in logs or pause it?
                # Pausing FFmpeg is tricky (suspend process). 
                # For high perf mode, maybe we just don't support pause for now 
                # OR we implement it by sending 'pause' command if supported, 
                # but gdigrab usually doesn't support interactive commands well.
                # EASIEST: Just don't log clicks while paused. The video will be continuous.
                # If user wants to cut the pause, they can do it in post.
                # But to keep consistent with UI, let's just sleep.
                
                time.sleep(0.1)

        except Exception as e:
            print(f"Error running FFmpeg: {e}")
        finally:
            self.cleanup()

    def _build_ffmpeg_command(self):
        ffmpeg_path = get_ffmpeg_path()
        cmd = [ffmpeg_path]
        
        # Input: GDI Grab
        cmd.extend(['-f', 'gdigrab'])
        cmd.extend(['-draw_mouse', '0'])
        cmd.extend(['-framerate', str(int(self.fps))])
        
        if self.record_region:
            # Region recording
            # Ensure width/height are even for x264
            w = self.record_region['width']
            h = self.record_region['height']
            x = self.record_region['left']
            y = self.record_region['top']
            
            w = w if w % 2 == 0 else w - 1
            h = h if h % 2 == 0 else h - 1
            
            cmd.extend(['-offset_x', str(x)])
            cmd.extend(['-offset_y', str(y)])
            cmd.extend(['-video_size', f"{w}x{h}"])
        
        cmd.extend(['-i', 'desktop'])
        
        # Encoding
        cmd.extend(['-c:v', 'libx264'])
        cmd.extend(['-preset', 'ultrafast'])
        cmd.extend(['-crf', '0']) # Lossless for intermediate
        
        # Output
        cmd.extend(['-y', self.video_temp])
        
        return cmd

    def stop(self):
        self.is_running = False

    def cleanup(self):
        if self.mouse_listener:
            self.mouse_listener.stop()
            
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            # Terminate FFmpeg gracefully to finalize file
            # Send 'q' to stdin
            try:
                self.ffmpeg_process.stdin.write(b'q')
                self.ffmpeg_process.stdin.flush()
                # Give it more time to finalize (especially for larger files or slower systems)
                self.ffmpeg_process.wait(timeout=5)
            except Exception as e:
                print(f"Graceful stop failed: {e}")
                # Force kill if graceful stop fails
                try:
                     self.ffmpeg_process.terminate()
                     self.ffmpeg_process.wait(timeout=1)
                except:
                     pass
                
                # Also try taskkill for Windows to be sure, but only if still running
                if os.name == 'nt' and self.ffmpeg_process.poll() is None:
                     os.system(f"taskkill /F /PID {self.ffmpeg_process.pid} >nul 2>&1")
        
        if self.audio_recorder:
            self.audio_recorder.stop_recording()
            
        # Save click logs
        with open(self.click_log_file, 'w') as f:
            json.dump(self.click_log, f, indent=2)
            
        print(f"Raw recording saved: {self.video_temp}")
        print(f"Click logs saved: {self.click_log_file}")
        
        # Trigger Post Processing
        self.post_process()

    def post_process(self):
        from post_processor import PostProcessor
        
        print("Starting post-processing...")
        processor = PostProcessor()
        
        # Configure processor with current settings
        config = {
            "zoom_max": self.zoom_max,
            "smooth_speed": self.smooth_speed,
            "zoom_duration": self.zoom_duration,
            "fps": self.fps,
            "quality": self.video_quality
        }
        
        processor.process(
            self.video_temp,
            self.audio_file if self.audio_mode != AudioRecorder.MODE_NONE else None,
            self.click_log_file,
            self.output_file,
            config
        )

        # Cleanup intermediate files
        try:
            if os.path.exists(self.video_temp):
                os.remove(self.video_temp)
            if os.path.exists(self.click_log_file):
                os.remove(self.click_log_file)
            if self.audio_file and os.path.exists(self.audio_file):
                os.remove(self.audio_file)
            print("Intermediate files cleaned up.")
        except Exception as e:
            print(f"Error cleaning up files: {e}")

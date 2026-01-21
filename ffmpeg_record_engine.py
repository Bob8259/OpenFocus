
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
        self.mouse_log_interval = 0.05  # 20 FPS limiting
        self.last_mouse_log_time = 0
        
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
            # Rate limiting: 10 FPS
            current_real_time = time.time()
            if current_real_time - self.last_mouse_log_time < self.mouse_log_interval:
                return
            self.last_mouse_log_time = current_real_time

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


    def pause(self):
        """Pause recording and log event"""
        if not self.is_running or self.is_paused:
            return
        
        self.is_paused = True
        if self.start_time:
            timestamp = time.time() - self.start_time
            with self.log_lock:
                self.click_log.append({
                    "time": timestamp,
                    "type": "pause_start"
                })
        print("Engine paused")

    def resume(self):
        """Resume recording and log event"""
        if not self.is_running or not self.is_paused:
            return
            
        if self.start_time:
            timestamp = time.time() - self.start_time
            with self.log_lock:
                self.click_log.append({
                    "time": timestamp,
                    "type": "pause_end"
                })
        self.is_paused = False
        print("Engine resumed")

    def reset(self):
        """重置录制引擎状态，清空所有缓冲区和日志"""
        with self.log_lock:
            self.click_log = []
        self.start_time = None
        self.is_running = False
        self.is_paused = False
        self.output_file = ""
        self.video_temp = ""
        self.click_log_file = ""
        self.audio_file = ""
        self.ffmpeg_process = None
        self.ffmpeg_process = None
        self.mouse_listener = None
        self.last_mouse_log_time = 0
        print("FFmpeg engine reset: all buffers and logs cleared")

    def run(self):
        """Start the recording process"""
        # 清空之前的录制数据
        self.reset()
        
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
        else:
            # 如果没有音频录制，确保 audio_recorder 为 None
            self.audio_recorder = None

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
                creationflags=creationflags,
                universal_newlines=True # Text mode for easier parsing
            )
            
            # Start a thread to monitor stderr for start signal and prevent blocking
            self.start_event = threading.Event()
            self.stderr_thread = threading.Thread(target=self._monitor_stderr)
            self.stderr_thread.daemon = True
            self.stderr_thread.start()
            
            # Wait for FFmpeg to actually start
            if self.start_event.wait(timeout=5.0):
                print("FFmpeg started successfully (synced).")
            else:
                 print("Warning: Timed out waiting for FFmpeg start signal. Using fallback timing.")
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
                # The pause events are logged. PostProcessor will cut these sections.
                # Video continues recording but will be trimmed later.
                
                time.sleep(0.1)

        except Exception as e:
            print(f"Error running FFmpeg: {e}")
        finally:
            self.cleanup()

    def _monitor_stderr(self):
        """Monitor FFmpeg stderr for start signal and consume output"""
        try:
            while self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                line = self.ffmpeg_process.stderr.readline()
                if not line:
                    break
                    
                # print(f"FFmpeg Log: {line.strip()}") # Optional: debug logging
                
                # Check for start signal
                if not self.start_time:
                    # Look for "Press [q]" or "frame=" which indicates main loop started
                    if "Press [q]" in line or "frame=" in line or "fps=" in line:
                         self.start_time = time.time()
                         self.start_event.set()
        except Exception as e:
            print(f"Error reading stderr: {e}")

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
        # 1. Immediately stop audio capture so we don't record extra seconds while waiting for FFmpeg
        if self.audio_recorder:
            self.audio_recorder.stop_capture()

        if self.mouse_listener:
            self.mouse_listener.stop()
            
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            # Terminate FFmpeg gracefully to finalize file
            # Send 'q' to stdin
            try:
                self.ffmpeg_process.stdin.write('q')
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
        
        # 2. Now that FFmpeg is done, we can finish saving the audio file
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

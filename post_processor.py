
import cv2
import json
import os
import numpy as np
import pyautogui
from video_audio_merger import VideoAudioMerger
from utils.locale_manager import locale_manager
import subprocess
from utils.path_utils import get_ffmpeg_path

class PostProcessor:
    def __init__(self):
        self.current_zoom = 1.0
        self.curr_center = [0, 0]
        self.last_click_time = -100 # Initialize far in past
        self.click_coord = (0, 0)
        self.is_active = False

    def process(self, video_path, audio_path, click_log_path, output_path, config):
        """
        Process the raw video and apply zoom effects based on click logs.
        """
        if not os.path.exists(video_path):
            print(f"Error: Video file not found: {video_path}")
            return
            
        with open(click_log_path, 'r') as f:
            full_log = json.load(f)
            
        # Separate clicks and moves for easier processing
        clicks = [e for e in full_log if e.get('type') == 'click' or 'button' in e] # Fallback for old logs
        moves = [e for e in full_log if e.get('type') == 'move']
        
        # Sort just in case
        clicks.sort(key=lambda x: x['time'])
        clicks.sort(key=lambda x: x['time'])
        moves.sort(key=lambda x: x['time'])

        # Parse Pause Intervals
        pause_events = [e for e in full_log if e.get('type', '').startswith('pause_')]
        pause_events.sort(key=lambda x: x['time'])
        
        pause_intervals = []
        current_pause_start = None
        
        for e in pause_events:
            if e['type'] == 'pause_start':
                current_pause_start = e['time']
            elif e['type'] == 'pause_end' and current_pause_start is not None:
                pause_intervals.append((current_pause_start, e['time']))
                current_pause_start = None
        
        if current_pause_start is not None:
             # Assume pause until end of video
             pause_intervals.append((current_pause_start, 999999))
             
        if pause_intervals:
            print(f"Detected {len(pause_intervals)} pause intervals: {pause_intervals}")
            
        # Parse Config
        zoom_max = config.get("zoom_max", 1.3)
        smooth_speed = config.get("smooth_speed", 0.15)
        zoom_duration = config.get("zoom_duration", 1.0)
        
        try:
            cap = cv2.VideoCapture(video_path)
        except Exception as e:
            print(f"OpenCV open error: {e}")
            cap = None
        
        # Check if video opened successfully
        if cap is None or not cap.isOpened():
            print(f"Warning: Could not open video file {video_path}. Attempting repair...")
            if cap:
                cap.release()
                
            # Attempt repair
            repaired_path = self.repair_video(video_path)
            if repaired_path and os.path.exists(repaired_path):
                print(f"Repair successful. Using: {repaired_path}")
                video_path = repaired_path # Use repaired file
                cap = cv2.VideoCapture(video_path)
            else:
                 print("Repair failed.")
                 return

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Temp output for processed video (silent)
        temp_output = output_path.replace(".mp4", "_processed_video.mp4")
        
        if not cap.isOpened():
            print(f"Error: Could not open video file {video_path}")
            return
            
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))
        
        print(f"Processing video: {total_frames} frames, {width}x{height} @ {fps}fps")
        
        self.curr_center = [width // 2, height // 2]
        
        frame_idx = 0
        click_idx = 0
        move_idx = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Use actual video timestamp if available, fallback to frame count
            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp_ms > 0:
                 current_time = timestamp_ms / 1000.0
            else:
                 current_time = frame_idx / fps

            # Check if current_time is inside any pause interval
            is_paused_frame = False
            for start, end in pause_intervals:
                if start <= current_time <= end:
                    is_paused_frame = True
                    break
            
            if is_paused_frame:
                frame_idx += 1
                continue
            
            # Check for clicks around this time
            # We want to trigger the effect slightly before or exactly at the click?
            # User said: "Check if current frame time has click event"
            # We can look ahead simply by checking the sorted list
            
            # Allow multiple clicks in close succession
            while click_idx < len(clicks):
                click = clicks[click_idx]
                # Trigger slightly if within a small window, or just ensure we catch it
                # Since log is time-based, just check if we passed it
                if click['time'] <= current_time:
                    self.last_click_time = current_time # Sync effect start with video time
                    self.click_coord = (click['x'], click['y'])
                    self.is_active = True
                    click_idx += 1
                    print(f"Applied click effect at {current_time:.2f}s: {self.click_coord}")
                else:
                    break

            # Logic from RecordEngine
            if self.is_active and (current_time - self.last_click_time < zoom_duration):
                target_f = zoom_max
                target_c = self.click_coord
            else:
                target_f = 1.0
                target_c = (width // 2, height // 2)
                self.is_active = False

            # Smooth interpolation
            self.current_zoom += (target_f - self.current_zoom) * smooth_speed
            self.curr_center[0] += (target_c[0] - self.curr_center[0]) * smooth_speed
            self.curr_center[1] += (target_c[1] - self.curr_center[1]) * smooth_speed
            
            # Find current mouse position from moves log
            # Simple approach: find the last move event before current_time
            # For better smoothness, we could interpolate between two events
            current_mouse_pos = (width // 2, height // 2) # Default center
            
            # We can maintain an index for moves too since they are time-sorted
            # But scanning backward slightly is safer if we skip frames? No, we process sequentially.
            # Let's use a simple cached index
            while move_idx < len(moves) - 1:
                if moves[move_idx+1]['time'] <= current_time:
                    move_idx += 1
                else:
                    break
            
            if move_idx < len(moves):
                current_mouse_pos = (moves[move_idx]['x'], moves[move_idx]['y'])

            # Apply effects
            processed = self.apply_zoom(frame, self.curr_center, self.current_zoom, (width, height))
            processed = self.draw_effects(processed, self.current_zoom, self.curr_center, width, height, current_time, current_mouse_pos)
            
            out.write(processed)
            frame_idx += 1
            
            if frame_idx % 30 == 0:
                print(f"Processed {frame_idx}/{total_frames} frames...", end='\r')

        cap.release()
        out.release()
        print("\nProcessing complete.")
        
        # Merge Audio
        quality = config.get("quality", "medium")
        if audio_path and os.path.exists(audio_path):
            VideoAudioMerger.merge_with_fallback(temp_output, audio_path, output_path, quality)
        else:
            VideoAudioMerger.merge_with_fallback(temp_output, None, output_path, quality)
            
        # Clean up temp files if desired? 
        # User said "Late flexibility", so maybe keep the raw inputs.
        # But we should clean the intermediate temp_output
        if os.path.exists(temp_output):
            os.remove(temp_output)
            
        # Clean up repaired file if it exists
        if 'repaired_path' in locals() and repaired_path and os.path.exists(repaired_path):
            try:
                os.remove(repaired_path)
            except Exception as e:
                print(f"Error cleaning up repaired file: {e}")

    def apply_zoom(self, img, center, zoom_factor, target_size):
        h, w = img.shape[:2]
        zoom_factor = max(1.0, zoom_factor)
        cw, ch = int(w / zoom_factor), int(h / zoom_factor)
        
        # Safety for extreme zooms
        cw = max(1, cw)
        ch = max(1, ch)
        
        x, y = center
        x1 = int(max(0, min(x - cw // 2, w - cw)))
        y1 = int(max(0, min(y - ch // 2, h - ch)))
        
        crop = img[y1:y1+ch, x1:x1+cw]
        return cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

    def draw_effects(self, img, zoom_factor, center_orig, width, height, current_time, current_mouse_pos=None):
        zoom_factor = max(1.0, zoom_factor)
        
        # Calculate crop dimensions (must match apply_zoom exactly)
        cw = int(width / zoom_factor)
        ch = int(height / zoom_factor)
        
        # Prevent division by zero and match valid crop logic
        cw = max(1, cw)
        ch = max(1, ch)

        x, y = center_orig
        
        # Calculate top-left of crop (must match apply_zoom exactly)
        x1 = int(max(0, min(x - cw // 2, width - cw)))
        y1 = int(max(0, min(y - ch // 2, height - ch)))

        # Calculate EFFECTIVE scale factor based on actual crop dimensions
        # This matches the resize operation in apply_zoom
        scale_x = width / cw
        scale_y = height / ch

        # 1. Click Ripple Effect
        if current_time - self.last_click_time < 0.5 and self.last_click_time > 0:
            progress = (current_time - self.last_click_time) / 0.5
            
            # Project coords using effective scale
            fx = int((self.click_coord[0] - x1) * scale_x)
            fy = int((self.click_coord[1] - y1) * scale_y)
            
            radius = int(progress * 50)
            alpha_color = (0, 0, 255) # Red
            try:
                cv2.circle(img, (fx, fy), radius, alpha_color, 2)
            except: 
                pass

        # 2. Virtual Mouse Cursor
        if current_mouse_pos:
            mx, my = current_mouse_pos
            
            # Project coords using effective scale
            draw_x = int((mx - x1) * scale_x)
            draw_y = int((my - y1) * scale_y)
            
            # Draw simple arrow cursor
            # Green fill, White outline
            pts = np.array([[draw_x, draw_y], [draw_x, draw_y + 15], [draw_x + 10, draw_y + 10]], np.int32)
            cv2.fillPoly(img, [pts], (0, 255, 0)) 
            cv2.polylines(img, [pts], True, (255, 255, 255), 1)
        
        return img

    def repair_video(self, video_path):
        """
        Attempts to repair a corrupt video file using FFmpeg.
        Returns the path to the repaired file if successful, else None.
        """
        try:
            ffmpeg_path = get_ffmpeg_path()
            repaired_path = video_path.replace(".mkv", "_fixed.mkv")
            
            if os.path.exists(repaired_path):
                os.remove(repaired_path)
                
            cmd = [
                ffmpeg_path,
                "-i", video_path,
                "-c", "copy", # Stream copy to fix container issues
                "-y",
                repaired_path
            ]
            
            print(f"Running repair command: {' '.join(cmd)}")
            
            # Hide console on Windows
            creationflags = 0
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
                
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            
            return repaired_path
        except Exception as e:
            print(f"Video repair failed: {e}")
            return None

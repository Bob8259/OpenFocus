# Copyright 2026 Azikaban/Bob8259

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

import os
import cv2
import numpy as np
import time
from mss import mss
from pynput import mouse
import pyautogui
from audio_recorder import AudioRecorder
from video_audio_merger import VideoAudioMerger
from utils.locale_manager import locale_manager

class RecordEngine:
    """负责所有后端录屏与图像处理逻辑"""
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.pause_start_time = 0
        self.total_paused_duration = 0

        # 默认参数（可被 UI 实时修改）
        self.zoom_max = 1.3
        self.smooth_speed = 0.15
        self.zoom_duration = 1.0  # 缩放持续时间（秒）
        self.fps = 30.0
        self.output_file = ""
        self.save_path = ""
        self.video_quality = "medium"
        
        # 音频录制参数
        self.audio_mode = AudioRecorder.MODE_NONE  # 音频模式
        self.audio_recorder = None
        self.audio_file = ""
        self.system_volume = 1.0  # 系统音量增益
        self.mic_volume = 2.0  # 麦克风音量增益（默认2.0以增强麦克风）
        
        # 录制区域参数
        self.record_region = None  # None 表示全屏，否则为 {'left': x, 'top': y, 'width': w, 'height': h}

        # 内部状态
        self.current_zoom = 1.0
        self.curr_center = [0, 0]
        self.last_click_time = 0
        self.click_coord = (0, 0)
        self.is_active = False

    def on_click(self, x, y, button, pressed):
        if pressed:
            self.click_coord = (int(x), int(y))
            self.last_click_time = time.time()
            self.is_active = True

    def apply_zoom(self, img, center, zoom_factor, target_size):
        h, w = img.shape[:2]
        zoom_factor = max(1.0, zoom_factor)
        cw, ch = int(w / zoom_factor), int(h / zoom_factor)
        
        x, y = center
        x1 = int(max(0, min(x - cw // 2, w - cw)))
        y1 = int(max(0, min(y - ch // 2, h - ch)))
        
        crop = img[y1:y1+ch, x1:x1+cw]
        return cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

    def draw_effects(self, img, zoom_factor, center_orig, width, height):
        now = time.time()
        # 计算缩放后的偏移偏移参考
        cw, ch = width / zoom_factor, height / zoom_factor
        x1 = max(0, min(center_orig[0] - cw // 2, width - cw))
        y1 = max(0, min(center_orig[1] - ch // 2, height - ch))

        # 1. 绘制点击特效
        if now - self.last_click_time < 0.5:
            progress = (now - self.last_click_time) / 0.5
            fx = int((self.click_coord[0] - x1) * zoom_factor)
            fy = int((self.click_coord[1] - y1) * zoom_factor)
            radius = int(progress * 50)
            alpha_color = (0, 0, 255) # 红色
            cv2.circle(img, (fx, fy), radius, alpha_color, 2)

        # 2. 绘制鼠标指针
        raw_mx, raw_my = pyautogui.position()
        draw_x = int((raw_mx - x1) * zoom_factor)
        draw_y = int((raw_my - y1) * zoom_factor)
        
        pts = np.array([[draw_x, draw_y], [draw_x, draw_y + 15], [draw_x + 10, draw_y + 10]], np.int32)
        cv2.fillPoly(img, [pts], (0, 255, 0)) # 绿色
        cv2.polylines(img, [pts], True, (255, 255, 255), 1)
        return img

    def run(self):
        self.is_running = True
        self.is_paused = False
        timestamp = int(time.time())
        
        # 根据音频模式决定文件名
        filename = f"Record_{timestamp}.mp4"
        if self.save_path and os.path.exists(self.save_path):
            self.output_file = os.path.join(self.save_path, filename)
        else:
            self.output_file = filename

        # 始终使用临时视频文件，以便最后通过 FFmpeg 压缩
        video_temp = self.output_file.replace(".mp4", "_video.mp4")
        
        if self.audio_mode != AudioRecorder.MODE_NONE:
            self.audio_file = self.output_file.replace(".mp4", "_audio.wav")
        
        # 启动音频录制
        if self.audio_mode != AudioRecorder.MODE_NONE:
            self.audio_recorder = AudioRecorder(
                mode=self.audio_mode,
                sample_rate=48000,
                system_volume=self.system_volume,
                mic_volume=self.mic_volume
            )
            audio_started = self.audio_recorder.start_recording(self.audio_file)
            if not audio_started:
                print(locale_manager.get_text("log_audio_start_fail"))
                self.audio_mode = AudioRecorder.MODE_NONE
        
        listener = mouse.Listener(on_click=self.on_click)
        listener.start()

        with mss() as sct:
            # 确定录制区域
            if self.record_region:
                # 使用自定义区域
                monitor = {
                    'left': self.record_region['left'],
                    'top': self.record_region['top'],
                    'width': self.record_region['width'],
                    'height': self.record_region['height']
                }
                w, h = self.record_region['width'], self.record_region['height']
            else:
                # 使用全屏
                monitor = sct.monitors[1]
                w, h = monitor["width"], monitor["height"]
            
            self.curr_center = [w // 2, h // 2]
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_temp, fourcc, self.fps, (w, h))

            # 设置音频录制开始时间（与视频录制同步）
            start_time = time.time()
            if self.audio_mode != AudioRecorder.MODE_NONE and self.audio_recorder:
                self.audio_recorder.set_start_time()

            self.total_paused_duration = 0
            frames_written = 0

            while self.is_running:
                if self.is_paused:
                    if self.pause_start_time == 0:
                        self.pause_start_time = time.time()
                    time.sleep(0.1)
                    continue
                
                if self.pause_start_time > 0:
                    self.total_paused_duration += (time.time() - self.pause_start_time)
                    self.pause_start_time = 0

                loop_start = time.time()
                
                # 计算当前应该有的总帧数
                elapsed = loop_start - start_time - self.total_paused_duration
                expected_frames = int(elapsed * self.fps)
                
                # 抓取屏幕
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                # 逻辑判断：是否处于点击缩放期间
                now = time.time()
                if self.is_active and (now - self.last_click_time < self.zoom_duration):
                    target_f = self.zoom_max
                    target_c = self.click_coord
                else:
                    target_f = 1.0
                    target_c = (w // 2, h // 2)
                    self.is_active = False

                # 平滑差值计算
                self.current_zoom += (target_f - self.current_zoom) * self.smooth_speed
                self.curr_center[0] += (target_c[0] - self.curr_center[0]) * self.smooth_speed
                self.curr_center[1] += (target_c[1] - self.curr_center[1]) * self.smooth_speed

                # 处理图像
                processed = self.apply_zoom(frame, self.curr_center, self.current_zoom, (w, h))
                processed = self.draw_effects(processed, self.current_zoom, self.curr_center, w, h)

                # 写入当前帧，并根据需要补帧以维持 FPS
                out.write(processed)
                frames_written += 1
                
                while frames_written < expected_frames:
                    out.write(processed)
                    frames_written += 1

                # 帧率控制
                elapsed_loop = time.time() - loop_start
                wait = (1.0 / self.fps) - elapsed_loop
                if wait > 0:
                    time.sleep(wait)

            out.release()
            listener.stop()
            
            # 停止音频录制
            if self.audio_mode != AudioRecorder.MODE_NONE and self.audio_recorder:
                print(locale_manager.get_text("log_audio_stop"))
                self.audio_recorder.stop_recording()
                
                # 合并音视频并压缩
                print(locale_manager.get_text("log_merging"))
                success, final_file = VideoAudioMerger.merge_with_fallback(
                    video_temp, self.audio_file, self.output_file, quality=self.video_quality
                )
                if success:
                    self.output_file = final_file
                else:
                    print(locale_manager.get_text("log_merge_fail"))
            else:
                # 仅压缩视频
                print(locale_manager.get_text("log_merging")) # 复用合并日志表示处理中
                success, final_file = VideoAudioMerger.merge_with_fallback(
                    video_temp, "", self.output_file, quality=self.video_quality
                )
                if success:
                    self.output_file = final_file

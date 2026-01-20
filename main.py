# Copyright 2026 Azikaban/Bob8259

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

import sys
import os
import cv2
import numpy as np
import time
from threading import Thread
from mss import mss
from pynput import mouse, keyboard
import pyautogui
import customtkinter as ctk
from tkinter import filedialog
from audio_recorder import AudioRecorder
from video_audio_merger import VideoAudioMerger
from region_selector import RegionSelector
from utils.locale_manager import locale_manager
from utils.config_manager import config_manager

# 解决 Windows DPI 缩放导致的界面模糊和报错
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# --- 界面风格配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

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

        if self.audio_mode == AudioRecorder.MODE_NONE:
            video_temp = self.output_file
        else:
            video_temp = self.output_file.replace(".mp4", "_video.mp4")
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
                
                # 合并音视频
                print(locale_manager.get_text("log_merging"))
                success, final_file = VideoAudioMerger.merge_with_fallback(
                    video_temp, self.audio_file, self.output_file
                )
                if success:
                    self.output_file = final_file
                else:
                    print(locale_manager.get_text("log_merge_fail"))


class OverlayIcon(ctk.CTkToplevel):
    def __init__(self, master, icon_type="start"):
        super().__init__(master)
        self.title("Overlay")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # Windows transparency trick: use a color key
        # We use a color that is unlikely to be used in the icon itself
        self.attributes("-transparentcolor", "white")
        self.configure(fg_color="white")
        
        size = 120
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (size // 2)
        y = (screen_height // 2) - (size // 2)
        self.geometry(f"{size}x{size}+{x}+{y}")
        
        self.canvas = ctk.CTkCanvas(self, width=size, height=size, bg="white", highlightthickness=0)
        self.canvas.pack(expand=True, fill="both")
        
        if icon_type == "start":
            # Green Play Triangle
            self.canvas.create_polygon([30, 20, 30, 100, 100, 60], fill="#27ae60", outline="#2ecc71", width=2)
        elif icon_type == "pause":
            # Orange Pause Bars
            self.canvas.create_rectangle(35, 25, 55, 95, fill="#e67e22", outline="#d35400", width=2)
            self.canvas.create_rectangle(65, 25, 85, 95, fill="#e67e22", outline="#d35400", width=2)
            
        self.after(1000, self.destroy)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Apply language from config
        lang = config_manager.get("language", "zh_CN")
        locale_manager.set_language(lang)

        # --- 全局快捷键 ---
        self.hotkey_listener = keyboard.GlobalHotKeys({
            '<ctrl>+<f1>': self.on_f1_shortcut,
            '<ctrl>+<f2>': self.on_f2_shortcut
        })
        self.hotkey_listener.start()


        self.title(locale_manager.get_text("window_title"))
        self.geometry("700x750")
        self.engine = RecordEngine()
        self.is_starting = False
        
        # Apply config to engine
        self.engine.zoom_max = config_manager.get("zoom_max", 1.3)
        self.engine.smooth_speed = config_manager.get("smooth_speed", 0.15)
        self.engine.zoom_duration = config_manager.get("zoom_duration", 1.0)
        self.engine.audio_mode = config_manager.get("audio_mode", AudioRecorder.MODE_NONE)
        self.engine.system_volume = config_manager.get("system_volume", 1.0)
        self.engine.mic_volume = config_manager.get("mic_volume", 2.0)
        self.engine.record_region = config_manager.get("record_region", None)
        self.engine.save_path = config_manager.get("save_path", "")
        
        # 音频模式映射
        self.audio_mode_map = {
            locale_manager.get_text("audio_mode_none"): AudioRecorder.MODE_NONE,
            locale_manager.get_text("audio_mode_system"): AudioRecorder.MODE_SYSTEM,
            locale_manager.get_text("audio_mode_mic"): AudioRecorder.MODE_MICROPHONE,
            locale_manager.get_text("audio_mode_both"): AudioRecorder.MODE_BOTH
        }

        # UI 布局
        self.grid_columnconfigure(0, weight=1)

        # 头部标题
        self.header = ctk.CTkLabel(self, text=locale_manager.get_text("app_title"), font=ctk.CTkFont(size=22, weight="bold"))
        self.header.grid(row=0, column=0, padx=20, pady=(20, 15))
        
        # 区域选择按钮
        self.region_frame = ctk.CTkFrame(self)
        self.region_frame.grid(row=1, column=0, padx=30, pady=(0, 10), sticky="ew")
        self.region_frame.grid_columnconfigure(0, weight=1)
        
        self.region_label = ctk.CTkLabel(
            self.region_frame,
            text=locale_manager.get_text("region_label_fullscreen"),
            font=ctk.CTkFont(size=13)
        )
        self.region_label.grid(row=0, column=0, pady=(10, 5))
        
        self.region_btn = ctk.CTkButton(
            self.region_frame,
            text=locale_manager.get_text("btn_select_region"),
            command=self.select_region,
            width=180,
            height=32,
            fg_color="#3498db",
            hover_color="#2980b9"
        )
        self.region_btn.grid(row=1, column=0, pady=(0, 10))

        # Restore region UI if saved
        if self.engine.record_region:
            region = self.engine.record_region
            region_text = locale_manager.get_text("region_label_selected").format(
                width=region['width'], height=region['height'], left=region['left'], top=region['top']
            )
            self.region_label.configure(text=region_text)
            self.region_btn.configure(text=locale_manager.get_text("btn_reselect_region"))

        # 参数设置卡片 (Double Column)
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        
        # Configure columns for settings frame
        self.settings_frame.grid_columnconfigure(0, weight=1)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        # --- LEFT COLUMN (Video Settings) ---
        
        # 缩放倍数
        self.zoom_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_zoom").format(self.engine.zoom_max))
        self.zoom_label.grid(row=0, column=0, pady=(15, 0))
        self.zoom_slider = ctk.CTkSlider(self.settings_frame, from_=1.0, to=2.5, command=self.change_zoom)
        self.zoom_slider.set(self.engine.zoom_max)
        self.zoom_slider.grid(row=1, column=0, padx=20, pady=10)

        # 平滑度
        self.smooth_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_smooth").format(self.engine.smooth_speed))
        self.smooth_label.grid(row=2, column=0, pady=(10, 0))
        self.smooth_slider = ctk.CTkSlider(self.settings_frame, from_=0.05, to=0.5, command=self.change_smooth)
        self.smooth_slider.set(self.engine.smooth_speed)
        self.smooth_slider.grid(row=3, column=0, padx=20, pady=10)

        # 缩放持续时间
        self.duration_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_duration").format(self.engine.zoom_duration))
        self.duration_label.grid(row=4, column=0, pady=(10, 0))
        self.duration_slider = ctk.CTkSlider(self.settings_frame, from_=0.3, to=3.0, command=self.change_duration)
        self.duration_slider.set(self.engine.zoom_duration)
        self.duration_slider.grid(row=5, column=0, padx=20, pady=10)

        # --- RIGHT COLUMN (Audio & Other Settings) ---
        
        # 音频录制模式
        self.audio_mode_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_audio_mode"),
                                             font=ctk.CTkFont(size=13, weight="bold"))
        self.audio_mode_label.grid(row=0, column=1, pady=(15, 5))
        
        self.audio_mode_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=list(self.audio_mode_map.keys()),
            command=self.change_audio_mode,
            width=200,
            height=32,
            font=ctk.CTkFont(size=13)
        )
        # Set initial audio mode in UI
        current_mode_label = [k for k, v in self.audio_mode_map.items() if v == self.engine.audio_mode]
        if current_mode_label:
            self.audio_mode_menu.set(current_mode_label[0])
        else:
            self.audio_mode_menu.set(locale_manager.get_text("audio_mode_none"))
        self.audio_mode_menu.grid(row=1, column=1, padx=20, pady=(0, 10))
        
        # 系统音量控制
        self.system_volume_label = ctk.CTkLabel(
            self.settings_frame,
            text=locale_manager.get_text("label_system_volume").format(self.engine.system_volume),
            font=ctk.CTkFont(size=12)
        )
        self.system_volume_label.grid(row=2, column=1, pady=(10, 0))
        self.system_volume_slider = ctk.CTkSlider(
            self.settings_frame,
            from_=0.0,
            to=3.0,
            command=self.change_system_volume
        )
        self.system_volume_slider.set(self.engine.system_volume)
        self.system_volume_slider.grid(row=3, column=1, padx=20, pady=(5, 10))
        
        # 麦克风音量控制
        self.mic_volume_label = ctk.CTkLabel(
            self.settings_frame,
            text=locale_manager.get_text("label_mic_volume").format(self.engine.mic_volume),
            font=ctk.CTkFont(size=12)
        )
        self.mic_volume_label.grid(row=4, column=1, pady=(5, 0))
        self.mic_volume_slider = ctk.CTkSlider(
            self.settings_frame,
            from_=0.0,
            to=3.0,
            command=self.change_mic_volume
        )
        self.mic_volume_slider.set(self.engine.mic_volume)
        self.mic_volume_slider.grid(row=5, column=1, padx=20, pady=(5, 15))
        
        # Language Selector
        self.language_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_language"), font=ctk.CTkFont(size=13, weight="bold"))
        self.language_label.grid(row=6, column=0, columnspan=2, pady=(15, 5))  # Centered at bottom or keep in right column? Let's center it at bottom of frame
        
        self.language_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=["English", "简体中文"],
            command=self.change_language,
            width=200,
            height=32,
            font=ctk.CTkFont(size=13)
        )
        self.language_menu.set("English" if locale_manager.current_locale == "en" else "简体中文")
        self.language_menu.grid(row=7, column=0, columnspan=2, padx=20, pady=(0, 10))

        # Save Path Selector
        self.save_path_label = ctk.CTkLabel(self.settings_frame, text=locale_manager.get_text("label_save_path"), font=ctk.CTkFont(size=13, weight="bold"))
        self.save_path_label.grid(row=8, column=0, columnspan=2, pady=(10, 5))

        self.path_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.path_frame.grid(row=9, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        self.path_frame.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(self.path_frame, height=32)
        self.path_entry.insert(0, self.engine.save_path if self.engine.save_path else os.getcwd())
        self.path_entry.configure(state="readonly")
        self.path_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.path_btn = ctk.CTkButton(
            self.path_frame,
            text=locale_manager.get_text("btn_browse"),
            command=self.select_save_path,
            width=80,
            height=32
        )
        self.path_btn.grid(row=0, column=1)

        # 状态指示
        self.status_label = ctk.CTkLabel(self, text=locale_manager.get_text("status_ready"), text_color="#7f8c8d")
        self.status_label.grid(row=3, column=0, pady=10)

        # 控制按钮容器
        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.grid(row=4, column=0, padx=40, pady=(0, 30), sticky="ew")
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1)

        # 主按钮 (开始/停止)
        self.btn_main = ctk.CTkButton(self.control_frame, text=locale_manager.get_text("btn_start"), fg_color="#27ae60", hover_color="#219150",
                                      height=50, font=ctk.CTkFont(size=15, weight="bold"),
                                      command=self.toggle_action)
        self.btn_main.grid(row=0, column=0, columnspan=2, sticky="ew")

        # 暂停/继续按钮
        self.btn_pause = ctk.CTkButton(self.control_frame, text=locale_manager.get_text("btn_pause"), fg_color="#e67e22", hover_color="#d35400",
                                       height=50, font=ctk.CTkFont(size=15, weight="bold"),
                                       command=self.toggle_pause)
        self.btn_pause.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.btn_pause.grid_remove() # 初始隐藏

    def toggle_pause(self):
        """切换暂停/继续状态"""
        if not self.engine.is_running:
            return
            
        if self.engine.is_paused:
            self.resume_recording()
        else:
            self.pause_recording()

    def change_zoom(self, value):
        self.engine.zoom_max = round(value, 2)
        config_manager.set("zoom_max", self.engine.zoom_max)
        self.zoom_label.configure(text=locale_manager.get_text("label_zoom").format(self.engine.zoom_max))

    def change_smooth(self, value):
        self.engine.smooth_speed = round(value, 2)
        config_manager.set("smooth_speed", self.engine.smooth_speed)
        self.smooth_label.configure(text=locale_manager.get_text("label_smooth").format(self.engine.smooth_speed))

    def change_duration(self, value):
        self.engine.zoom_duration = round(value, 2)
        config_manager.set("zoom_duration", self.engine.zoom_duration)
        self.duration_label.configure(text=locale_manager.get_text("label_duration").format(self.engine.zoom_duration))
    
    def change_audio_mode(self, choice):
        """更改音频录制模式"""
        self.engine.audio_mode = self.audio_mode_map[choice]
        config_manager.set("audio_mode", self.engine.audio_mode)
        print(locale_manager.get_text("log_audio_mode_set").format(choice, self.engine.audio_mode))
    
    def change_system_volume(self, value):
        """更改系统音量增益"""
        self.engine.system_volume = round(value, 2)
        config_manager.set("system_volume", self.engine.system_volume)
        self.system_volume_label.configure(text=locale_manager.get_text("label_system_volume").format(self.engine.system_volume))
    
    def change_mic_volume(self, value):
        """更改麦克风音量增益"""
        self.engine.mic_volume = round(value, 2)
        config_manager.set("mic_volume", self.engine.mic_volume)
        self.mic_volume_label.configure(text=locale_manager.get_text("label_mic_volume").format(self.engine.mic_volume))
    
    def select_save_path(self):
        """选择保存路径"""
        path = filedialog.askdirectory()
        if path:
            self.engine.save_path = path
            config_manager.set("save_path", path)
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)
            self.path_entry.configure(state="readonly")
            print(locale_manager.get_text("log_save_path_set").format(path))

    def select_region(self):
        """选择录制区域"""
        # 最小化主窗口
        self.iconify()
        
        # 等待窗口最小化完成
        self.after(200, self._show_region_selector)

    def change_language(self, choice):
        lang_code = "en" if choice == "English" else "zh_CN"
        if lang_code == locale_manager.current_locale:
            return
            
        locale_manager.set_language(lang_code)
        config_manager.set("language", lang_code)
        
        # Refresh UI
        self.header.configure(text=locale_manager.get_text("app_title"))
        self.title(locale_manager.get_text("window_title"))
        
        if self.engine.record_region:
            region_text = locale_manager.get_text("region_label_selected").format(
                width=self.engine.record_region['width'], 
                height=self.engine.record_region['height'], 
                left=self.engine.record_region['left'], 
                top=self.engine.record_region['top']
            )
            self.region_btn.configure(text=locale_manager.get_text("btn_reselect_region"))
        else:
            region_text = locale_manager.get_text("region_label_fullscreen")
            self.region_btn.configure(text=locale_manager.get_text("btn_select_region"))
        self.region_label.configure(text=region_text)
        
        self.zoom_label.configure(text=locale_manager.get_text("label_zoom").format(self.engine.zoom_max))
        self.smooth_label.configure(text=locale_manager.get_text("label_smooth").format(self.engine.smooth_speed))
        self.duration_label.configure(text=locale_manager.get_text("label_duration").format(self.engine.zoom_duration))
        
        self.audio_mode_label.configure(text=locale_manager.get_text("label_audio_mode"))
        
        # Update audio mode map and menu
        self.audio_mode_map = {
            locale_manager.get_text("audio_mode_none"): AudioRecorder.MODE_NONE,
            locale_manager.get_text("audio_mode_system"): AudioRecorder.MODE_SYSTEM,
            locale_manager.get_text("audio_mode_mic"): AudioRecorder.MODE_MICROPHONE,
            locale_manager.get_text("audio_mode_both"): AudioRecorder.MODE_BOTH
        }
        
        # Find new label for current mode
        new_label = [k for k, v in self.audio_mode_map.items() if v == self.engine.audio_mode][0]
        self.audio_mode_menu.configure(values=list(self.audio_mode_map.keys()))
        self.audio_mode_menu.set(new_label)
        
        self.system_volume_label.configure(text=locale_manager.get_text("label_system_volume").format(self.engine.system_volume))
        self.mic_volume_label.configure(text=locale_manager.get_text("label_mic_volume").format(self.engine.mic_volume))
        
        if not self.engine.is_running:
            self.status_label.configure(text=locale_manager.get_text("status_ready"))
            self.btn_main.configure(text=locale_manager.get_text("btn_start"))
        else:
            if self.engine.is_paused:
                self.status_label.configure(text=locale_manager.get_text("status_paused"))
                self.btn_pause.configure(text=locale_manager.get_text("btn_resume"))
            else:
                self.status_label.configure(text=locale_manager.get_text("status_recording"))
                self.btn_pause.configure(text=locale_manager.get_text("btn_pause"))
            self.btn_main.configure(text=locale_manager.get_text("btn_stop"))

        self.language_label.configure(text=locale_manager.get_text("label_language"))
        self.save_path_label.configure(text=locale_manager.get_text("label_save_path"))
        self.path_btn.configure(text=locale_manager.get_text("btn_browse"))
    
    def _show_region_selector(self):
        """显示区域选择器"""
        selector = RegionSelector()
        region = selector.select_region()
        
        # 恢复主窗口
        self.deiconify()
        
        if region:
            self.engine.record_region = region
            config_manager.set("record_region", region)
            region_text = locale_manager.get_text("region_label_selected").format(
                width=region['width'], height=region['height'], left=region['left'], top=region['top']
            )
            self.region_label.configure(text=region_text)
            self.region_btn.configure(text=locale_manager.get_text("btn_reselect_region"))
            print(locale_manager.get_text("log_region_set").format(region))
        else:
            print(locale_manager.get_text("log_region_cancel"))

    def show_overlay(self, icon_type):
        OverlayIcon(self, icon_type)

    def toggle_action(self):
        if not self.engine.is_running:
            if self.is_starting:
                return
            # 开始录制
            self.is_starting = True
            self.btn_main.configure(state="disabled")
            self.show_overlay("start")
            # 延迟 1 秒后真正开始录制
            self.after(1000, self._really_start_recording)
        else:
            # 停止录制
            self.engine.is_running = False
            self.engine.is_paused = False
            self.status_label.configure(text=locale_manager.get_text("status_saving"), text_color="#f1c40f")
            self.btn_main.configure(state="disabled")
            self.btn_pause.grid_remove()
            
            # 检查线程结束
            self.check_thread_done()

    def _really_start_recording(self):
        self.is_starting = False
        self.status_label.configure(text=locale_manager.get_text("status_recording"), text_color="#e74c3c")
        self.btn_main.grid(row=0, column=0, columnspan=1, padx=(0, 5), sticky="ew")
        self.btn_main.configure(state="normal", text=locale_manager.get_text("btn_stop"), fg_color="#e74c3c", hover_color="#c0392b")
        self.btn_pause.grid() # 显示暂停按钮
        self.btn_pause.configure(text=locale_manager.get_text("btn_pause"), fg_color="#e67e22", hover_color="#d35400")
        
        # 在单独线程启动引擎，防止 UI 挂起
        self.record_thread = Thread(target=self.engine.run)
        self.record_thread.start()

    def check_thread_done(self):
        if self.record_thread.is_alive():
            self.after(500, self.check_thread_done)
        else:
            self.btn_main.grid(row=0, column=0, columnspan=2, padx=0, sticky="ew")
            self.btn_main.configure(state="normal", text=locale_manager.get_text("btn_start"), fg_color="#27ae60", hover_color="#219150")
            self.status_label.configure(text=locale_manager.get_text("status_saved").format(self.engine.output_file), text_color="#2ecc71")

    def on_f1_shortcut(self):
        """Ctrl+F1: 开始/暂停/继续"""
        if not self.engine.is_running:
            self.toggle_action()  # 开始
        else:
            if self.engine.is_paused:
                self.resume_recording()
            else:
                self.pause_recording()

    def on_f2_shortcut(self):
        """Ctrl+F2: 停止并保存"""
        if self.engine.is_running:
            self.toggle_action()  # 停止

    def pause_recording(self):
        """暂停录制"""
        print("Pausing recording...")
        self.engine.is_paused = True
        self.show_overlay("pause")
        if self.engine.audio_recorder:
            self.engine.audio_recorder.pause()
        self.status_label.configure(text=locale_manager.get_text("status_paused"), text_color="#e67e22")
        self.btn_pause.configure(text=locale_manager.get_text("btn_resume"), fg_color="#27ae60", hover_color="#219150")

    def resume_recording(self):
        """恢复录制"""
        if self.is_starting:
            return
        print("Resuming recording...")
        self.is_starting = True
        self.btn_pause.configure(state="disabled")
        self.show_overlay("start")
        self.after(1000, self._really_resume_recording)

    def _really_resume_recording(self):
        self.is_starting = False
        self.engine.is_paused = False
        if self.engine.audio_recorder:
            self.engine.audio_recorder.resume()
        self.status_label.configure(text=locale_manager.get_text("status_recording"), text_color="#e74c3c")
        self.btn_pause.configure(state="normal", text=locale_manager.get_text("btn_pause"), fg_color="#e67e22", hover_color="#d35400")

    def destroy(self):
        """Cleanup on close"""
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()

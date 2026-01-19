import sys
import os
import cv2
import numpy as np
import time
from threading import Thread
from mss import mss
from pynput import mouse
import pyautogui
import customtkinter as ctk
from audio_recorder import AudioRecorder
from video_audio_merger import VideoAudioMerger
from region_selector import RegionSelector

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
        
        # 默认参数（可被 UI 实时修改）
        self.zoom_max = 1.3
        self.smooth_speed = 0.15
        self.zoom_duration = 1.0  # 缩放持续时间（秒）
        self.fps = 30.0
        self.output_file = ""
        
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
        timestamp = int(time.time())
        
        # 根据音频模式决定文件名
        if self.audio_mode == AudioRecorder.MODE_NONE:
            self.output_file = f"Record_{timestamp}.mp4"
            video_temp = self.output_file
        else:
            video_temp = f"Record_{timestamp}_video.mp4"
            self.audio_file = f"Record_{timestamp}_audio.wav"
            self.output_file = f"Record_{timestamp}.mp4"
        
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
                print("音频录制启动失败，将以无音频模式继续")
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
            if self.audio_mode != AudioRecorder.MODE_NONE and self.audio_recorder:
                self.audio_recorder.set_start_time()

            while self.is_running:
                loop_start = time.time()
                
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

                out.write(processed)

                # 帧率控制
                elapsed = time.time() - loop_start
                wait = (1.0 / self.fps) - elapsed
                if wait > 0:
                    time.sleep(wait)

            out.release()
            listener.stop()
            
            # 停止音频录制
            if self.audio_mode != AudioRecorder.MODE_NONE and self.audio_recorder:
                print("正在停止音频录制...")
                self.audio_recorder.stop_recording()
                
                # 合并音视频
                print("正在合并音视频文件...")
                success, final_file = VideoAudioMerger.merge_with_fallback(
                    video_temp, self.audio_file, self.output_file
                )
                if success:
                    self.output_file = final_file
                else:
                    print("音视频合并失败")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Smooth Focus Recorder")
        self.geometry("420x780")  # 增加高度以容纳音量控制
        self.engine = RecordEngine()
        
        # 音频模式映射
        self.audio_mode_map = {
            "不录音频": AudioRecorder.MODE_NONE,
            "仅系统声音": AudioRecorder.MODE_SYSTEM,
            "仅麦克风": AudioRecorder.MODE_MICROPHONE,
            "麦克风和系统": AudioRecorder.MODE_BOTH
        }

        # UI 布局
        self.grid_columnconfigure(0, weight=1)

        # 头部标题
        self.header = ctk.CTkLabel(self, text="AI 智能录屏系统", font=ctk.CTkFont(size=22, weight="bold"))
        self.header.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        # 区域选择按钮
        self.region_frame = ctk.CTkFrame(self)
        self.region_frame.grid(row=1, column=0, padx=30, pady=(0, 10), sticky="ew")
        self.region_frame.grid_columnconfigure(0, weight=1)
        
        self.region_label = ctk.CTkLabel(
            self.region_frame,
            text="录制区域: 全屏",
            font=ctk.CTkFont(size=13)
        )
        self.region_label.grid(row=0, column=0, pady=(10, 5))
        
        self.region_btn = ctk.CTkButton(
            self.region_frame,
            text="选择录制区域",
            command=self.select_region,
            width=180,
            height=32,
            fg_color="#3498db",
            hover_color="#2980b9"
        )
        self.region_btn.grid(row=1, column=0, pady=(0, 10))

        # 参数设置卡片
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        self.settings_frame.grid_columnconfigure(0, weight=1)

        # 缩放倍数
        self.zoom_label = ctk.CTkLabel(self.settings_frame, text=f"缩放倍数: {self.engine.zoom_max}x")
        self.zoom_label.grid(row=0, column=0, pady=(15, 0))
        self.zoom_slider = ctk.CTkSlider(self.settings_frame, from_=1.0, to=2.5, command=self.change_zoom)
        self.zoom_slider.set(self.engine.zoom_max)
        self.zoom_slider.grid(row=1, column=0, padx=20, pady=10)

        # 平滑度
        self.smooth_label = ctk.CTkLabel(self.settings_frame, text=f"平滑速度: {self.engine.smooth_speed}")
        self.smooth_label.grid(row=2, column=0, pady=(10, 0))
        self.smooth_slider = ctk.CTkSlider(self.settings_frame, from_=0.05, to=0.5, command=self.change_smooth)
        self.smooth_slider.set(self.engine.smooth_speed)
        self.smooth_slider.grid(row=3, column=0, padx=20, pady=10)

        # 缩放持续时间
        self.duration_label = ctk.CTkLabel(self.settings_frame, text=f"缩放持续时间: {self.engine.zoom_duration}秒")
        self.duration_label.grid(row=4, column=0, pady=(10, 0))
        self.duration_slider = ctk.CTkSlider(self.settings_frame, from_=0.3, to=3.0, command=self.change_duration)
        self.duration_slider.set(self.engine.zoom_duration)
        self.duration_slider.grid(row=5, column=0, padx=20, pady=10)
        
        # 音频录制模式
        self.audio_mode_label = ctk.CTkLabel(self.settings_frame, text="音频录制模式",
                                             font=ctk.CTkFont(size=13, weight="bold"))
        self.audio_mode_label.grid(row=6, column=0, pady=(15, 5))
        
        self.audio_mode_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=["不录音频", "仅系统声音", "仅麦克风", "麦克风和系统"],
            command=self.change_audio_mode,
            width=200,
            height=32,
            font=ctk.CTkFont(size=13)
        )
        self.audio_mode_menu.set("不录音频")
        self.audio_mode_menu.grid(row=7, column=0, padx=20, pady=(0, 10))
        
        # 系统音量控制
        self.system_volume_label = ctk.CTkLabel(
            self.settings_frame,
            text=f"系统音量: {self.engine.system_volume}x",
            font=ctk.CTkFont(size=12)
        )
        self.system_volume_label.grid(row=8, column=0, pady=(10, 0))
        self.system_volume_slider = ctk.CTkSlider(
            self.settings_frame,
            from_=0.0,
            to=3.0,
            command=self.change_system_volume
        )
        self.system_volume_slider.set(self.engine.system_volume)
        self.system_volume_slider.grid(row=9, column=0, padx=20, pady=(5, 10))
        
        # 麦克风音量控制
        self.mic_volume_label = ctk.CTkLabel(
            self.settings_frame,
            text=f"麦克风音量: {self.engine.mic_volume}x",
            font=ctk.CTkFont(size=12)
        )
        self.mic_volume_label.grid(row=10, column=0, pady=(5, 0))
        self.mic_volume_slider = ctk.CTkSlider(
            self.settings_frame,
            from_=0.0,
            to=3.0,
            command=self.change_mic_volume
        )
        self.mic_volume_slider.set(self.engine.mic_volume)
        self.mic_volume_slider.grid(row=11, column=0, padx=20, pady=(5, 15))

        # 状态指示
        self.status_label = ctk.CTkLabel(self, text="Ready to Record", text_color="#7f8c8d")
        self.status_label.grid(row=3, column=0, pady=20)

        # 控制按钮
        self.btn_main = ctk.CTkButton(self, text="START RECORDING", fg_color="#27ae60", hover_color="#219150",
                                      height=50, font=ctk.CTkFont(size=15, weight="bold"),
                                      command=self.toggle_action)
        self.btn_main.grid(row=4, column=0, padx=40, pady=(0, 30), sticky="ew")

    def change_zoom(self, value):
        self.engine.zoom_max = round(value, 2)
        self.zoom_label.configure(text=f"缩放倍数: {self.engine.zoom_max}x")

    def change_smooth(self, value):
        self.engine.smooth_speed = round(value, 2)
        self.smooth_label.configure(text=f"平滑速度: {self.engine.smooth_speed}")

    def change_duration(self, value):
        self.engine.zoom_duration = round(value, 2)
        self.duration_label.configure(text=f"缩放持续时间: {self.engine.zoom_duration}秒")
    
    def change_audio_mode(self, choice):
        """更改音频录制模式"""
        self.engine.audio_mode = self.audio_mode_map[choice]
        print(f"音频模式已设置为: {choice} ({self.engine.audio_mode})")
    
    def change_system_volume(self, value):
        """更改系统音量增益"""
        self.engine.system_volume = round(value, 2)
        self.system_volume_label.configure(text=f"系统音量: {self.engine.system_volume}x")
    
    def change_mic_volume(self, value):
        """更改麦克风音量增益"""
        self.engine.mic_volume = round(value, 2)
        self.mic_volume_label.configure(text=f"麦克风音量: {self.engine.mic_volume}x")
    
    def select_region(self):
        """选择录制区域"""
        # 最小化主窗口
        self.iconify()
        
        # 等待窗口最小化完成
        self.after(200, self._show_region_selector)
    
    def _show_region_selector(self):
        """显示区域选择器"""
        selector = RegionSelector()
        region = selector.select_region()
        
        # 恢复主窗口
        self.deiconify()
        
        if region:
            self.engine.record_region = region
            region_text = f"录制区域: {region['width']}x{region['height']} @ ({region['left']}, {region['top']})"
            self.region_label.configure(text=region_text)
            self.region_btn.configure(text="重新选择区域")
            print(f"已设置录制区域: {region}")
        else:
            print("未选择区域，将使用当前设置")

    def toggle_action(self):
        if not self.engine.is_running:
            # 开始录制
            self.status_label.configure(text="● RECORDING...", text_color="#e74c3c")
            self.btn_main.configure(text="STOP AND SAVE", fg_color="#e74c3c", hover_color="#c0392b")
            
            # 在单独线程启动引擎，防止 UI 挂起
            self.record_thread = Thread(target=self.engine.run)
            self.record_thread.start()
        else:
            # 停止录制
            self.engine.is_running = False
            self.status_label.configure(text="Saving file... please wait", text_color="#f1c40f")
            self.btn_main.configure(state="disabled")
            
            # 检查线程结束
            self.check_thread_done()

    def check_thread_done(self):
        if self.record_thread.is_alive():
            self.after(500, self.check_thread_done)
        else:
            self.btn_main.configure(state="normal", text="START RECORDING", fg_color="#27ae60", hover_color="#219150")
            self.status_label.configure(text=f"Saved: {self.engine.output_file}", text_color="#2ecc71")

if __name__ == "__main__":
    app = App()
    app.mainloop()
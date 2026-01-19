"""
音频录制模块
支持四种录制模式：不录音频、仅系统声音、仅麦克风、麦克风和系统
"""
import numpy as np
import wave
import time
from threading import Thread, Lock
import os
from utils.locale_manager import locale_manager

try:
    import pyaudiowpatch as pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


class AudioRecorder:
    """音频录制管理类"""
    
    # 音频模式常量
    MODE_NONE = "none"
    MODE_SYSTEM = "system"
    MODE_MICROPHONE = "microphone"
    MODE_BOTH = "both"
    
    def __init__(self, mode=MODE_NONE, sample_rate=44100, channels=2,
                 system_volume=1.0, mic_volume=1.0):
        """
        初始化音频录制器
        
        Args:
            mode: 录制模式 (none/system/microphone/both)
            sample_rate: 采样率，默认44100Hz
            channels: 声道数，默认2（立体声）
            system_volume: 系统音量增益，默认1.0（范围0.0-3.0）
            mic_volume: 麦克风音量增益，默认1.0（范围0.0-3.0）
        """
        self.mode = mode
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        
        # 音量增益参数
        self.system_volume = max(0.0, min(3.0, system_volume))
        self.mic_volume = max(0.0, min(3.0, mic_volume))
        
        # 音频数据缓冲区
        self.system_audio_data = []
        self.mic_audio_data = []
        self.data_lock = Lock()
        self.paused = False
        self.pause_start_timestamp = 0


        
        # 录制线程
        self.system_thread = None
        self.mic_thread = None
        
        # 输出文件路径
        self.output_file = ""
        self.start_time = None
        
        # 实际系统音频采样率
        self.system_sample_rate = None
        
    def set_start_time(self):
        """设置录制开始时间，用于音画同步"""
        self.start_time = time.time()
        print(locale_manager.get_text("log_audio_sync_time").format(self.start_time))

    def pause(self):
        """暂停录制"""
        self.paused = True
        self.pause_start_timestamp = time.time()

    def resume(self):
        """恢复录制"""
        if self.paused and self.start_time is not None and self.pause_start_timestamp > 0:
            pause_duration = time.time() - self.pause_start_timestamp
            self.start_time += pause_duration
            print(f"Resuming audio: adjusted start_time by {pause_duration:.2f}s")
            
        self.paused = False
        self.pause_start_timestamp = 0


    def start_recording(self, output_file):
        """
        启动音频录制
        
        Args:
            output_file: 输出音频文件路径
        """
        if self.mode == self.MODE_NONE:
            return True
            
        self.output_file = output_file
        self.is_recording = True
        self.paused = False
        self.pause_start_timestamp = 0
        self.start_time = None
        
        try:
            if self.mode == self.MODE_SYSTEM:
                return self._start_system_recording()
            elif self.mode == self.MODE_MICROPHONE:
                return self._start_microphone_recording()
            elif self.mode == self.MODE_BOTH:
                return self._start_mixed_recording()
        except Exception as e:
            print(locale_manager.get_text("log_audio_start_error").format(e))
            self.is_recording = False
            return False
            
        return True
    
    def stop_recording(self):
        """停止音频录制并保存文件"""
        if self.mode == self.MODE_NONE or not self.is_recording:
            return True
            
        self.is_recording = False
        
        # 等待录制线程结束
        if self.system_thread and self.system_thread.is_alive():
            self.system_thread.join(timeout=2.0)
        if self.mic_thread and self.mic_thread.is_alive():
            self.mic_thread.join(timeout=2.0)
        
        # 保存音频数据
        try:
            return self._save_audio_file()
        except Exception as e:
            print(locale_manager.get_text("log_audio_save_error").format(e))
            return False
    
    def _start_system_recording(self):
        """启动系统音频录制（WASAPI loopback）"""
        if not PYAUDIO_AVAILABLE:
            print(locale_manager.get_text("log_pyaudio_missing"))
            return False
            
        self.system_thread = Thread(target=self._record_system_audio, daemon=True)
        self.system_thread.start()
        return True
    
    def _start_microphone_recording(self):
        """启动麦克风录制"""
        """启动麦克风录制"""
        if not SOUNDDEVICE_AVAILABLE:
            print(locale_manager.get_text("log_sounddevice_missing"))
            return False
        
        # 验证是否有可用设备
        devices = AudioRecorder.get_input_devices()
        if not devices:
            print(locale_manager.get_text("log_no_input_device"))
            print(locale_manager.get_text("log_run_diagnosis"))
            AudioRecorder.diagnose_audio_devices()
            return False
            
        self.mic_thread = Thread(target=self._record_microphone, daemon=True)
        self.mic_thread.start()
        return True
    
    def _start_mixed_recording(self):
        """启动混合录制（系统+麦克风）"""
        if not PYAUDIO_AVAILABLE or not SOUNDDEVICE_AVAILABLE:
            print(locale_manager.get_text("log_libs_missing_mixed"))
            return False
            
        self.system_thread = Thread(target=self._record_system_audio, daemon=True)
        self.mic_thread = Thread(target=self._record_microphone, daemon=True)
        
        self.system_thread.start()
        self.mic_thread.start()
        return True
    
    def _record_system_audio(self):
        """录制系统音频（使用 WASAPI loopback）"""
        try:
            p = pyaudio.PyAudio()
            
            # 尝试获取 WASAPI loopback 设备
            try:
                wasapi_info = p.get_default_wasapi_loopback()
                device_index = wasapi_info["index"]
                channels = wasapi_info["maxInputChannels"]
                rate = int(wasapi_info["defaultSampleRate"])
            except AttributeError:
                # 如果不支持 WASAPI，使用默认输入设备
                device_info = p.get_default_input_device_info()
                device_index = device_info["index"]
                channels = min(2, device_info["maxInputChannels"])
                rate = int(device_info["defaultSampleRate"])
            
            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            
            self.system_sample_rate = rate
            print(locale_manager.get_text("log_system_audio_started").format(rate, channels))
            
            # 计算每字节的时间（用于补齐静音）
            bytes_per_frame = channels * 2  # 16-bit = 2 bytes
            total_bytes_read = 0
            
            # 等待开始时间设置
            while self.is_recording and self.start_time is None:
                try:
                    # 读取并丢弃数据，保持流的活性
                    stream.read(1024, exception_on_overflow=False)
                except:
                    pass
                time.sleep(0.001)
            
            while self.is_recording:
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    
                    if self.start_time is None:
                        continue

                    # 计算理论上应该有的数据量
                    elapsed_time = time.time() - self.start_time
                    expected_bytes = int(elapsed_time * rate * bytes_per_frame)
                    # 确保是帧大小的整数倍，防止 buffer size 错误
                    expected_bytes -= expected_bytes % bytes_per_frame
                    
                    with self.data_lock:
                        # 如果实际读取的数据远少于理论数据，说明中间有静音（WASAPI loopback特性）
                        # 允许一定的误差（例如 0.1秒）
                        if expected_bytes > total_bytes_read + len(data) + (rate * bytes_per_frame * 0.1):
                            missing_bytes = expected_bytes - (total_bytes_read + len(data))
                            # 补齐静音
                            silence = b'\x00' * missing_bytes
                            self.system_audio_data.append(silence)
                            total_bytes_read += missing_bytes
                            
                        if not self.paused:
                            self.system_audio_data.append(data)
                            total_bytes_read += len(data)

                        
                except Exception as e:
                    print(locale_manager.get_text("log_read_system_audio_error").format(e))
                    break
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            print(locale_manager.get_text("log_system_audio_stopped"))
            
        except Exception as e:
            print(locale_manager.get_text("log_system_audio_record_error").format(e))
            self.is_recording = False
    
    def _record_microphone(self):
        """录制麦克风音频"""
        try:
            # 选择输入设备
            device_index = AudioRecorder.select_best_input_device()
            
            if device_index is None:
                print(locale_manager.get_text("log_no_input_device"))
                print(locale_manager.get_text("log_check_mic_permission"))
                self.is_recording = False
                return
            
            # 获取设备信息
            try:
                device_info = sd.query_devices(device_index)
                print(locale_manager.get_text("log_using_device").format(device_info['name'], device_index))
            except Exception as e:
                print(locale_manager.get_text("log_get_device_info_warning").format(e))
            
            def callback(indata, frames, time_info, status):
                if self.start_time is None or self.paused:
                    return
                    
                if status:
                    print(locale_manager.get_text("log_mic_status").format(status))
                with self.data_lock:
                    self.mic_audio_data.append(indata.copy())
            
            # 显式指定设备
            with sd.InputStream(
                device=device_index,  # 添加设备参数
                samplerate=self.sample_rate,
                channels=1,  # 麦克风通常使用单声道
                callback=callback,
                dtype='int16'
            ):
                print(locale_manager.get_text("log_mic_started").format(self.sample_rate))
                while self.is_recording:
                    sd.sleep(100)
            
            print(locale_manager.get_text("log_mic_stopped"))
            
        except Exception as e:
            print(locale_manager.get_text("log_mic_record_error").format(e))
            print(locale_manager.get_text("log_check_mic_permission"))
            self.is_recording = False
    
    def _save_audio_file(self):
        """保存音频数据到 WAV 文件"""
        if not self.output_file:
            return False
        
        try:
            # 根据模式处理音频数据
            if self.mode == self.MODE_SYSTEM:
                audio_data = self._process_system_audio()
            elif self.mode == self.MODE_MICROPHONE:
                audio_data = self._process_microphone_audio()
            elif self.mode == self.MODE_BOTH:
                audio_data = self._process_mixed_audio()
            else:
                return False
            
            if audio_data is None or len(audio_data) == 0:
                print(locale_manager.get_text("log_no_audio_data"))
                return False
            
            # 保存为 WAV 文件
            with wave.open(self.output_file, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data)
            
            print(locale_manager.get_text("log_audio_saved").format(self.output_file))
            return True
            
        except Exception as e:
            print(locale_manager.get_text("log_audio_save_error").format(e))
            return False
    
    def _process_system_audio(self):
        """处理系统音频数据"""
        with self.data_lock:
            if not self.system_audio_data:
                return None
            
            # 应用音量增益
            if self.system_volume != 1.0:
                audio_bytes = b''.join(self.system_audio_data)
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                # 应用增益并限制在int16范围内
                audio_array = audio_array.astype(np.float32) * self.system_volume
                audio_array = np.clip(audio_array, -32768, 32767).astype(np.int16)
                return audio_array.tobytes()
            else:
                audio_bytes = b''.join(self.system_audio_data)
                
            # 重采样处理
            if self.system_sample_rate and self.system_sample_rate != self.sample_rate:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                audio_array = self._resample_audio(audio_array, self.system_sample_rate, self.sample_rate)
                return audio_array.tobytes()
                
            return audio_bytes
    
    def _resample_audio(self, audio_data, original_rate, target_rate):
        """
        重采样音频数据
        
        Args:
            audio_data: int16 numpy array
            original_rate: 原始采样率
            target_rate: 目标采样率
            
        Returns:
            int16 numpy array
        """
        if original_rate == target_rate or len(audio_data) == 0:
            return audio_data
            
        duration = len(audio_data) / original_rate
        target_length = int(duration * target_rate)
        
        # 使用线性插值进行重采样
        x_old = np.linspace(0, duration, len(audio_data))
        x_new = np.linspace(0, duration, target_length)
        
        resampled_data = np.interp(x_new, x_old, audio_data.astype(np.float32))
        return resampled_data.astype(np.int16)
    
    def _process_microphone_audio(self):
        """处理麦克风音频数据"""
        with self.data_lock:
            if not self.mic_audio_data:
                return None
            
            # 将 numpy 数组转换为字节
            audio_array = np.concatenate(self.mic_audio_data, axis=0)
            
            # 应用音量增益
            if self.mic_volume != 1.0:
                audio_array = audio_array.astype(np.float32) * self.mic_volume
                audio_array = np.clip(audio_array, -32768, 32767).astype(np.int16)
            
            # 如果需要立体声，复制单声道到两个声道
            if self.channels == 2:
                audio_array = np.column_stack((audio_array, audio_array))
            
            return audio_array.tobytes()
    
    def _process_mixed_audio(self):
        """处理混合音频数据（系统+麦克风）"""
        with self.data_lock:
            if not self.system_audio_data and not self.mic_audio_data:
                return None
            
            # 处理系统音频
            if self.system_audio_data:
                system_bytes = b''.join(self.system_audio_data)
                system_array = np.frombuffer(system_bytes, dtype=np.int16).astype(np.float32)
                
                # 重采样系统音频以匹配目标采样率
                if self.system_sample_rate and self.system_sample_rate != self.sample_rate:
                    # 注意：此时 system_array 已经是 float32
                    duration = len(system_array) / self.system_sample_rate
                    target_length = int(duration * self.sample_rate)
                    x_old = np.linspace(0, duration, len(system_array))
                    x_new = np.linspace(0, duration, target_length)
                    system_array = np.interp(x_new, x_old, system_array)
                
                # 应用系统音量增益
                system_array = system_array * self.system_volume
            else:
                system_array = np.array([], dtype=np.float32)
            
            # 处理麦克风音频
            if self.mic_audio_data:
                mic_array = np.concatenate(self.mic_audio_data, axis=0).flatten().astype(np.float32)
                # 应用麦克风音量增益
                mic_array = mic_array * self.mic_volume
                # 将单声道扩展为立体声
                mic_array = np.repeat(mic_array, 2)
            else:
                mic_array = np.array([], dtype=np.float32)
            
            # 对齐长度，取最大长度，短的补静音
            max_len = max(len(system_array), len(mic_array))
            
            if max_len == 0:
                return None
                
            # 补齐系统音频
            if len(system_array) < max_len:
                padding = np.zeros(max_len - len(system_array), dtype=np.float32)
                system_array = np.concatenate((system_array, padding))
                
            # 补齐麦克风音频
            if len(mic_array) < max_len:
                padding = np.zeros(max_len - len(mic_array), dtype=np.float32)
                mic_array = np.concatenate((mic_array, padding))
            
            # 混合音频（平均混合）
            mixed_array = (system_array + mic_array) / 2
            
            # 限制在int16范围内并转换
            mixed_array = np.clip(mixed_array, -32768, 32767).astype(np.int16)
            return mixed_array.tobytes()
    
    @staticmethod
    def get_input_devices():
        """获取所有可用的输入设备"""
        if not SOUNDDEVICE_AVAILABLE:
            return []
        
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, device in enumerate(device_list):
                if device['max_input_channels'] > 0:
                    devices.append({
                        'index': idx,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': device['default_samplerate']
                    })
        except Exception as e:
            print(locale_manager.get_text("log_query_device_fail").format(e))
        
        return devices
    
    @staticmethod
    def select_best_input_device():
        """选择最佳的输入设备"""
        if not SOUNDDEVICE_AVAILABLE:
            return None
        
        devices = AudioRecorder.get_input_devices()
        
        if not devices:
            return None
        
        # 优先级策略：
        # 1. 查找名称包含 "麦克风" 或 "Microphone" 的设备
        # 2. 使用系统默认输入设备
        # 3. 使用第一个可用的输入设备
        
        for device in devices:
            name_lower = device['name'].lower()
            if 'microphone' in name_lower or '麦克风' in name_lower or 'mic' in name_lower:
                print(locale_manager.get_text("log_found_mic").format(device['name']))
                return device['index']
        
        # 尝试获取默认设备
        try:
            default_device = sd.query_devices(kind='input')
            if default_device['max_input_channels'] > 0:
                print(locale_manager.get_text("log_using_default_device").format(default_device['name']))
                return default_device['index']
        except Exception as e:
            print(locale_manager.get_text("log_get_default_device_fail").format(e))
        
        # 返回第一个可用设备
        if devices:
            print(locale_manager.get_text("log_using_first_device").format(devices[0]['name']))
            return devices[0]['index']
        
        return None
    
    @staticmethod
    def diagnose_audio_devices():
        """诊断音频设备配置"""
        print("\n=== 音频设备诊断 ===")
        
        if not SOUNDDEVICE_AVAILABLE:
            print("❌ sounddevice 库未安装")
            print("   请运行: pip install sounddevice")
            return
        
        print("✓ sounddevice 库已安装")
        
        try:
            devices = sd.query_devices()
            print(f"\n检测到 {len(devices)} 个音频设备：")
            
            input_count = 0
            for idx, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    input_count += 1
                    print(f"  [{idx}] {device['name']}")
                    print(f"      输入通道: {device['max_input_channels']}")
                    print(f"      采样率: {device['default_samplerate']} Hz")
            
            if input_count == 0:
                print("\n❌ 未找到可用的输入设备")
                print("   请检查：")
                print("   1. 麦克风是否正确连接")
                print("   2. 系统音频设置中是否启用了输入设备")
                print("   3. 应用程序是否有麦克风访问权限")
                print("      Windows: 设置 → 隐私 → 麦克风")
            else:
                print(f"\n✓ 找到 {input_count} 个输入设备")
                
            # 检查默认设备
            try:
                default_input = sd.query_devices(kind='input')
                print(f"\n默认输入设备: {default_input['name']} (索引: {default_input['index']})")
            except Exception as e:
                print(f"\n⚠ 无法获取默认输入设备: {e}")
                
        except Exception as e:
            print(f"\n❌ 设备查询失败: {e}")
        
        print("===================\n")
    
    @staticmethod
    def check_audio_support():
        """检查音频库支持情况"""
        support_info = {
            'pyaudio': PYAUDIO_AVAILABLE,
            'sounddevice': SOUNDDEVICE_AVAILABLE,
            'system_audio': PYAUDIO_AVAILABLE,
            'microphone': SOUNDDEVICE_AVAILABLE,
            'mixed': PYAUDIO_AVAILABLE and SOUNDDEVICE_AVAILABLE
        }
        return support_info
    
    @staticmethod
    def get_available_modes():
        """获取可用的录制模式"""
        modes = [AudioRecorder.MODE_NONE]
        
        if PYAUDIO_AVAILABLE:
            modes.append(AudioRecorder.MODE_SYSTEM)
        
        if SOUNDDEVICE_AVAILABLE:
            modes.append(AudioRecorder.MODE_MICROPHONE)
        
        if PYAUDIO_AVAILABLE and SOUNDDEVICE_AVAILABLE:
            modes.append(AudioRecorder.MODE_BOTH)
        
        return modes

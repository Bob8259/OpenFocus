"""
音频设备诊断工具
用于测试和诊断麦克风录制问题
"""
import sys

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    import pyaudiowpatch as pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False


def diagnose_sounddevice():
    """诊断 sounddevice 音频设备"""
    print("\n" + "="*60)
    print("SoundDevice 音频设备诊断")
    print("="*60)
    
    if not SOUNDDEVICE_AVAILABLE:
        print("❌ sounddevice 库未安装")
        print("   安装命令: pip install sounddevice")
        return
    
    print("✓ sounddevice 库已安装")
    print(f"   版本: {sd.__version__}")
    
    try:
        devices = sd.query_devices()
        print(f"\n检测到 {len(devices)} 个音频设备：\n")
        
        input_devices = []
        output_devices = []
        
        for idx, device in enumerate(devices):
            device_type = []
            if device['max_input_channels'] > 0:
                device_type.append("输入")
                input_devices.append((idx, device))
            if device['max_output_channels'] > 0:
                device_type.append("输出")
                output_devices.append((idx, device))
            
            type_str = "/".join(device_type) if device_type else "未知"
            
            print(f"[{idx}] {device['name']}")
            print(f"    类型: {type_str}")
            if device['max_input_channels'] > 0:
                print(f"    输入通道: {device['max_input_channels']}")
            if device['max_output_channels'] > 0:
                print(f"    输出通道: {device['max_output_channels']}")
            print(f"    默认采样率: {device['default_samplerate']} Hz")
            print()
        
        # 统计信息
        print("-" * 60)
        print(f"✓ 输入设备数量: {len(input_devices)}")
        print(f"✓ 输出设备数量: {len(output_devices)}")
        
        # 检查默认设备
        print("\n默认设备信息：")
        try:
            default_input = sd.query_devices(kind='input')
            print(f"  默认输入: [{default_input['index']}] {default_input['name']}")
        except Exception as e:
            print(f"  ⚠ 无法获取默认输入设备: {e}")
        
        try:
            default_output = sd.query_devices(kind='output')
            print(f"  默认输出: [{default_output['index']}] {default_output['name']}")
        except Exception as e:
            print(f"  ⚠ 无法获取默认输出设备: {e}")
        
        # 麦克风设备推荐
        if input_devices:
            print("\n推荐的麦克风设备：")
            for idx, device in input_devices:
                name_lower = device['name'].lower()
                if 'microphone' in name_lower or '麦克风' in name_lower or 'mic' in name_lower:
                    print(f"  ✓ [{idx}] {device['name']}")
        else:
            print("\n❌ 未找到可用的输入设备")
            print("\n故障排除建议：")
            print("  1. 检查麦克风是否正确连接到电脑")
            print("  2. 在系统设置中启用麦克风设备")
            print("     Windows: 设置 → 系统 → 声音 → 输入")
            print("  3. 检查应用程序麦克风权限")
            print("     Windows: 设置 → 隐私 → 麦克风")
            print("  4. 重启音频服务或重启电脑")
            
    except Exception as e:
        print(f"\n❌ 设备查询失败: {e}")
        print(f"   错误类型: {type(e).__name__}")


def diagnose_pyaudio():
    """诊断 PyAudio 音频设备"""
    print("\n" + "="*60)
    print("PyAudio 音频设备诊断")
    print("="*60)
    
    if not PYAUDIO_AVAILABLE:
        print("❌ pyaudio/pyaudiowpatch 库未安装")
        print("   安装命令: pip install pyaudiowpatch")
        return
    
    print("✓ PyAudio 库已安装")
    
    try:
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()
        print(f"\n检测到 {device_count} 个音频设备：\n")
        
        input_devices = []
        
        for i in range(device_count):
            try:
                info = p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    input_devices.append((i, info))
                    print(f"[{i}] {info['name']}")
                    print(f"    输入通道: {info['maxInputChannels']}")
                    print(f"    采样率: {info['defaultSampleRate']} Hz")
                    print()
            except Exception as e:
                print(f"[{i}] 无法获取设备信息: {e}")
        
        print("-" * 60)
        print(f"✓ 输入设备数量: {len(input_devices)}")
        
        # 检查 WASAPI loopback
        try:
            wasapi_info = p.get_default_wasapi_loopback()
            print(f"\n✓ WASAPI Loopback 可用")
            print(f"  设备: {wasapi_info['name']}")
            print(f"  (用于录制系统声音)")
        except AttributeError:
            print("\n⚠ WASAPI Loopback 不可用")
            print("  提示: 使用 pyaudiowpatch 而不是 pyaudio 以支持系统音频录制")
        except Exception as e:
            print(f"\n⚠ WASAPI Loopback 检查失败: {e}")
        
        p.terminate()
        
    except Exception as e:
        print(f"\n❌ PyAudio 初始化失败: {e}")


def test_microphone_recording():
    """测试麦克风录制"""
    print("\n" + "="*60)
    print("麦克风录制测试")
    print("="*60)
    
    if not SOUNDDEVICE_AVAILABLE:
        print("❌ sounddevice 未安装，无法测试")
        return
    
    try:
        # 获取输入设备
        devices = []
        device_list = sd.query_devices()
        for idx, device in enumerate(device_list):
            if device['max_input_channels'] > 0:
                devices.append({'index': idx, 'name': device['name']})
        
        if not devices:
            print("❌ 未找到可用的输入设备")
            return
        
        # 选择设备
        print("\n可用的输入设备：")
        for i, dev in enumerate(devices):
            print(f"  {i+1}. [{dev['index']}] {dev['name']}")
        
        print("\n正在使用第一个设备进行测试...")
        device_index = devices[0]['index']
        device_info = sd.query_devices(device_index)
        print(f"测试设备: {device_info['name']}")
        
        # 尝试打开流
        print("\n尝试打开音频流...")
        with sd.InputStream(
            device=device_index,
            samplerate=44100,
            channels=1,
            dtype='int16'
        ):
            print("✓ 音频流打开成功！")
            print("  麦克风设备工作正常")
            print("  可以开始录制")
        
    except Exception as e:
        print(f"\n❌ 麦克风测试失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        print("\n可能的原因：")
        print("  1. 设备被其他应用程序占用")
        print("  2. 没有麦克风访问权限")
        print("  3. 设备驱动程序问题")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("音频设备诊断工具")
    print("="*60)
    print("\n此工具将帮助您诊断麦克风录制问题\n")
    
    # 检查库安装情况
    print("库安装状态：")
    print(f"  sounddevice: {'✓ 已安装' if SOUNDDEVICE_AVAILABLE else '❌ 未安装'}")
    print(f"  pyaudio:     {'✓ 已安装' if PYAUDIO_AVAILABLE else '❌ 未安装'}")
    
    # 运行诊断
    diagnose_sounddevice()
    diagnose_pyaudio()
    test_microphone_recording()
    
    print("\n" + "="*60)
    print("诊断完成")
    print("="*60)
    print("\n如果仍然遇到问题，请：")
    print("  1. 确保麦克风已正确连接")
    print("  2. 检查系统音频设置")
    print("  3. 授予应用程序麦克风权限")
    print("  4. 尝试重启音频服务或重启电脑")
    print()


if __name__ == "__main__":
    main()

"""
音视频合并工具模块
使用 FFmpeg 合并视频和音频文件
"""
import os
import subprocess
import shutil


class VideoAudioMerger:
    """音视频合并工具类"""
    
    @staticmethod
    def check_ffmpeg():
        """检查 FFmpeg 是否可用"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def merge_files(video_file, audio_file, output_file, cleanup=True):
        """
        合并视频和音频文件
        
        Args:
            video_file: 输入视频文件路径
            audio_file: 输入音频文件路径
            output_file: 输出文件路径
            cleanup: 是否清理临时文件
            
        Returns:
            bool: 合并是否成功
        """
        if not os.path.exists(video_file):
            print(f"视频文件不存在: {video_file}")
            return False
        
        if not os.path.exists(audio_file):
            print(f"音频文件不存在: {audio_file}")
            return False
        
        if not VideoAudioMerger.check_ffmpeg():
            print("FFmpeg 未安装或不可用")
            print("请从 https://ffmpeg.org/download.html 下载并安装 FFmpeg")
            return False
        
        try:
            # 构建 FFmpeg 命令
            # -i: 输入文件
            # -c:v copy: 复制视频流（不重新编码）
            # -c:a aac: 使用 AAC 编码音频
            # -strict experimental: 允许实验性编码器
            # -y: 覆盖输出文件
            command = [
                'ffmpeg',
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-strict', 'experimental',
                '-y',
                output_file
            ]
            
            print(f"正在合并音视频文件...")
            print(f"视频: {video_file}")
            print(f"音频: {audio_file}")
            print(f"输出: {output_file}")
            
            # 执行 FFmpeg 命令
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                print("音视频合并成功")
                
                # 清理临时文件
                if cleanup:
                    VideoAudioMerger.cleanup_temp_files(video_file, audio_file)
                
                return True
            else:
                print(f"FFmpeg 错误: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("FFmpeg 执行超时")
            return False
        except Exception as e:
            print(f"合并文件时发生错误: {e}")
            return False
    
    @staticmethod
    def cleanup_temp_files(*files):
        """
        清理临时文件
        
        Args:
            *files: 要删除的文件路径列表
        """
        for file_path in files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"已删除临时文件: {file_path}")
            except Exception as e:
                print(f"删除文件失败 {file_path}: {e}")
    
    @staticmethod
    def merge_with_fallback(video_file, audio_file, output_file):
        """
        带降级策略的合并方法
        如果 FFmpeg 不可用，则只保留视频文件
        
        Args:
            video_file: 输入视频文件路径
            audio_file: 输入音频文件路径
            output_file: 输出文件路径
            
        Returns:
            tuple: (success, final_file)
        """
        # 尝试使用 FFmpeg 合并
        if VideoAudioMerger.merge_files(video_file, audio_file, output_file, cleanup=True):
            return True, output_file
        
        # 如果合并失败，使用视频文件作为输出
        print("音视频合并失败，将只保留视频文件")
        try:
            if os.path.exists(output_file):
                os.remove(output_file)
            shutil.move(video_file, output_file)
            
            # 清理音频文件
            if os.path.exists(audio_file):
                os.remove(audio_file)
            
            return True, output_file
        except Exception as e:
            print(f"文件处理错误: {e}")
            return False, video_file

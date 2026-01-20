# OpenFocus

[English](https://github.com/Bob8259/OpenFocus) | 简体中文

---

# AI 智能录屏系统 - 音频录制功能

## 概览

本系统是一款智能录屏工具，支持点击缩放效果和多种音频录制模式。

### 免责声明
*本项目中的代码主要由 AI 生成。使用前请仔细检查！*

### 核心功能

- ✅ 智能点击缩放效果
- ✅ 平滑的摄像头移动
- ✅ 鼠标指针显示及点击动画效果
- ✅ **鼠标拖拽选择录制区域**
- ✅ **四种音频录制模式**：
  - 无音频
  - 仅系统声音
  - 仅麦克风
  - 混合麦克风和系统声音

## 安装

### 运行要求
- 本应用程序仅适用于 **Windows**，推荐使用 **Windows 11**。

### 直接下载
- 您可以直接从 [Releases](https://github.com/Bob8259/OpenFocus/releases) 下载可执行文件。

### 使用指南

1. **录制区域**：
   - 默认为全屏录制。
   - 点击“选择录制区域”按钮，拖动鼠标选择自定义区域。
   - 您可以重新选择区域或恢复全屏。
2. **缩放倍数**：设置点击时的放大倍数（1.0-2.5x）。
3. **平滑速度**：设置摄像头移动的平滑度（0.05-0.5）。平滑速度越高，画面跟随鼠标移动的速度越快。
4. **缩放持续时间**：设置缩放效果的持续时间（0.3-3.0 秒）。
5. **音频录制模式**：选择音频录制方式。
   - **无音频**：仅录制视频。
   - **仅系统声音**：录制电脑播放的所有声音。
   - **仅麦克风**：录制麦克风输入的声音。
   - **麦克风和系统**：同时录制并混合两者。
6. **键盘快捷键**：`Ctrl+F1` 开始录制，`Ctrl+F2` 停止并保存录制。

（文件将以 `Record_时间戳.mp4` 的形式保存在程序目录下。）

### DIY 安装
如果您想从源码运行或自定义代码：

#### 1. 创建 Conda 环境
```bash
conda create -n OpenFocus python=3.10
conda activate OpenFocus
```

#### 2. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

#### 3. 安装 FFmpeg（音频合并所需）

**Windows:**
1. 访问 [FFmpeg 官方网站](https://ffmpeg.org/download.html)
2. 下载 Windows 版本
3. 解压到任意目录（例如 `C:/ffmpeg`）
4. 将 `C:/ffmpeg/bin` 添加到系统环境变量 PATH 中
5. 验证安装：打开命令提示符并输入 `ffmpeg -version`

**快速安装（使用 Chocolatey）：**
```bash
choco install ffmpeg
```

#### 启动程序
```bash
python main.py
```

#### 构建 EXE（可选）
```bash
pip install pyinstaller
pyinstaller main.spec
```

## 技术架构

### 核心逻辑

OpenFocus 采用高性能、多阶段的流水线设计，以保证效率和视觉质量：

1.  **高速捕获**：使用高性能的录制引擎实现屏幕捕捉。
2.  **同步日志**：实时记录鼠标移动、点击和窗口事件。
3.  **智能后处理**：
    *   动态点击缩放效果。
    *   平滑的摄像头追踪和稳定。
    *   虚拟高保真光标渲染。
4.  **自动组装**：无缝合并高质量视频与同步的系统及麦克风音频。

### 技术栈

- **UI 框架**：CustomTkinter
- **视频处理**：OpenCV, mss
- **音频录制**：pyaudiowpatch
- **合并**：FFmpeg
- **输入监听**：pynput

## 许可证

Copyright 2026 Azikaban/Bob8259

本项目采用 Apache License 2.0 许可证。

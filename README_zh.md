# OpenFocus

[English](https://github.com/Bob8259/OpenFocus) | 简体中文

---

# AI 智能录屏系统 - 音频录制功能

## 概述

本系统是一款智能录屏工具，支持点击缩放效果和多种音频录制模式。

### 声明
*本项目代码主要由AI生成，使用前请仔细检查！*

### 主要功能

- ✅ 智能点击缩放效果
- ✅ 平滑的镜头移动
- ✅ 鼠标指针显示，与点击动画效果
- ✅ **鼠标拖拽选择录制区域**
- ✅ **四种音频录制模式**：
  - 无音频
  - 仅系统声音
  - 仅麦克风
  - 麦克风与系统声音

## 安装

### 环境要求
- 本应用仅适用于 **Windows**，建议使用 **Windows 11**。

### 直接下载
- 您可以直接从 [Releases](https://github.com/Bob8259/OpenFocus/releases) 下载可执行文件。

### 使用指南

1. **录制区域**：
   - 默认为全屏录制。
   - 点击“选择录制区域”按钮并拖动鼠标以选择自定义区域。
   - 您可以重新选择区域或恢复全屏。
2. **缩放倍率**：设置点击时的放大倍数（1.0-2.5x）。
3. **平滑速度**：设置镜头移动的平滑度（0.05-0.5）。平滑速度越高，屏幕跟随鼠标移动的速度越快。
4. **缩放时长**：设置缩放效果持续的时间（0.3-3.0 秒）。
5. **音频录制模式**：选择如何录制音频。
   - **无音频**：仅录制视频。
   - **仅系统声音**：录制电脑播放的所有声音。
   - **仅麦克风**：录制麦克风输入的声音。
   - **麦克风与系统**：同时录制两者并进行混音。
6. **快捷键**：`Ctrl+F1` 开始录制，`Ctrl+F2` 停止并保存录制。

（文件保存在程序目录下，命名为 `Record_时间戳.mp4`。）

### DIY 安装
如果您想从源码运行或自定义代码：

#### 1. 创建 Conda 环境
```bash
conda create -n OpenFoucs python=3.10
conda activate OpenFoucs
```

#### 2. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

#### 3. 安装 FFmpeg（音频合并所需）

**Windows:**
1. 访问 [FFmpeg 官方网站](https://ffmpeg.org/download.html)
2. 下载 Windows 构建版本
3. 解压到任意目录（例如 `C:/ffmpeg`）
4. 将 `C:/ffmpeg/bin` 添加到系统 PATH 环境变量中
5. 验证安装：打开命令提示符并输入 `ffmpeg -version`

**快速安装（使用 Chocolatey）：**
```bash
choco install ffmpeg
```

#### 启动程序
```bash
python main.py
```
#### 构建EXE
```bash
pip install pyinstaller
pyinstaller main.spec
```

## 技术架构

### 核心逻辑

系统遵循简单的工作流程：分别录制视频和音频流，然后使用 FFmpeg 将它们合并为单个输出。

### 局限性
**本项目并非使用 C/C++ 实现；因此，它主要用于个人使用，可能不适合性能要求极高或生产环境。**

本项目可能存在bug，尤其是录制“麦克风和系统声音”模式。

### 技术栈

- **UI 框架**：CustomTkinter
- **视频处理**：OpenCV, mss
- **音频录制**：pyaudiowpatch
- **合并**：FFmpeg
- **输入监听**：pynput

## 许可证
Copyright 2026 Azikaban/Bob8259

根据 Apache License, Version 2.0（“许可证”）授权。

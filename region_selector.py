"""
区域选择器模块
允许用户通过鼠标拖拽选择录屏区域
"""
import tkinter as tk
from PIL import ImageGrab, ImageTk
import pyautogui
from utils.locale_manager import locale_manager


class RegionSelector:
    """区域选择器 - 全屏半透明窗口，支持鼠标拖拽选择区域"""
    
    def __init__(self):
        self.selected_region = None  # 存储选择的区域 (x, y, width, height)
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.root = None
        self.canvas = None
        
    def select_region(self):
        """显示区域选择窗口，返回选择的区域"""
        self.selected_region = None
        
        # 创建全屏窗口
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)  # 半透明
        self.root.attributes('-topmost', True)  # 置顶
        self.root.configure(bg='black')
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 创建画布
        self.canvas = tk.Canvas(
            self.root, 
            width=screen_width, 
            height=screen_height,
            bg='black',
            highlightthickness=0,
            cursor='cross'
        )
        self.canvas.pack()
        
        # 添加提示文字
        self.canvas.create_text(
            screen_width // 2,
            50,
            text=locale_manager.get_text("region_select_hint"),
            fill='white',
            font=('Arial', 20, 'bold')
        )
        
        # 绑定鼠标事件
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        
        # 绑定键盘事件
        self.root.bind('<Escape>', lambda e: self.cancel_selection())
        
        # 运行窗口
        self.root.mainloop()
        
        return self.selected_region
    
    def on_mouse_down(self, event):
        """鼠标按下 - 记录起始位置"""
        self.start_x = event.x
        self.start_y = event.y
        
        # 删除之前的矩形
        if self.rect_id:
            self.canvas.delete(self.rect_id)
    
    def on_mouse_drag(self, event):
        """鼠标拖拽 - 绘制选择矩形"""
        if self.start_x is None or self.start_y is None:
            return
        
        # 删除之前的矩形
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        
        # 绘制新矩形
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            event.x, event.y,
            outline='red',
            width=3,
            fill='white',
            stipple='gray50'  # 半透明填充
        )
        
        # 显示尺寸信息
        width = abs(event.x - self.start_x)
        height = abs(event.y - self.start_y)
        
        # 删除之前的文字
        self.canvas.delete('size_text')
        
        # 显示尺寸
        mid_x = (self.start_x + event.x) / 2
        mid_y = (self.start_y + event.y) / 2
        self.canvas.create_text(
            mid_x, mid_y,
            text=locale_manager.get_text("region_size_text").format(width, height),
            fill='yellow',
            font=('Arial', 16, 'bold'),
            tags='size_text'
        )
    
    def on_mouse_up(self, event):
        """鼠标释放 - 确认选择"""
        if self.start_x is None or self.start_y is None:
            return
        
        # 计算选择的区域
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        width = x2 - x1
        height = y2 - y1
        
        # 确保区域有效（至少 50x50 像素）
        if width >= 50 and height >= 50:
            self.selected_region = {
                'left': x1,
                'top': y1,
                'width': width,
                'height': height
            }
            self.root.quit()
            self.root.destroy()
        else:
            # 区域太小，提示用户
            self.canvas.delete('error_text')
            self.canvas.create_text(
                self.root.winfo_screenwidth() // 2,
                100,
                text=locale_manager.get_text("region_too_small"),
                fill='red',
                font=('Arial', 16, 'bold'),
                tags='error_text'
            )
            # 重置
            self.start_x = None
            self.start_y = None
            if self.rect_id:
                self.canvas.delete(self.rect_id)
                self.rect_id = None
    
    def cancel_selection(self):
        """取消选择"""
        self.selected_region = None
        self.root.quit()
        self.root.destroy()


def test_region_selector():
    """测试区域选择器"""
    selector = RegionSelector()
    region = selector.select_region()
    
    if region:
        print(f"选择的区域: {region}")
        print(f"位置: ({region['left']}, {region['top']})")
        print(f"尺寸: {region['width']} x {region['height']}")
    else:
        print("未选择区域")


if __name__ == "__main__":
    test_region_selector()

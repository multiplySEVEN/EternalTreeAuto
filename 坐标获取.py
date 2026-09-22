import ctypes
import ctypes.wintypes
import time
import tkinter as tk

# DPI 感知，保证和 main 一致
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

窗口标题 = "悠久之树"


def 获取窗口客户区():
    user32 = ctypes.windll.user32
    hWnd = user32.FindWindowW(None, 窗口标题)
    if not hWnd:
        return None
    point = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hWnd, ctypes.byref(point))
    return (point.x, point.y)


class 工具:
    def __init__(self, root):
        self.root = root
        root.title("坐标获取工具")
        root.geometry("400x340")
        root.attributes("-topmost", True)

        self.客户区 = None
        self.测量模式 = False
        self.上次左键状态 = False

        tk.Label(root, text="窗口标题：").pack(anchor="w", padx=10, pady=(10, 0))
        self.标题变量 = tk.StringVar(value=窗口标题)
        tk.Entry(root, textvariable=self.标题变量).pack(fill="x", padx=10)

        tk.Button(root, text="刷新窗口位置", command=self.刷新).pack(fill="x", padx=10, pady=10)

        self.客户区标签 = tk.Label(root, text="客户区：未获取", justify="left")
        self.客户区标签.pack(anchor="w", padx=10)

        tk.Label(root, text="相对坐标：").pack(anchor="w", padx=10, pady=(10, 0))
        self.坐标标签 = tk.Label(root, text="把鼠标移到游戏窗口的按钮上", font=("Consolas", 16))
        self.坐标标签.pack(anchor="w", padx=10)

        self.测量按钮 = tk.Button(root, text="开始测量", command=self.切换测量模式,
                                  bg="#4CAF50", fg="white")
        self.测量按钮.pack(fill="x", padx=10, pady=10)

        self.状态标签 = tk.Label(root, text="", fg="blue")
        self.状态标签.pack(anchor="w", padx=10)

        self.当前坐标 = (0, 0)
        self.刷新()
        self.更新()

    def 刷新(self):
        global 窗口标题
        窗口标题 = self.标题变量.get()
        self.客户区 = 获取窗口客户区()
        if self.客户区:
            self.客户区标签.config(text=f"客户区：({self.客户区[0]}, {self.客户区[1]})")
        else:
            self.客户区标签.config(text="客户区：未找到窗口")

    def 切换测量模式(self):
        if self.测量模式:
            self.退出测量模式()
        else:
            self.进入测量模式()

    def 进入测量模式(self):
        self.测量模式 = True
        self.测量按钮.config(text="测量中...", bg="#FF9800")
        self.状态标签.config(text="请把鼠标移到目标位置，点击左键")

    def 退出测量模式(self):
        self.测量模式 = False
        self.测量按钮.config(text="开始测量", bg="#4CAF50")
        self.状态标签.config(text="")

    def 更新(self):
        user32 = ctypes.windll.user32

        # 鼠标位置
        cursor = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        if self.客户区:
            相对x = cursor.x - self.客户区[0]
            相对y = cursor.y - self.客户区[1]
            self.当前坐标 = (相对x, 相对y)
            self.坐标标签.config(text=f"({相对x}, {相对y})")

        # 测量模式：检测左键按下
        if self.测量模式:
            # GetAsyncKeyState(0x01) 检测左键
            状态 = user32.GetAsyncKeyState(0x01) & 0x8000
            按下 = 状态 != 0
            if 按下 and not self.上次左键状态:
                # 刚按下
                self.复制()
                self.退出测量模式()
            self.上次左键状态 = 按下

        self.root.after(50, self.更新)

    def 复制(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(f"{self.当前坐标[0]}, {self.当前坐标[1]}")
        self.状态标签.config(text=f"已复制：{self.当前坐标}")


if __name__ == "__main__":
    root = tk.Tk()
    工具(root)
    root.mainloop()
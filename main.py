import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
import pyautogui

from config import (
    图片目录, 置信度,
    页面表, 流程表, 扫荡配置,
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


# ---------- 读图（支持中文路径） ----------
def 读图(路径):
    try:
        with open(路径, "rb") as f:
            数据 = np.frombuffer(f.read(), dtype=np.uint8)
        图 = cv2.imdecode(数据, cv2.IMREAD_COLOR)
        return 图
    except Exception as e:
        print(f"[读图失败] {路径}: {e}")
        return None


# ---------- 图像识别 ----------
def 找图(文件名, 置信=None, 重试=1, 重试等待=0.3):
    if 置信 is None:
        置信 = 置信度
    路径 = os.path.join(图片目录, 文件名)
    if not os.path.exists(路径):
        print(f"[警告] 图片不存在: {路径}")
        return None

    模板 = 读图(路径)
    if 模板 is None:
        return None

    模板高, 模板宽 = 模板.shape[:2]

    for _ in range(重试):
        屏幕 = pyautogui.screenshot()
        屏幕np = np.array(屏幕)
        屏幕np = cv2.cvtColor(屏幕np, cv2.COLOR_RGB2BGR)

        结果 = cv2.matchTemplate(屏幕np, 模板, cv2.TM_CCOEFF_NORMED)
        _, 最大值, _, 最大位置 = cv2.minMaxLoc(结果)

        if 最大值 >= 置信:
            中心x = 最大位置[0] + 模板宽 // 2
            中心y = 最大位置[1] + 模板高 // 2
            return (中心x, 中心y)

        time.sleep(重试等待)

    return None


def 找多图(图片列表, 置信=None, 重试=1):
    if isinstance(图片列表, str):
        图片列表 = [图片列表]
    for 图 in 图片列表:
        位置 = 找图(图, 置信, 重试)
        if 位置:
            return 位置, 图
    return None, None


def 点多图(图片列表, 置信=None, 重试=1):
    """点击，点击后固定等待，防连点"""
    位置, 图 = 找多图(图片列表, 置信, 重试)
    if 位置:
        pyautogui.click(位置)
        print(f"[点击] {图} @ {位置}")
        time.sleep(扫荡配置["点击后等待"])      # ← 新增：点击后短等待
        return True
    print(f"[失败] 没找到 {图片列表}")
    return False


def 等待按钮出现(图片列表, 超时=300, 轮询间隔=1, 日志=print):
    """轮询直到任意一张图出现，返回坐标；超时返回 None"""
    开始 = time.time()
    上次日志 = 0
    while time.time() - 开始 < 超时:
        位置, _ = 找多图(图片列表, 重试=1)
        if 位置:
            return 位置
        经过 = int(time.time() - 开始)
        if 经过 - 上次日志 >= 10:
            名字 = 图片列表 if isinstance(图片列表, str) else "/".join(图片列表)
            日志(f"  等待 {名字} 中... 已等待 {经过}s")
            上次日志 = 经过
        time.sleep(轮询间隔)
    return None


# ---------- 页面识别 ----------
def 识别当前页面():
    for 页面名, 页面信息 in 页面表.items():
        标识 = 页面信息.get("标识")
        if 标识:
            位置, _ = 找多图(标识, 重试=1)
            if 位置:
                return 页面名
    return None


def 等待页面(目标页面, 超时=None, 轮询间隔=None):
    if 超时 is None:
        超时 = 扫荡配置["页面超时"]
    if 轮询间隔 is None:
        轮询间隔 = 扫荡配置["轮询快"]
    开始 = time.time()
    while time.time() - 开始 < 超时:
        if 识别当前页面() == 目标页面:
            return True
        time.sleep(轮询间隔)
    return False


# ---------- 确保在契约类别页 ----------
def 确保在类别页(目标类别页, 日志=print):
    """不管当前在哪个类别页，都切到目标类别页"""
    for _ in range(8):
        当前 = 识别当前页面()
        日志(f"当前页面：{当前}")

        if 当前 == 目标类别页:
            return True

        # 主界面：先点出击
        if 当前 == "主界面":
            日志("在主界面，点击出击")
            if not 点多图("出击.png", 重试=3):
                日志("点击出击失败")
                return False
            # 等任意类别页出现
            位置 = 等待按钮出现(
                ["导览_2.png", "主线_2.png", "素材_2.png", "挑战_2.png", "限时_2.png", "常驻_2.png", "契约_2.png", "多人_2.png", "高难_2.png"],
                超时=扫荡配置["页面超时"],
                轮询间隔=扫荡配置["轮询快"],
                日志=日志,
            )
            if not 位置:
                日志("出击后等待类别页出现超时")
                return False
            continue

        # 当前在某个类别页，点目标类别的标签
        if 当前 in ("导览类别页", "主线类别页", "素材类别页", "挑战类别页", "限时类别页", "常驻类别页", "契约类别页", "多人类别页", "高难类别页"):
            # 找到目标类别对应的标签
            目标动作 = {
                "导览类别页": "导览",
                "主线类别页": "主线",
                "素材类别页": "素材",
                "挑战类别页": "挑战",
                "限时类别页": "限时",
                "常驻类别页": "常驻",
                "契约类别页": "契约",
                "多人类别页": "多人",
                "高难类别页": "高难",
            }.get(目标类别页)

            if not 目标动作:
                日志(f"未知目标类别页：{目标类别页}")
                return False

            页面信息 = 页面表[当前]
            按钮 = 页面信息["可点击"].get(目标动作)
            if not 按钮:
                日志(f"当前页没有 {目标动作} 按钮")
                return False

            if not 点多图(按钮, 重试=3):
                日志(f"点击 {目标动作} 失败")
                return False

            # 等目标类别页出现
            位置 = 等待按钮出现(
                页面表[目标类别页]["标识"],
                超时=扫荡配置["页面超时"],
                轮询间隔=扫荡配置["轮询快"],
                日志=日志,
            )
            if not 位置:
                日志(f"等待 {目标类别页} 出现超时")
                return False
            continue

        日志(f"当前页面无法处理：{当前}")
        return False

    日志(f"切换 {目标类别页} 失败")
    return False

# ---------- 流程执行 ----------
def 执行流程(流程名, 次数, 日志=print):
    流程 = 流程表[流程名]
    路径 = 流程["路径"]

    日志(f"开始执行流程：{流程名}")

    # 1. 识别当前在路径的哪一步
    当前页面 = 识别当前页面()
    日志(f"识别当前页面：{当前页面}")

    if 当前页面 not in 路径:
        日志(f"当前页面不在流程路径中：{当前页面}，停止")
        return

    当前位置 = 路径.index(当前页面)
    日志(f"当前位置：{当前页面}（第 {当前位置} 步）")

    # 2. 从当前位置往后推进
    for 目标页面 in 路径[当前位置 + 1:]:
        当前页面 = 识别当前页面()
        日志(f"当前页面：{当前页面}，目标：{目标页面}")

        if 当前页面 == 目标页面:
            continue

        # 特殊处理：契约类别页
        if 目标页面 in ("导览类别页", "主线类别页", "素材类别页", "挑战类别页", "限时类别页", "常驻类别页", "契约类别页", "多人类别页", "高难类别页"):
            if not 确保在类别页(目标页面, 日志):
                日志(f"确保 {目标页面} 失败，停止")
                return
            continue

        # 普通处理
        页面信息 = 页面表.get(当前页面)
        if not 页面信息:
            日志(f"无法识别当前页面：{当前页面}，停止")
            return

        按钮 = None
        for 动作, 下一页面 in 页面信息.get("跳转", {}).items():
            if 下一页面 == 目标页面:
                按钮 = 页面信息["可点击"].get(动作)
                break

        if not 按钮:
            日志(f"当前页面没有去 {目标页面} 的按钮，停止")
            return

        if not 点多图(按钮, 重试=3):
            日志(f"点击 {按钮} 失败，停止")
            return

        # 特殊情况：到扫荡确认弹窗为止，后面不等页面
        if 目标页面 == "扫荡确认弹窗":
            # 等确定按钮出现
            位置 = 等待按钮出现(
                "桃源_扫荡后确定.png",
                超时=扫荡配置["页面超时"],
                轮询间隔=扫荡配置["轮询快"],
                日志=日志,
            )
            if not 位置:
                日志("等待确定按钮出现超时")
                return
            continue

        # 动态等待目标页面出现
        if not 等待页面(目标页面):
            日志(f"等待页面 {目标页面} 超时")
            return

    日志("已到达扫荡确认弹窗，开始扫荡")

    # 3. 先点确定，进入扫荡
    日志("点击确定，进入扫荡")
    if not 点多图("桃源_扫荡后确定.png", 重试=3):
        日志("点击确定失败")
        return

    # 4. 循环扫荡
    扫荡页 = 流程["扫荡页"]
    退出按钮 = 流程["退出按钮"]
    再次扫荡按钮 = 页面表[扫荡页]["可点击"].get("再次扫荡")

    已完成 = 0
    while 已完成 < 次数:

        日志(f"等待第 {已完成+1}/{次数} 次『再次扫荡』出现...")
        位置 = 等待按钮出现(
            再次扫荡按钮,
            超时=扫荡配置["单次超时"],
            轮询间隔=扫荡配置["轮询间隔"],
            日志=日志,
        )

        if not 位置:
            日志("等待『再次扫荡』超时，停止")
            break

        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])      # ← 新增：点击后短等待
        已完成 += 1
        日志(f"已点击第 {已完成}/{次数} 次扫荡")

    # 5. 扫荡完成后等确定
    日志("扫荡次数已完成，等待『确定』按钮出现...")
    位置 = 等待按钮出现(
        退出按钮,
        超时=扫荡配置["单次超时"],
        轮询间隔=扫荡配置["轮询间隔"],
        日志=日志,
    )

    if 位置:
        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])      # ← 新增：点击后短等待
        日志("已点击确定，退出扫荡界面")
    else:
        日志("等待『确定』超时，请手动检查")


# ---------- UI ----------
class 应用:
    def __init__(self, root):
        self.root = root
        root.title("悠久之树 自动扫荡")
        root.geometry("420x400")

        tk.Label(root, text="流程").pack(anchor="w", padx=10, pady=(10, 0))
        self.流程变量 = tk.StringVar(value=list(流程表.keys())[0])
        ttk.Combobox(
            root, textvariable=self.流程变量,
            values=list(流程表.keys()), state="readonly",
        ).pack(fill="x", padx=10)

        tk.Label(root, text="扫荡次数").pack(anchor="w", padx=10, pady=(10, 0))
        self.次数变量 = tk.StringVar(value="10")
        tk.Entry(root, textvariable=self.次数变量).pack(fill="x", padx=10)

        tk.Button(
            root, text="开始", command=self.开始,
            bg="#4CAF50", fg="white",
        ).pack(fill="x", padx=10, pady=15)

        self.日志框 = tk.Text(root, height=8)
        self.日志框.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def 日志(self, 内容):
        self.日志框.insert("end", 内容 + "\n")
        self.日志框.see("end")
        self.root.update()

    def 开始(self):
        try:
            次数 = int(self.次数变量.get())
        except ValueError:
            messagebox.showerror("错误", "次数必须是数字")
            return
        流程名 = self.流程变量.get()
        threading.Thread(
            target=执行流程,
            args=(流程名, 次数, self.日志),
            daemon=True,
        ).start()


if __name__ == "__main__":
    root = tk.Tk()
    应用(root)
    root.mainloop()
import os
import time
import json
import ctypes
import ctypes.wintypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
import pyautogui

from config import (
    图片目录, 置信度, 窗口标题,
    页面表, 流程表, 扫荡配置,
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


# ============================================================
# 窗口客户区
# ============================================================
def 获取窗口客户区():
    user32 = ctypes.windll.user32
    hWnd = user32.FindWindowW(None, 窗口标题)
    if not hWnd:
        return None
    point = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hWnd, ctypes.byref(point))
    return (point.x, point.y)


# ============================================================
# 缓存
# ============================================================
_缓存 = {}
_缓存已加载 = False


def 加载缓存():
    global _缓存, _缓存已加载
    if _缓存已加载:
        return
    path = 扫荡配置.get("缓存文件")
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                _缓存 = json.load(f)
            print(f"[缓存] 已加载 {len(_缓存)} 条")
        except Exception as e:
            print(f"[缓存] 加载失败：{e}")
            _缓存 = {}
    _缓存已加载 = True


def 保存缓存():
    path = 扫荡配置.get("缓存文件")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_缓存, f, ensure_ascii=False, indent=2)
        print(f"[缓存] 已保存 {len(_缓存)} 条")
    except Exception as e:
        print(f"[缓存] 保存失败：{e}")


def 记录位置(图名, 相对x, 相对y):
    _缓存[图名] = [相对x, 相对y]


# ============================================================
# 读图
# ============================================================
_模板缓存 = {}


def 读图(路径):
    try:
        with open(路径, "rb") as f:
            数据 = np.frombuffer(f.read(), dtype=np.uint8)
        图 = cv2.imdecode(数据, cv2.IMREAD_COLOR)
        return 图
    except Exception as e:
        print(f"[读图失败] {路径}: {e}")
        return None


def 读模板(文件名):
    if 文件名 in _模板缓存:
        return _模板缓存[文件名]
    路径 = os.path.join(图片目录, 文件名)
    if not os.path.exists(路径):
        print(f"[警告] 图片不存在: {路径}")
        _模板缓存[文件名] = None
        return None
    模板 = 读图(路径)
    _模板缓存[文件名] = 模板
    return 模板


# ============================================================
# 截屏 + 匹配
# ============================================================
def 截屏():
    屏幕 = pyautogui.screenshot()
    屏幕np = np.array(屏幕)
    return cv2.cvtColor(屏幕np, cv2.COLOR_RGB2BGR)


def 在帧上找图(帧, 文件名, 置信=None):
    if 置信 is None:
        置信 = 置信度
    模板 = 读模板(文件名)
    if 模板 is None:
        return None
    模板高, 模板宽 = 模板.shape[:2]
    if 帧.shape[0] < 模板高 or 帧.shape[1] < 模板宽:
        return None
    结果 = cv2.matchTemplate(帧, 模板, cv2.TM_CCOEFF_NORMED)
    _, 最大值, _, 最大位置 = cv2.minMaxLoc(结果)
    if 最大值 >= 置信:
        return (最大位置[0] + 模板宽 // 2, 最大位置[1] + 模板高 // 2)
    return None


def 在帧上找缓存位置(帧, 文件名, 客户区, 置信=None):
    if 置信 is None:
        置信 = 置信度
    if not 客户区:
        return None
    缓存坐标 = _缓存.get(文件名)
    if not 缓存坐标:
        return None
    模板 = 读模板(文件名)
    if 模板 is None:
        return None

    相对x, 相对y = 缓存坐标
    x = 客户区[0] + 相对x
    y = 客户区[1] + 相对y
    模板高, 模板宽 = 模板.shape[:2]

    x1 = max(0, x - 模板宽 // 2)
    y1 = max(0, y - 模板高 // 2)
    x2 = min(帧.shape[1], x + 模板宽 // 2)
    y2 = min(帧.shape[0], y + 模板高 // 2)
    区域 = 帧[y1:y2, x1:x2]

    if 区域.shape[0] < 模板高 or 区域.shape[1] < 模板宽:
        return None

    结果 = cv2.matchTemplate(区域, 模板, cv2.TM_CCOEFF_NORMED)
    _, 最大值, _, _ = cv2.minMaxLoc(结果)
    if 最大值 >= 置信:
        return (x, y)
    return None


# ============================================================
# 找图 / 找多图
# ============================================================
def 找图(文件名, 置信=None, 重试=1, 重试等待=0.3):
    if 置信 is None:
        置信 = 置信度
    加载缓存()
    客户区 = 获取窗口客户区()

    for _ in range(重试):
        帧 = 截屏()
        if 扫荡配置.get("启用缓存", True):
            位置 = 在帧上找缓存位置(帧, 文件名, 客户区, 置信)
            if 位置:
                return 位置
        位置 = 在帧上找图(帧, 文件名, 置信)
        if 位置:
            if 扫荡配置.get("启用缓存", True) and 客户区:
                记录位置(文件名, 位置[0] - 客户区[0], 位置[1] - 客户区[1])
            return 位置
        time.sleep(重试等待)
    return None


def 找多图(图片列表, 置信=None, 重试=1):
    if isinstance(图片列表, str):
        图片列表 = [图片列表]
    if 置信 is None:
        置信 = 置信度

    加载缓存()
    客户区 = 获取窗口客户区()

    for _ in range(重试):
        帧 = 截屏()

        if 扫荡配置.get("启用缓存", True):
            for 图 in 图片列表:
                位置 = 在帧上找缓存位置(帧, 图, 客户区, 置信)
                if 位置:
                    return 位置, 图

        for 图 in 图片列表:
            位置 = 在帧上找图(帧, 图, 置信)
            if 位置:
                if 扫荡配置.get("启用缓存", True) and 客户区:
                    记录位置(图, 位置[0] - 客户区[0], 位置[1] - 客户区[1])
                return 位置, 图

        time.sleep(0.2)

    return None, None


def 点多图(图片列表, 置信=None, 重试=1):
    位置, 图 = 找多图(图片列表, 置信, 重试)
    if 位置:
        pyautogui.click(位置)
        print(f"[点击] {图} @ {位置}")
        return True
    print(f"[失败] 没找到 {图片列表}")
    return False


def 等待按钮出现(图片列表, 超时=300, 轮询间隔=None, 日志=print):
    if 轮询间隔 is None:
        轮询间隔 = 扫荡配置["轮询间隔"]
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


# ============================================================
# 点击并确认页面跳转（切页按钮专用）
# ============================================================
def 点击并确认页面(按钮图, 目标页面, 日志=print, 最大重试=None):
    if 最大重试 is None:
        最大重试 = 扫荡配置.get("最大点击重试", 3)
    目标标识 = 页面表[目标页面]["标识"]

    for i in range(最大重试):
        日志(f"点击 {按钮图}（第 {i+1}/{最大重试} 次）")
        if not 点多图(按钮图, 重试=2):
            日志(f"没找到按钮：{按钮图}")
            time.sleep(0.5)
            continue

        if 等待按钮出现(目标标识, 超时=扫荡配置["页面超时"], 日志=日志):
            return True

        日志(f"点击后未跳转到 {目标页面}，重试")

    return False


# ============================================================
# 点击并确认按钮出现（弹窗按钮专用）
# ============================================================
def 点击并确认出现(按钮图, 后果图, 点击前超时=30, 点击后超时=None, 日志=print, 最大重试=None):
    """
    点击按钮 → 等后果标识出现 → 没出现就重点
    用于：点确定后等弹窗关闭、点扫荡后等下一按钮等
    """
    if 最大重试 is None:
        最大重试 = 扫荡配置.get("最大点击重试", 3)
    if 点击后超时 is None:
        点击后超时 = 扫荡配置["页面超时"]

    for i in range(最大重试):
        日志(f"点击 {按钮图}（第 {i+1}/{最大重试} 次）")

        # 等按钮出现
        位置 = 等待按钮出现(按钮图, 超时=点击前超时, 日志=日志)
        if not 位置:
            日志(f"等待按钮出现超时：{按钮图}")
            return False

        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])

        # 等后果标识出现
        if 等待按钮出现(后果图, 超时=点击后超时, 轮询间隔=扫荡配置["轮询快"], 日志=日志):
            return True

        日志(f"点击后未出现 {后果图}，重试")

    return False


# ============================================================
# 识别当前页面（启动时调用一次）
# ============================================================
def 识别当前页面():
    帧 = 截屏()
    加载缓存()
    客户区 = 获取窗口客户区()

    for 页面名, 页面信息 in 页面表.items():
        标识 = 页面信息.get("标识")
        if not 标识:
            continue
        图列表 = 标识 if isinstance(标识, list) else [标识]
        for 图 in 图列表:
            if 扫荡配置.get("启用缓存", True):
                位置 = 在帧上找缓存位置(帧, 图, 客户区)
                if 位置:
                    return 页面名
            位置 = 在帧上找图(帧, 图)
            if 位置:
                if 扫荡配置.get("启用缓存", True) and 客户区:
                    记录位置(图, 位置[0] - 客户区[0], 位置[1] - 客户区[1])
                return 页面名
    return None


# ============================================================
# 类别页
# ============================================================
类别页集合 = ("导览类别页", "主线类别页", "素材类别页", "挑战类别页",
             "限时类别页", "常驻类别页", "契约类别页", "多人类别页", "高难类别页")

类别动作映射 = {
    "导览类别页": "导览",
    "主线类别页": "主线",
    "素材类别页": "素材",
    "挑战类别页": "挑战",
    "限时类别页": "限时",
    "常驻类别页": "常驻",
    "契约类别页": "契约",
    "多人类别页": "多人",
    "高难类别页": "高难",
}

类别页标识列表 = ["导览_2.png", "主线_2.png", "素材_2.png", "挑战_2.png",
                  "限时_2.png", "常驻_2.png", "契约_2.png", "多人_2.png", "高难_2.png"]


def 识别类别页():
    帧 = 截屏()
    加载缓存()
    客户区 = 获取窗口客户区()

    for 页面名 in 类别页集合:
        页面信息 = 页面表.get(页面名)
        if not 页面信息:
            continue
        标识 = 页面信息.get("标识")
        if not 标识:
            continue
        图列表 = 标识 if isinstance(标识, list) else [标识]
        for 图 in 图列表:
            if 扫荡配置.get("启用缓存", True):
                位置 = 在帧上找缓存位置(帧, 图, 客户区)
                if 位置:
                    return 页面名
            位置 = 在帧上找图(帧, 图)
            if 位置:
                if 扫荡配置.get("启用缓存", True) and 客户区:
                    记录位置(图, 位置[0] - 客户区[0], 位置[1] - 客户区[1])
                return 页面名
    return None


def 点击出击并确认(日志=print, 最大重试=None):
    if 最大重试 is None:
        最大重试 = 扫荡配置.get("最大点击重试", 3)
    for i in range(最大重试):
        日志(f"点击出击（第 {i+1}/{最大重试} 次）")
        if not 点多图("出击.png", 重试=2):
            日志("没找到出击按钮")
            time.sleep(0.5)
            continue
        if 等待按钮出现(类别页标识列表, 超时=扫荡配置["页面超时"], 日志=日志):
            return True
        日志("点击出击后未进入类别页，重试")
    return False


def 确保在类别页(目标类别页, 日志=print):
    for _ in range(8):
        当前 = 识别类别页()
        日志(f"当前类别页：{当前}")

        if 当前 == 目标类别页:
            return True

        if 当前 is None:
            日志("未识别到类别页，尝试点出击")
            if not 点击出击并确认(日志):
                日志("点出击失败，停止")
                return False
            continue

        目标动作 = 类别动作映射.get(目标类别页)
        if not 目标动作:
            日志(f"未知目标类别页：{目标类别页}")
            return False

        页面信息 = 页面表[当前]
        按钮 = 页面信息["可点击"].get(目标动作)
        if not 按钮:
            日志(f"当前页没有 {目标动作} 按钮")
            return False

        if not 点击并确认页面(按钮, 目标类别页, 日志=日志):
            日志(f"切换 {目标类别页} 失败")
            return False

    日志(f"切换 {目标类别页} 失败")
    return False


# ============================================================
# 流程执行
# ============================================================
def 执行流程(流程名, 次数, 日志=print):
    流程 = 流程表[流程名]
    路径 = 流程["路径"]

    日志(f"开始执行流程：{流程名}")

    当前页面 = 识别当前页面()
    日志(f"识别当前页面：{当前页面}")

    if 当前页面 not in 路径:
        日志(f"当前页面不在流程路径中：{当前页面}，停止")
        return

    当前位置 = 路径.index(当前页面)
    日志(f"当前位置：{当前页面}（第 {当前位置} 步）")

    # ---------- 线性推进 ----------
    for i in range(当前位置, len(路径) - 1):
        当前页面 = 路径[i]
        目标页面 = 路径[i + 1]
        日志(f"当前：{当前页面} → 目标：{目标页面}")

        if 目标页面 in 类别页集合:
            if not 确保在类别页(目标页面, 日志):
                日志(f"确保 {目标页面} 失败，停止")
                return
            continue

        页面信息 = 页面表.get(当前页面)
        if not 页面信息:
            日志(f"页面表里没有：{当前页面}，停止")
            return

        按钮 = None
        for 动作, 下一页面 in 页面信息.get("跳转", {}).items():
            if 下一页面 == 目标页面:
                按钮 = 页面信息["可点击"].get(动作)
                break

        if not 按钮:
            日志(f"{当前页面} 没有去 {目标页面} 的按钮，停止")
            return

        # 到扫荡确认弹窗：点扫荡 → 等确定按钮出现
        if 目标页面 == "扫荡确认弹窗":
            if not 点击并确认出现(
                按钮,
                "桃源_扫荡后确定.png",
                点击前超时=扫荡配置["页面超时"],
                点击后超时=扫荡配置["页面超时"],
                日志=日志,
            ):
                日志("无法进入扫荡确认弹窗，停止")
                return
            continue

        # 普通页面：点击并确认跳转
        if not 点击并确认页面(按钮, 目标页面, 日志=日志):
            日志(f"无法进入 {目标页面}，停止")
            return

    日志("已到达扫荡确认弹窗，开始扫荡")

    # ---------- 进入扫荡：点确定 → 等再次扫荡出现 ----------
    日志("点击确定，进入扫荡")
    if not 点击并确认出现(
        "桃源_扫荡后确定.png",
        "桃源_再次扫荡.png",
        点击前超时=扫荡配置["页面超时"],
        点击后超时=扫荡配置["单次超时"],
        日志=日志,
    ):
        日志("进入扫荡失败，停止")
        return

    # ---------- 循环扫荡 ----------
    扫荡页 = 流程["扫荡页"]
    再次扫荡按钮 = 页面表[扫荡页]["可点击"].get("再次扫荡")

    # 进入扫荡时点的那次确定，已经算第 1 次
    剩余次数 = max(0, 次数 - 1)
    已完成 = 0

    while 已完成 < 剩余次数:
        当前第几次 = 已完成 + 2  # 显示用：第 1 次已由确定触发
        日志(f"等待第 {当前第几次}/{次数} 次『再次扫荡』出现...")
        位置 = 等待按钮出现(
            再次扫荡按钮,
            超时=扫荡配置["单次超时"],
            日志=日志,
        )
        if not 位置:
            日志("等待『再次扫荡』超时，停止")
            break
        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])
        已完成 += 1
        日志(f"已完成第 {已完成 + 1}/{次数} 次扫荡")

    # ---------- 收尾：点确定 → 等返回主界面出现 ----------
    日志("扫荡次数完成，准备退出扫荡界面")
    if not 点击并确认出现(
        "桃源_扫荡结束确认.png",
        "返回主界面.png",
        点击前超时=扫荡配置["单次超时"],
        点击后超时=扫荡配置["页面超时"],
        日志=日志,
    ):
        日志("点确定退出失败，停止")
        return

    # ---------- 点返回主界面 ----------
    日志("点击返回主界面")
    if not 点击并确认出现(
        "返回主界面.png",
        "出击.png",
        点击前超时=扫荡配置["页面超时"],
        点击后超时=扫荡配置["页面超时"],
        日志=日志,
    ):
        日志("返回主界面失败，请手动检查")
        return

    日志("已返回主界面，流程结束")


# ============================================================
# UI
# ============================================================
class 应用:
    def __init__(self, root):
        self.root = root
        root.title("EternalTreeAuto")
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
    加载缓存()
    root = tk.Tk()
    应用(root)
    try:
        root.mainloop()
    finally:
        保存缓存()
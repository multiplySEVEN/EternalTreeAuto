import os
import time
import json
import ctypes
import ctypes.wintypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import cv2
import numpy as np
import pyautogui

from config import (
    图片目录, 置信度, 窗口标题,
    页面表, 流程表, 扫荡配置, 任务流文件,
    坐标按钮表, 战令按钮顺序,
)

"""pyinstaller --onefile --windowed --name EternalTreeAuto main.py"""

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

_体力不足 = False


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
        except Exception:
            _缓存 = {}
    _缓存已加载 = True


def 保存缓存():
    path = 扫荡配置.get("缓存文件")
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_缓存, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
        return cv2.imdecode(数据, cv2.IMREAD_COLOR)
    except Exception:
        return None


def 读模板(文件名):
    if 文件名 in _模板缓存:
        return _模板缓存[文件名]
    路径 = os.path.join(图片目录, 文件名)
    if not os.path.exists(路径):
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
# 找图 / 找多图（多帧重试）
# ============================================================
def 找图(文件名, 置信=None, 重试=3, 重试等待=0.2):
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


def 找多图(图片列表, 置信=None, 重试=3):
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


def 点多图(图片列表, 置信=None, 重试=3):
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
# 点击并确认
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


def 点击并确认出现(按钮图, 后果图, 点击前超时=30, 点击后超时=None, 日志=print, 最大重试=None):
    if 最大重试 is None:
        最大重试 = 扫荡配置.get("最大点击重试", 3)
    if 点击后超时 is None:
        点击后超时 = 扫荡配置["页面超时"]

    for i in range(最大重试):
        日志(f"点击 {按钮图}（第 {i+1}/{最大重试} 次）")
        位置 = 等待按钮出现(按钮图, 超时=点击前超时, 日志=日志)
        if not 位置:
            日志(f"等待按钮出现超时：{按钮图}")
            return False
        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])
        if 等待按钮出现(后果图, 超时=点击后超时, 轮询间隔=扫荡配置["轮询快"], 日志=日志):
            return True
        日志(f"点击后未出现 {后果图}，重试")
    return False


# ============================================================
# 识别当前页面
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
    "导览类别页": "导览", "主线类别页": "主线", "素材类别页": "素材",
    "挑战类别页": "挑战", "限时类别页": "限时", "常驻类别页": "常驻",
    "契约类别页": "契约", "多人类别页": "多人", "高难类别页": "高难",
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
                return False
            continue
        目标动作 = 类别动作映射.get(目标类别页)
        if not 目标动作:
            return False
        页面信息 = 页面表[当前]
        按钮 = 页面信息["可点击"].get(目标动作)
        if not 按钮:
            return False
        if not 点击并确认页面(按钮, 目标类别页, 日志=日志):
            return False
    return False


# ============================================================
# 回到主界面
# ============================================================
返回类按钮 = ["返回主界面.png", "返回上一步.png", "扫荡结束确认.png"]


def 回到主界面(日志=print, 最大重试=5):
    for i in range(最大重试):
        当前 = 识别当前页面()
        日志(f"当前页面：{当前}")
        if 当前 == "主界面":
            return True

        for 图 in 返回类按钮:
            位置, _ = 找多图(图, 重试=1)
            if 位置:
                日志(f"点击 {图}")
                pyautogui.click(位置)
                time.sleep(扫荡配置["点击后等待"])
                break
        else:
            日志("找不到返回按钮")
            return False

    return False


def 检测体力不足并处理(日志=print):
    """检测是否弹出体力回复界面，有则关闭并返回主界面"""
    global _体力不足

    位置, _ = 找多图("回复AP.png", 重试=1)
    if not 位置:
        return False

    _体力不足 = True
    日志("检测到体力不足，关闭回复界面")
    点击坐标按钮("回复AP关闭", 日志)
    time.sleep(0.5)
    回到主界面(日志)
    return True


# ============================================================
# 坐标点击
# ============================================================
def 点击坐标(相对x, 相对y, 日志=print):
    """直接用相对坐标点击，不走图像识别"""
    客户区 = 获取窗口客户区()
    if not 客户区:
        日志("未找到游戏窗口，无法点击坐标")
        return False
    x = 客户区[0] + 相对x
    y = 客户区[1] + 相对y
    pyautogui.click(x, y)
    日志(f"坐标点击 ({相对x}, {相对y})")
    time.sleep(扫荡配置["点击后等待"])
    return True


def 点击坐标按钮(动作名, 日志=print):
    """按坐标按钮表里的动作名点击"""
    坐标 = 坐标按钮表.get(动作名)
    if not 坐标:
        日志(f"坐标按钮表里没有：{动作名}")
        return False
    return 点击坐标(坐标[0], 坐标[1], 日志)


# ============================================================
# 执行路径项
# ============================================================
def 执行路径项(项, 当前任务次数=1, 日志=print):
    """执行路径里的一个字典元素"""

    # 图像按钮
    if "图像按钮" in 项:
        按钮图 = 项["图像按钮"]
        后果图 = 项.get("等图")
        重试 = 项.get("重试", 扫荡配置.get("最大点击重试", 3))
        if 后果图:
            点击并确认出现(
                按钮图, 后果图,
                点击前超时=扫荡配置["页面超时"],
                点击后超时=扫荡配置["页面超时"],
                日志=日志,
                最大重试=重试,
            )
        else:
            for _ in range(重试):
                if 点多图(按钮图, 重试=2):
                    break
                time.sleep(0.5)
        return

    # 坐标
    if "坐标" in 项:
        次数 = 项.get("次数", 1)
        间隔 = 项.get("间隔", 扫荡配置["点击后等待"])
        for _ in range(次数):
            点击坐标按钮(项["坐标"], 日志)
            time.sleep(间隔)
        return

    # 坐标序列
    if "坐标序列" in 项:
        序列名 = 项["坐标序列"]
        次数 = 项.get("次数", 1)
        间隔 = 项.get("间隔", 1)
        序列 = 战令按钮顺序 if 序列名 == "战令按钮顺序" else 坐标按钮表.get(序列名, [])
        for 动作名 in 序列:
            坐标 = 坐标按钮表.get(动作名)
            if not 坐标:
                日志(f"跳过（坐标按钮表里没有）：{动作名}")
                continue
            for _ in range(次数):
                点击坐标(坐标[0], 坐标[1], 日志)
                time.sleep(间隔)
        return

    # 按键
    if "按键" in 项:
        键 = 项["按键"]
        次数 = 项.get("次数", 1)
        间隔 = 项.get("间隔", 0.1)
        for _ in range(次数):
            pyautogui.press(键)
            time.sleep(间隔)
        日志(f"按键 {键} × {次数}")
        return

    # 输入
    if "输入" in 项:
        文本 = 项["输入"]
        if 文本 == "次数":
            文本 = str(当前任务次数)
        日志(f"输入：{文本}")
        pyautogui.write(文本, interval=0.05)
        time.sleep(0.5)
        return

    # 等待连战结束
    if "等待连战结束" in 项:
        标识图 = 项["等待连战结束"]
        超时 = 项.get("超时", 60)
        日志(f"等待连战结束（超过 {超时} 秒未识别到 {标识图} 视为结束）")
        上次识别 = time.time()
        上次日志 = 0
        while True:
            位置, _ = 找多图(标识图, 重试=1)
            if 位置:
                上次识别 = time.time()
            未识别时长 = time.time() - 上次识别
            if 未识别时长 >= 超时:
                日志(f"连战结束（{超时} 秒未识别到标识）")
                break
            经过 = int(time.time() - 上次识别)
            if 经过 - 上次日志 >= 30:
                日志(f"  连战进行中... 上次识别到标识 {经过}s 前")
                上次日志 = 经过
            time.sleep(2)
        return

    # 等图
    if "等图" in 项:
        超时 = 项.get("超时", 扫荡配置["页面超时"])
        日志(f"等待图片出现：{项['等图']}")
        位置 = 等待按钮出现(项["等图"], 超时=超时, 日志=日志)
        if not 位置:
            日志(f"等待超时：{项['等图']}")
        return

    日志(f"未知路径项：{项}")


# ============================================================
# 执行非扫荡流程
# ============================================================
def 执行非扫荡流程(流程名, 次数, 日志=print):
    流程 = 流程表[流程名]
    路径 = 流程["路径"]

    当前页面 = 识别当前页面()
    日志(f"识别当前页面：{当前页面}")

    if 当前页面 not in 路径:
        日志(f"当前页面不在流程路径中：{当前页面}，尝试回主界面")
        回到主界面(日志)
        当前页面 = 识别当前页面()
        日志(f"回主界面后识别：{当前页面}")
        if 当前页面 not in 路径:
            日志("仍不在流程路径中，流程终止")
            return False

    当前位置 = 路径.index(当前页面)
    日志(f"当前位置：{当前页面}（第 {当前位置} 步）")

    for i in range(当前位置, len(路径)):
        项 = 路径[i]

        if isinstance(项, dict):
            执行路径项(项, 次数, 日志)
            continue

        if i + 1 >= len(路径):
            break
        目标页面 = 路径[i + 1]

        if isinstance(目标页面, dict):
            continue

        日志(f"当前：{项} → 目标：{目标页面}")

        if 目标页面 in 类别页集合:
            if not 确保在类别页(目标页面, 日志):
                日志(f"确保 {目标页面} 失败")
                return False
            continue

        页面信息 = 页面表.get(项)
        if not 页面信息:
            日志(f"页面表里没有：{项}")
            return False

        按钮 = None
        for 动作, 下一页面 in 页面信息.get("跳转", {}).items():
            if 下一页面 == 目标页面:
                按钮 = 页面信息["可点击"].get(动作)
                break

        if not 按钮:
            日志(f"{项} 没有去 {目标页面} 的按钮")
            return False

        if not 点击并确认页面(按钮, 目标页面, 日志=日志):
            日志(f"无法进入 {目标页面}")
            return False

    日志(f"流程结束：{流程名}")
    return True


# ============================================================
# 执行流程
# ============================================================
def 执行流程(流程名, 次数, 日志=print):
    流程 = 流程表[流程名]
    路径 = 流程["路径"]

    日志(f"开始执行流程：{流程名}")

    # 判断是否是扫荡流程
    是扫荡流程 = 流程.get("扫荡页") is not None

    if not 是扫荡流程:
        return 执行非扫荡流程(流程名, 次数, 日志)

    # ---------- 扫荡流程 ----------
    当前页面 = 识别当前页面()
    日志(f"识别当前页面：{当前页面}")

    if 当前页面 not in 路径:
        日志(f"当前页面不在流程路径中：{当前页面}，尝试回主界面")
        回到主界面(日志)
        当前页面 = 识别当前页面()
        日志(f"回主界面后识别：{当前页面}")
        if 当前页面 not in 路径:
            日志("仍不在流程路径中，流程终止")
            return False

    当前位置 = 路径.index(当前页面)
    日志(f"当前位置：{当前页面}（第 {当前位置} 步）")

    for i in range(当前位置, len(路径)):
        项 = 路径[i]

        if isinstance(项, dict):
            执行路径项(项, 次数, 日志)
            continue

        if i + 1 >= len(路径):
            break
        目标页面 = 路径[i + 1]

        if isinstance(目标页面, dict):
            continue

        日志(f"当前：{项} → 目标：{目标页面}")

        if 目标页面 in 类别页集合:
            if not 确保在类别页(目标页面, 日志):
                日志(f"确保 {目标页面} 失败")
                return False
            continue

        页面信息 = 页面表.get(项)
        if not 页面信息:
            日志(f"页面表里没有：{项}")
            return False

        按钮 = None
        for 动作, 下一页面 in 页面信息.get("跳转", {}).items():
            if 下一页面 == 目标页面:
                按钮 = 页面信息["可点击"].get(动作)
                break

        if not 按钮:
            日志(f"{项} 没有去 {目标页面} 的按钮")
            return False

        if 目标页面 == "扫荡确认弹窗":
            # 点扫荡按钮
            if not 点多图(按钮, 重试=3):
                日志(f"没找到按钮：{按钮}")
                return False
            time.sleep(扫荡配置["点击后等待"])

            # 等确定按钮出现，同时检测体力不足
            位置 = 等待按钮出现(
                ["桃源_扫荡后确定.png", "回复AP.png"],
                超时=扫荡配置["页面超时"],
                日志=日志,
            )
            if not 位置:
                日志("等待扫荡确认弹窗超时")
                return False

            # 体力不足
            if 找多图("回复AP.png", 重试=1)[0]:
                global _体力不足
                _体力不足 = True
                日志("检测到体力不足，关闭回复界面")
                点击坐标按钮("回复AP关闭", 日志)
                time.sleep(0.5)
                回到主界面(日志)
                return False

            continue

        if not 点击并确认页面(按钮, 目标页面, 日志=日志):
            日志(f"无法进入 {目标页面}")
            return False

    日志("已到达扫荡确认弹窗，开始扫荡")

    日志("点击确定，进入扫荡")
    if not 点击并确认出现(
        "桃源_扫荡后确定.png", "桃源_再次扫荡.png",
        点击前超时=扫荡配置["页面超时"],
        点击后超时=扫荡配置["单次超时"],
        日志=日志,
    ):
        if 检测体力不足并处理(日志):
            日志("体力不足，流程终止")
            return False
        日志("进入扫荡失败")
        return False

    扫荡页 = 流程["扫荡页"]
    再次扫荡按钮 = 页面表[扫荡页]["可点击"].get("再次扫荡")

    剩余次数 = max(0, 次数 - 1)
    已完成 = 0
    while 已完成 < 剩余次数:
        当前第几次 = 已完成 + 2
        日志(f"等待第 {当前第几次}/{次数} 次『再次扫荡』出现...")
        位置 = 等待按钮出现(再次扫荡按钮, 超时=扫荡配置["单次超时"], 日志=日志)
        if not 位置:
            日志("等待『再次扫荡』超时")
            return False
        pyautogui.click(位置)
        time.sleep(扫荡配置["点击后等待"])
        已完成 += 1
        日志(f"已完成第 {已完成 + 1}/{次数} 次扫荡")

    日志("扫荡次数完成，准备退出扫荡界面")
    if not 点击并确认出现(
        "桃源_扫荡结束确认.png", "返回主界面.png",
        点击前超时=扫荡配置["单次超时"],
        点击后超时=扫荡配置["页面超时"],
        日志=日志,
    ):
        日志("点确定退出失败")
        return False

    日志("点击返回主界面")
    if not 点击并确认出现(
        "返回主界面.png", "出击.png",
        点击前超时=扫荡配置["页面超时"],
        点击后超时=扫荡配置["页面超时"],
        日志=日志,
    ):
        日志("返回主界面失败")
        return False

    日志("已返回主界面，流程结束")
    return True


# ============================================================
# 任务流管理
# ============================================================
所有任务流 = {}


def 加载任务流():
    global 所有任务流
    if os.path.exists(任务流文件):
        try:
            with open(任务流文件, "r", encoding="utf-8") as f:
                所有任务流 = json.load(f)
        except Exception as e:
            print(f"[任务流] 加载失败：{e}")
            所有任务流 = {}


def 保存任务流():
    try:
        with open(任务流文件, "w", encoding="utf-8") as f:
            json.dump(所有任务流, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[任务流] 保存失败：{e}")


def 执行任务流(任务流名, 日志=print):
    global _体力不足

    任务列表 = 所有任务流.get(任务流名, [])
    if not 任务列表:
        日志("任务流为空")
        return

    任务间隔 = 扫荡配置.get("任务间隔", 1.0)

    for i, 任务 in enumerate(任务列表):
        if i > 0:
            日志(f"等待 {任务间隔} 秒后执行下一个任务...")
            time.sleep(任务间隔)

        _体力不足 = False

        日志(f"===== 任务 {i+1}/{len(任务列表)}：{任务['流程']} × {任务['次数']} =====")
        成功 = 执行流程(任务["流程"], 任务["次数"], 日志)

        if not 成功:
            if _体力不足:
                日志(f"任务 {i+1} 体力不足，跳过重试")
                回到主界面(日志)
                continue
            日志("任务失败，尝试回主界面后重试")
            回到主界面(日志)
            成功 = 执行流程(任务["流程"], 任务["次数"], 日志)

        if not 成功:
            if _体力不足:
                日志(f"任务 {i+1} 体力不足，跳过")
                回到主界面(日志)
                continue
            日志(f"任务 {i+1} 重试仍失败，继续下一个")
            回到主界面(日志)

    日志("所有任务完成")


# ============================================================
# UI
# ============================================================
class 应用:
    def __init__(self, root):
        self.root = root
        root.title("EternalTreeAuto")
        root.geometry("720x840")

        self.当前任务流 = tk.StringVar()
        self.流程变量 = tk.StringVar()
        self.次数变量 = tk.StringVar(value="1")

        self.操作按钮 = []

        # ---------- 任务流选择 ----------
        frame1 = tk.Frame(root)
        frame1.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(frame1, text="任务流：").pack(side="left")
        self.任务流下拉 = ttk.Combobox(frame1, textvariable=self.当前任务流, state="readonly", width=20)
        self.任务流下拉.pack(side="left", padx=5)
        self.任务流下拉.bind("<<ComboboxSelected>>", self.刷新任务列表)
        self.操作按钮.append(self.任务流下拉)
        btn = tk.Button(frame1, text="创建任务流", command=self.创建任务流)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)
        btn = tk.Button(frame1, text="删除任务流", command=self.删除任务流)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)

        # ---------- 添加任务 ----------
        frame2 = tk.Frame(root)
        frame2.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(frame2, text="流程：").pack(side="left")
        self.目标下拉 = ttk.Combobox(frame2, textvariable=self.流程变量, state="readonly", width=30)
        self.目标下拉["values"] = list(流程表.keys())
        self.目标下拉.pack(side="left", padx=5)
        self.目标下拉.bind("<<ComboboxSelected>>", self.切换流程)
        self.操作按钮.append(self.目标下拉)

        tk.Label(frame2, text="次数：").pack(side="left")
        self.次数输入框 = tk.Entry(frame2, textvariable=self.次数变量, width=6)
        self.次数输入框.pack(side="left", padx=5)
        self.操作按钮.append(self.次数输入框)

        btn = tk.Button(frame2, text="添加", command=self.添加任务)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)

        # ---------- 任务列表 ----------
        frame3 = tk.Frame(root)
        frame3.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        tk.Label(frame3, text="任务列表：").pack(anchor="w")
        self.任务列表框 = tk.Listbox(frame3, height=10)
        self.任务列表框.pack(fill="both", expand=True, side="left")
        scrollbar = tk.Scrollbar(frame3, command=self.任务列表框.yview)
        scrollbar.pack(side="right", fill="y")
        self.任务列表框.config(yscrollcommand=scrollbar.set)

        # ---------- 任务操作 ----------
        frame4 = tk.Frame(root)
        frame4.pack(fill="x", padx=10, pady=(5, 0))
        btn = tk.Button(frame4, text="删除任务", command=self.删除任务)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)
        btn = tk.Button(frame4, text="上移", command=self.上移任务)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)
        btn = tk.Button(frame4, text="下移", command=self.下移任务)
        btn.pack(side="left", padx=5)
        self.操作按钮.append(btn)

        # ---------- 执行 ----------
        frame5 = tk.Frame(root)
        frame5.pack(fill="x", padx=10, pady=(10, 0))
        self.执行按钮 = tk.Button(frame5, text="开始执行", command=self.开始执行,
                                  bg="#4CAF50", fg="white", width=15)
        self.执行按钮.pack(side="left", padx=5)

        # ---------- 日志 ----------
        tk.Label(root, text="日志：").pack(anchor="w", padx=10, pady=(10, 0))
        self.日志框 = tk.Text(root, height=10)
        self.日志框.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        加载任务流()
        self.刷新任务流下拉()

    # ---------- 任务流 ----------
    def 刷新任务流下拉(self):
        名字列表 = list(所有任务流.keys())
        self.任务流下拉["values"] = 名字列表
        if 名字列表 and not self.当前任务流.get():
            self.当前任务流.set(名字列表[0])
            self.刷新任务列表()

    def 创建任务流(self):
        名字 = simpledialog.askstring("创建任务流", "输入任务流名字：")
        if not 名字:
            return
        if 名字 in 所有任务流:
            messagebox.showwarning("提示", "任务流已存在")
            return
        所有任务流[名字] = []
        保存任务流()
        self.刷新任务流下拉()
        self.当前任务流.set(名字)
        self.刷新任务列表()

    def 删除任务流(self):
        名字 = self.当前任务流.get()
        if not 名字:
            return
        if not messagebox.askyesno("确认", f"删除任务流「{名字}」？"):
            return
        del 所有任务流[名字]
        保存任务流()
        self.当前任务流.set("")
        self.刷新任务流下拉()
        self.刷新任务列表()

    # ---------- 流程切换 ----------
    def 切换流程(self, event=None):
        流程名 = self.流程变量.get()
        if 流程名 == "角色经验4":
            self.次数输入框.config(state="disabled")
            self.次数变量.set("1")
        else:
            self.次数输入框.config(state="normal")

    # ---------- 任务列表 ----------
    def 刷新任务列表(self, event=None):
        self.任务列表框.delete(0, "end")
        名字 = self.当前任务流.get()
        任务列表 = 所有任务流.get(名字, [])
        for i, 任务 in enumerate(任务列表):
            self.任务列表框.insert("end", f"{i+1}. {任务['流程']} × {任务['次数']}")

    def 添加任务(self):
        名字 = self.当前任务流.get()
        if not 名字:
            messagebox.showwarning("提示", "请先创建或选择任务流")
            return
        流程名 = self.流程变量.get()
        if not 流程名:
            messagebox.showwarning("提示", "请选择流程")
            return

        if 流程名 == "角色经验4":
            次数 = 1
        else:
            try:
                次数 = int(self.次数变量.get())
                if 次数 <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("提示", "次数必须是正整数")
                return

        if 流程名 == "联机战斗连战":
            if not (1 <= 次数 <= 300):
                messagebox.showwarning("提示", "联机连战次数必须在 1~300 之间")
                return

        所有任务流[名字].append({"流程": 流程名, "次数": 次数})
        保存任务流()
        self.刷新任务列表()

    def 删除任务(self):
        名字 = self.当前任务流.get()
        if not 名字:
            return
        选中 = self.任务列表框.curselection()
        if not 选中:
            messagebox.showwarning("提示", "请先选中要删除的任务")
            return
        索引 = 选中[0]
        del 所有任务流[名字][索引]
        保存任务流()
        self.刷新任务列表()

    def 上移任务(self):
        self.移动任务(-1)

    def 下移任务(self):
        self.移动任务(1)

    def 移动任务(self, 方向):
        名字 = self.当前任务流.get()
        if not 名字:
            return
        选中 = self.任务列表框.curselection()
        if not 选中:
            return
        索引 = 选中[0]
        新索引 = 索引 + 方向
        if 新索引 < 0 or 新索引 >= len(所有任务流[名字]):
            return
        任务列表 = 所有任务流[名字]
        任务列表[索引], 任务列表[新索引] = 任务列表[新索引], 任务列表[索引]
        保存任务流()
        self.刷新任务列表()
        self.任务列表框.selection_set(新索引)

    # ---------- 执行 ----------
    def 日志(self, 内容):
        self.日志框.insert("end", 内容 + "\n")
        self.日志框.see("end")
        self.root.update()

    def 设置按钮状态(self, 可用):
        state = "normal" if 可用 else "disabled"
        for 控件 in self.操作按钮:
            try:
                if isinstance(控件, ttk.Combobox):
                    控件.config(state="readonly" if 可用 else "disabled")
                else:
                    控件.config(state=state)
            except Exception:
                pass
        if 可用:
            self.执行按钮.config(state="normal", text="开始执行", bg="#4CAF50")
        else:
            self.执行按钮.config(state="disabled", text="执行中...", bg="#999999")

    def 开始执行(self):
        if self.执行按钮["state"] == "disabled":
            return

        名字 = self.当前任务流.get()
        if not 名字:
            messagebox.showwarning("提示", "请先选择任务流")
            return
        if not 所有任务流.get(名字):
            messagebox.showwarning("提示", "任务流为空")
            return

        self.设置按钮状态(False)

        def 跑():
            try:
                执行任务流(名字, self.日志)
            finally:
                self.root.after(0, lambda: self.设置按钮状态(True))

        threading.Thread(target=跑, daemon=True).start()


if __name__ == "__main__":
    加载缓存()
    加载任务流()
    root = tk.Tk()
    应用(root)
    try:
        root.mainloop()
    finally:
        保存缓存()
        保存任务流()
# -*- coding: utf-8 -*-
"""自检脚本：把环境、依赖、配置、端口一次性全查一遍。

用法: python tools/preflight.py
"""
import os
import socket
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# Windows 控制台 GBK，中文/符号会让 print 直接抛异常
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OK = "  [OK]  "
BAD = "  [!!]  "
WARN = "  [~~]  "
problems = []


def line(tag, msg):
    print(tag + msg)


def check_python():
    print("\n== Python 运行环境 ==")
    line(OK, f"解释器: {sys.executable}")
    line(OK, f"版本: {sys.version.split()[0]}")
    if sys.version_info < (3, 8):
        problems.append("Python 版本过低，需要 3.8+")


def check_libs():
    print("\n== 依赖库 ==")
    try:
        import tkinter
        line(OK, f"tkinter {tkinter.TkVersion}（全屏弹窗用）")
    except Exception as e:
        line(BAD, f"tkinter 不可用: {e}")
        problems.append("缺少 tkinter，弹窗无法显示")
    try:
        from PIL import Image, ImageTk
        import PIL
        line(OK, f"Pillow {PIL.__version__}（图片缩放用）")
    except Exception as e:
        line(BAD, f"Pillow 不可用: {e}")
        problems.append("缺少 Pillow，图片无法缩放显示")
    try:
        import winsound
        line(OK, "winsound（响铃用）")
    except Exception as e:
        line(WARN, f"winsound 不可用: {e}（不影响主流程）")


def check_config():
    print("\n== 配置 ==")
    try:
        from app.config import CFG
        line(OK, f"群号: {sorted(CFG.groups)}")
        line(OK, f"关键发送者: {sorted(CFG.senders)}")
        line(OK, f"关键词: {CFG.keywords}")
        line(OK, f"必须含图片: {CFG.need_image}")
        line(OK, f"接收端口: {CFG.port}")
        line(OK, f"干跑模式: {CFG.dry_run}" + ("  <- 正式使用前要改成 false" if CFG.dry_run else ""))
        line(OK, f"全屏弹窗: {CFG.popup} / 声音: {CFG.sound}")
        if CFG.push_enabled and (not CFG.send_key or "在这里填" in CFG.send_key):
            line(WARN, "手机推送已开启，但 SendKey 还没填")
            problems.append("手机推送缺 SendKey")
        elif CFG.push_enabled:
            line(OK, f"手机推送已配置 SendKey: {CFG.send_key[:8]}...")
        else:
            line(WARN, "手机推送未启用")
        if CFG.push_qq_image and not CFG.target_qq:
            line(WARN, "勾了「推送原图到QQ」但目标QQ号是 0")
    except Exception as e:
        line(BAD, f"配置读取失败: {e}")
        problems.append(f"config.json 有问题: {e}")


def check_port():
    print("\n== 端口 ==")
    try:
        from app.config import CFG
        port = CFG.port
    except Exception:
        port = 18080
    s = socket.socket()
    s.settimeout(1.5)
    busy = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    if busy:
        line(OK, f"127.0.0.1:{port} 已有服务在监听（监听服务可能已在运行）")
    else:
        line(WARN, f"127.0.0.1:{port} 空闲（监听服务尚未启动）")


def check_napcat():
    print("\n== NapCat 部署 ==")
    zip_path = os.path.join(BASE, "download", "NapCat.Shell.zip")
    if os.path.exists(zip_path):
        line(OK, f"安装包存在: {os.path.getsize(zip_path)/1024/1024:.2f} MB")
    else:
        line(WARN, "还没下载安装包 download\\NapCat.Shell.zip")
    inst = os.path.join(BASE, "napcat")
    if os.path.isdir(inst):
        n = sum(len(f) for _, _, f in os.walk(inst))
        line(OK, f"已解压: {inst}（{n} 个文件）")
        cfg_dir = os.path.join(inst, "config")
        if os.path.isdir(cfg_dir):
            bots = [f for f in os.listdir(cfg_dir) if f.startswith("onebot11")]
            line(OK, f"OneBot 配置: {bots or '无'}")
        for cand in ("启动NapCat.bat", "launcher.bat", "launcher-win10.bat", "napcat.bat"):
            if os.path.exists(os.path.join(inst, cand)):
                line(OK, f"启动入口: {cand}")
                break
    else:
        line(WARN, "还没解压 NapCat")


def check_qq():
    print("\n== 现有 QQ ==")
    qq_exe = r"D:\新建文件夹\交流\QQ.exe"
    if os.path.exists(qq_exe):
        line(OK, f"QQ 客户端: {qq_exe}")
    else:
        line(BAD, f"找不到 QQ: {qq_exe}")
        problems.append("QQ 路径不对，NapCat 需要它")
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq QQ.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10).stdout
        n = out.lower().count("qq.exe")
        if n:
            line(WARN, f"QQ 正在运行（{n} 个进程）—— 挂载 NapCat 前需要先完全退出 QQ")
        else:
            line(OK, "QQ 当前未运行（适合挂载 NapCat）")
    except Exception as e:
        line(WARN, f"无法检查 QQ 进程: {e}")


def check_files():
    print("\n== 关键文件 ==")
    for rel in ("app\\main.py", "app\\popup.py", "app\\filter.py",
                "app\\config.py", "app\\jsonio.py", "config.json",
                "start-watcher.bat", "tools\\simulate.py"):
        p = os.path.join(BASE, rel)
        line(OK if os.path.exists(p) else BAD, rel)
        if not os.path.exists(p):
            problems.append(f"缺文件 {rel}")


if __name__ == "__main__":
    print("=" * 64)
    print("  QQ 志愿活动秒级提醒系统 — 自检")
    print("=" * 64)
    check_python()
    check_libs()
    check_files()
    check_config()
    check_port()
    check_napcat()
    check_qq()
    print("\n" + "=" * 64)
    if problems:
        print("发现需要处理的问题：")
        for p in problems:
            print("  - " + p)
    else:
        print("自检通过，没有发现阻塞问题 ✓")
    print("=" * 64)

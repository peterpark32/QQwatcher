# -*- coding: utf-8 -*-
"""登录二维码显示器：把 NapCat 的登录二维码放大到全屏并自动刷新。

为什么需要：
QQ 的登录二维码每约 2 分钟就过期。NapCat 会把最新二维码写到
napcat\\cache\\qrcode.png，但那个图只有 147x147 像素，而且过期后
你手机扫上去只会失败——非常容易让人以为"扫了没用"。
本工具全屏放大显示，并且每 2 秒检查一次文件，二维码一更新就换图，
过期倒计时也直接标出来，让登录这件事变得没有歧义。

用法:
    python tools\\show_qrcode.py            # 全屏显示并自动刷新
    python tools\\show_qrcode.py --file xxx.png
"""
import argparse
import os
import sys
import time
import tkinter as tk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None

DEFAULT_QR = os.path.join(BASE, "napcat", "cache", "qrcode.png")
REFRESH_MS = 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_QR)
    ap.add_argument("--windowed", action="store_true", help="窗口模式，不全屏")
    args = ap.parse_args()

    if Image is None:
        print("缺少 Pillow，无法显示图片")
        return 1

    root = tk.Tk()
    root.title("QQ 登录二维码 — 用手机 QQ 扫码登录 2014713076")
    root.configure(bg="#0b1f33")
    if not args.windowed:
        try:
            root.state("zoomed")
        except Exception:
            root.geometry("900x900")
    else:
        root.geometry("520x620")
    root.attributes("-topmost", True)

    head = tk.Label(root, text="用手机 QQ 扫码登录  2014713076",
                    fg="#7dd3ff", bg="#0b1f33",
                    font=("Microsoft YaHei UI", 24, "bold"))
    head.pack(pady=(14, 4))

    status = tk.Label(root, text="", fg="#ffd479", bg="#0b1f33",
                      font=("Microsoft YaHei UI", 14))
    status.pack(pady=(0, 8))

    canvas = tk.Label(root, bg="#0b1f33")
    canvas.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    tip = tk.Label(
        root,
        text="手机 QQ → 左上角头像 → 扫一扫（不要用微信扫）\n"
             "二维码约 2 分钟过期，本窗口会自动换成最新的",
        fg="#9fc6e8", bg="#0b1f33", font=("Microsoft YaHei UI", 12),
        justify="center")
    tip.pack(pady=(0, 12))

    state = {"tk": None, "mtime": None, "size": (0, 0), "job": None, "born": time.time()}

    def show():
        try:
            if not os.path.exists(args.file):
                status.configure(text=f"等二维码文件出现… ({args.file})")
                return
            m = os.path.getmtime(args.file)
            w_win, h_win = canvas.winfo_width(), canvas.winfo_height()
            if w_win < 60 or h_win < 60:
                return
            if m == state["mtime"] and (w_win, h_win) == state["size"] and state["tk"]:
                return
            state["mtime"] = m
            state["size"] = (w_win, h_win)
            state["born"] = time.time()

            im = Image.open(args.file)
            im.load()
            im = im.convert("RGB")
            # 放大到可用空间，留边距；qr 原图很小，放大后手机更容易扫
            side = max(120, min(w_win - 40, h_win - 40))
            im = im.resize((side, side), Image.NEAREST if side > 900 else Image.LANCZOS)
            tkimg = ImageTk.PhotoImage(im)
            state["tk"] = tkimg
            canvas.configure(image=tkimg, text="")
            canvas.image = tkimg
            age = int(time.time() - m)
            status.configure(
                text=f"二维码已更新（{age} 秒前生成）· 文件 {os.path.basename(args.file)}")
        except Exception as e:
            status.configure(text=f"读取二维码失败: {e}")

    def tick():
        show()
        # 提示二维码新鲜度
        try:
            if os.path.exists(args.file):
                age = int(time.time() - os.path.getmtime(args.file))
                if age > 110:
                    status.configure(
                        text=f"这张码已经 {age} 秒了，可能即将过期 —— 等它自动刷新",
                        fg="#ff9f7d")
                else:
                    status.configure(fg="#ffd479")
        except Exception:
            pass
        root.after(REFRESH_MS, tick)

    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<F5>", lambda e: show())
    root.after(200, tick)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

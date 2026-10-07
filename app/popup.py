# -*- coding: utf-8 -*-
"""命中后的全屏二维码弹窗（独立进程，避免拖慢监听主服务）。

用法: python popup.py <请求JSON文件路径>

为什么用文件传参：命令行里塞 JSON 会被 PowerShell / cmd 吞掉双引号，
中文还有编码问题。传一个路径，零歧义。
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import tkinter as tk
import urllib.request

# 进程起点，用于埋点测量真实延迟
T0 = time.perf_counter()
PERF = os.environ.get("WATCHER_PERF", "") == "1"


def perf(label):
    if PERF:
        try:
            print(f"[perf] {label}: {(time.perf_counter()-T0)*1000:.0f} ms", flush=True)
        except Exception:
            pass

try:
    from PIL import Image, ImageTk, ImageGrab
except Exception:
    Image = None

perf("imports done")


def beep():
    """响铃。

    必须在后台线程里跑：winsound.Beep 是【阻塞】调用，
    6 声蜂鸣会堵住主线程 1.1 秒——而那一秒正是抢名额最宝贵的时间。
    实测过：同步响铃会把窗口可见时间从 189ms 拖到 1519ms。
    """
    def worker():
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(880, 180)
                winsound.Beep(1320, 180)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def fetch_to_file(url, dst, timeout=12):
    """把图片来源变成本地文件。

    必须支持四种形态，否则二维码显示不出来：
      · http(s)://...    —— QQ 图床，需要联网下载
      · file:///C:/...   —— NapCat 给的本地路径
      · C:\\...          —— 本地绝对路径（enableLocalFile2Url 关闭时常见）
      · base64://<数据>  —— 图片直接内嵌在事件里

    注意：URL 形态（尤其是 base64 或本地路径）可能已经带前缀，
    调用方在交给本函数前应先用 split_prefixed_path 剥掉前缀。
    """
    if not url:
        raise ValueError("空图片地址")

    # base64 内嵌
    if url.lower().startswith("base64://"):
        import base64
        blob = base64.b64decode(url[9:])
        if not blob:
            raise IOError("base64 内容为空")
        with open(dst, "wb") as f:
            f.write(blob)
        return dst

    # http / https
    if re.match(r"https?://", url, re.I):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            blob = r.read()
        if not blob:
            raise IOError("空响应")
        with open(dst, "wb") as f:
            f.write(blob)
        return dst

    # file:///C:/x/y.png
    if url.lower().startswith("file:///"):
        src = url[8:].replace("/", os.sep)
    elif url.lower().startswith("file://"):
        src = url[7:].replace("/", os.sep)
    else:
        src = url

    if os.path.exists(src):
        shutil.copyfile(src, dst)
        return dst
    raise FileNotFoundError(f"本地图片不存在: {src}")


def split_prefixed_path(value):
    """把前缀和内容分开，返回 (前缀, 内容)。

    main.py 交给我们的可能是 "base64://<数据>" 或 "file:///C:/x.jpg"
    这种自带协议前缀的字符串。前缀要单独处理，不能当路径去拼。
    """
    low = value.lower()
    for pre in ("base64://", "file:///", "file://"):
        if low.startswith(pre):
            return pre, value[len(pre):]
    return "", value


def resolve_source(source, local_path, dst, wait=5.0, timeout=12):
    """取得图片文件，返回实际使用的来源说明。

    时序设计（这是速度与可靠性的平衡点）：
      监听服务在拉起本窗口的同时，会自己把图片存到 local_path。
      本函数先等这个本地文件出现（通常几十毫秒内就有了）——
      这样既能立刻显示，又避免重新去下载一个可能已过期的 QQ 图片链接。
      等不到才回退到用 source 自己下载。

    QQ 图片链接带临时 rkey，会失效，所以"等本地文件"这条路更可靠。
    """
    deadline = time.time() + wait
    while time.time() < deadline:
        if local_path and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            try:
                shutil.copyfile(local_path, dst)
                return "local"
            except Exception:
                break
        time.sleep(0.08)

    # 回退：自己解析 source
    pre, body = split_prefixed_path(source or "")
    if pre == "base64://":
        fetch_to_file(source, dst, timeout=timeout)
        return "base64"
    if pre:
        # file:/// 形态，body 是路径
        if os.path.exists(body):
            shutil.copyfile(body, dst)
            return "file"
        raise FileNotFoundError(f"本地图片不存在: {body}")
    if re.match(r"https?://", body, re.I):
        fetch_to_file(body, dst, timeout=timeout)
        return "http"
    if os.path.exists(body):
        shutil.copyfile(body, dst)
        return "path"
    raise FileNotFoundError(f"无法取得图片: {source[:120]}")


def main():
    req = {}
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        from jsonio import load_json_loose
        req = load_json_loose(sys.argv[1], default={})
    paths = list(req.get("paths") or [])
    image_urls = list(req.get("image_urls") or [])
    text = req.get("text") or ""
    meta = req.get("meta") or {}

    root = tk.Tk()
    root.title("⚡ 志愿活动提醒 — 立刻扫码报名")
    root.attributes("-topmost", True)
    root.configure(bg="#0b3d2c")
    try:
        root.state("zoomed")
    except Exception:
        root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
    perf("Tk window created")
    # 立刻渲染一次，让"窗口已经出现"这件事尽可能早发生，
    # 而不是等所有控件都搭好
    try:
        root.update_idletasks()
        root.update()
    except Exception:
        pass
    perf("first paint")

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    # 标题栏
    head = tk.Frame(root, bg="#0b3d2c")
    head.pack(fill="x", side="top")
    tk.Label(head, text="⚡ 新志愿活动 · 立刻长按图片识别小程序码报名",
             fg="#7dffb0", bg="#0b3d2c",
             font=("Microsoft YaHei UI", 26, "bold")).pack(pady=(14, 2))
    tk.Label(head, text=f"群 {meta.get('group_id','')} · 发送者 {meta.get('user_id','')} · {meta.get('time','')}",
             fg="#9fd8bd", bg="#0b3d2c",
             font=("Microsoft YaHei UI", 13)).pack(pady=(0, 8))

    body = tk.Frame(root, bg="#0b3d2c")
    body.pack(fill="both", expand=True)

    # 左侧图片，右侧文字
    left = tk.Frame(body, bg="#0b3d2c")
    left.pack(side="left", fill="both", expand=True, padx=12, pady=6)
    right = tk.Frame(body, bg="#123f2f")
    right.pack(side="right", fill="y", padx=(0, 12), pady=6)

    canvas = tk.Label(left, bg="#0b3d2c")
    canvas.pack(fill="both", expand=True)

    # 图片列表：先装本地已有的，剩下的等后台下载完再补进来
    imgs = []
    for p in paths:
        if os.path.exists(p):
            try:
                im = Image.open(p)
                im.load()
                imgs.append(im)
            except Exception:
                pass

    pending = len(image_urls)
    load_state = tk.Label(head, text="", fg="#ffd479", bg="#0b3d2c",
                          font=("Microsoft YaHei UI", 13, "bold"))
    load_state.pack(pady=(0, 6))
    if pending:
        load_state.configure(text=f"正在取图 {pending} 张…（先看左边，图会自己出现）")
    else:
        load_state.configure(text="")

    state = {"i": 0, "tk": None, "job": None, "last": (0, 0), "zoom": 1.0}

    def render():
        state["job"] = None
        if not imgs:
            msg = "正在取图…（图片会自己出现在这里）" if pending else \
                  "(没取到图片，请看日志)"
            canvas.configure(text=msg, fg="#ffd479",
                             font=("Microsoft YaHei UI", 20))
            return
        w_win, h_win = left.winfo_width(), left.winfo_height()
        # 布局未完成时尺寸还是 1，直接跳过，等下一次 Configure
        if w_win < 50 or h_win < 50:
            state["job"] = root.after(80, render)
            return
        if (w_win, h_win) == state["last"] and state["tk"] is not None:
            return
        state["last"] = (w_win, h_win)

        im = imgs[state["i"]].convert("RGB") if imgs[state["i"]].mode != "RGB" else imgs[state["i"]]
        max_w, max_h = w_win - 24, h_win - 24
        w, h = im.size
        scale = min(max_w / w, max_h / h)
        if scale < 1:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        # 放大镜：手机扫小二维码时，3 倍放大能显著提高一次成功率
        if state["zoom"] != 1.0:
            nw, nh = int(im.size[0] * state["zoom"]), int(im.size[1] * state["zoom"])
            nw, nh = max(1, min(nw, 20000)), max(1, min(nh, 20000))
            im = im.resize((nw, nh), Image.LANCZOS)
        tkimg = ImageTk.PhotoImage(im)
        state["tk"] = tkimg
        canvas.configure(image=tkimg, text="")
        canvas.image = tkimg  # 保住引用，否则空白

    def set_zoom(z):
        state["zoom"] = max(0.5, min(8.0, z))
        state["last"] = (0, 0)
        render()
        root.title(f"⚡ 志愿活动提醒 — 立刻扫码报名   [放大 {state['zoom']:.1f}x]")

    def schedule(_=None):
        """防抖：Configure 会连发几十次，取消上一个未执行的任务。"""
        if state["job"] is not None:
            try:
                root.after_cancel(state["job"])
            except Exception:
                pass
        state["job"] = root.after(60, render)

    def next_img(_=None):
        if imgs:
            state["i"] = (state["i"] + 1) % len(imgs)
            state["last"] = (0, 0)
            render()

    canvas.bind("<Button-1>", next_img)
    # 只在主窗口尺寸变化时重排，忽略内部子控件的 Configure
    root.bind("<Configure>", lambda e: schedule() if e.widget is root else None)
    root.after(150, render)

    img_count = tk.Label(right, text="", fg="#9fd8bd", bg="#123f2f",
                         font=("Microsoft YaHei UI", 11), justify="left")
    img_count.pack(anchor="w", padx=12, pady=(4, 4))

    def refresh_count():
        img_count.configure(
            text=f"共 {len(imgs)} 张图 · 点击图片切换\n"
                 f"上一张/下一张：空格 · 关闭：Esc")

    refresh_count()

    # ---- 后台补图：窗口已经弹出来了，图片一边取一边显示 ----
    def bg_load():
        # 每个请求用独立缓存目录：固定文件名会让同时弹出的多个窗口互相覆盖
        stamp = str(int(time.time() * 1000))
        cache_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "images", "popup-cache", stamp)
        os.makedirs(cache_dir, exist_ok=True)
        # 监听服务在拉起本窗口的同时会把图片写到这些本地路径。
        # 优先等它们出现，比重新下载一个可能已过期的 QQ 链接更可靠。
        local_paths = list(req.get("local_paths") or [])
        for idx, u in enumerate(image_urls, 1):
            lp = local_paths[idx - 1] if idx - 1 < len(local_paths) else None
            try:
                dst = os.path.join(cache_dir, f"img{idx}.jpg")
                resolve_source(u, lp, dst)
                im = Image.open(dst)
                im.load()
                root.after(0, lambda im=im: add_image(im, None))
            except Exception as e:
                root.after(0, lambda e=e: add_image(None, str(e)))

    def add_image(im, err):
        nonlocal pending
        pending = max(0, pending - 1)
        if im is not None:
            first = not imgs
            imgs.append(im)
            if first:
                state["i"] = 0
                state["last"] = (0, 0)
                render()
        refresh_count()
        if pending > 0:
            load_state.configure(text=f"正在取图，还剩 {pending} 张…")
        else:
            load_state.configure(text="图片已就绪" if imgs else "图片获取失败（看日志）")

    if image_urls:
        threading.Thread(target=bg_load, daemon=True).start()

    # 右侧文字
    tk.Label(right, text="消息原文", fg="#7dffb0", bg="#123f2f",
             font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
    txt = tk.Text(right, width=42, wrap="char", bg="#0e3327", fg="#e8fff4",
                  insertbackground="#e8fff4", font=("Microsoft YaHei UI", 12),
                  relief="flat", height=16)
    txt.pack(padx=12, pady=4, fill="both", expand=True)
    txt.insert("1.0", text or "(无文字，直接看图)")
    txt.configure(state="disabled")

    # 放大镜按钮组：扫小二维码时很有用
    zbar = tk.Frame(right, bg="#123f2f")
    zbar.pack(fill="x", padx=12, pady=(0, 6))
    tk.Label(zbar, text="放大:", fg="#9fd8bd", bg="#123f2f",
             font=("Microsoft YaHei UI", 11)).pack(side="left")
    for label, z in (("1x", 1.0), ("2x", 2.0), ("3x", 3.0), ("4x", 4.0)):
        tk.Button(zbar, text=label, command=lambda z=z: set_zoom(z),
                  bg="#1f7a55", fg="white", relief="flat", width=3,
                  font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=2)

    def save_all():
        try:
            ImageGrab.grab().save(os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "logs", "shot.png"))
        except Exception:
            pass

    tk.Button(right, text="关闭 (Esc)", command=root.destroy,
              bg="#1f7a55", fg="white", relief="flat",
              font=("Microsoft YaHei UI", 13, "bold")).pack(padx=12, pady=(0, 12), fill="x")
    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<space>", next_img)
    # 快捷键：+/- 缩放，1 复位
    root.bind("<plus>", lambda e: set_zoom(state["zoom"] * 1.5))
    root.bind("<equal>", lambda e: set_zoom(state["zoom"] * 1.5))
    root.bind("<minus>", lambda e: set_zoom(state["zoom"] / 1.5))
    root.bind("<Key-1>", lambda e: set_zoom(1.0))

    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    perf("before mainloop")
    beep()
    perf("after beep")
    root.mainloop()


if __name__ == "__main__":
    main()

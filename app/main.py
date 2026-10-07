# -*- coding: utf-8 -*-
"""主监听服务。

链路：NapCat --HTTP POST--> 本机 127.0.0.1:18080 --> 判定 --> 秒级动作

设计要点：
1. HTTP 线程收到事件后立刻返回 204，重活丢给后台线程，绝不让 NapCat 等待。
2. 只绑定 127.0.0.1，不对外开放端口。
3. 先落盘日志与图片，再并行触发「手机推送」和「全屏弹窗」，互不阻塞。
"""
import json
import os
import queue
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，中文/符号会直接抛 UnicodeEncodeError 把程序打死。
# 统一把标准输出切成 UTF-8，并且永不因编码问题抛异常。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.config import CFG  # noqa: E402
from app.filter import judge, plain_text  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
POPUP_SCRIPT = os.path.join(APP_DIR, "popup.py")
PYTHON = sys.executable

T0 = time.perf_counter()
TASK_Q = queue.Queue(maxsize=200)
STATS = {
    "收到": 0,          # 消息类事件（message）
    "POST总数": 0,      # 收到的所有 HTTP 上报（含心跳、生命周期）
    "事件类型": {},     # 各类 post_type 计数，用于诊断链路是否真的通
    "命中": 0,
    "弹窗": 0,
    "推送成功": 0,
    "推送失败": 0,
    "上次命中": None,
    "上次上报": None,
}


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def log(msg, also_console=True):
    line = f"[{ts()}] {msg}"
    try:
        os.makedirs(CFG.log_dir, exist_ok=True)
        with open(os.path.join(CFG.log_dir, "watcher.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if also_console:
        try:
            print(line, flush=True)
        except Exception:
            pass


def log_event(kind, payload):
    """把原始事件按天归档，方便校准与排查。"""
    try:
        day = datetime.now().strftime("%Y%m%d")
        path = os.path.join(CFG.log_dir, f"{kind}-{day}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- 图片落地
def download_image(url_or_file, tag):
    """把活动图片存到本地。

    NapCat 给的图片地址有四种可能，都必须处理，否则图片存不下来：
      file:///C:/...  本地文件
      C:\\...         本地绝对路径
      http(s)://...   QQ 图床，需要下载
      base64://...    内嵌数据
    """
    if not url_or_file:
        return None
    src = url_or_file

    if src.lower().startswith("base64://"):
        import base64
        blob = base64.b64decode(src[9:])
        dst = os.path.join(CFG.image_dir, f"{tag}.jpg")
        with open(dst, "wb") as f:
            f.write(blob)
        return dst

    if src.lower().startswith("file:///"):
        p = src[8:].replace("/", os.sep)
    elif src.lower().startswith("file://"):
        p = src[7:].replace("/", os.sep)
    else:
        p = src

    if os.path.isabs(p) and os.path.exists(p):
        ext = os.path.splitext(p)[1] or ".jpg"
        dst = os.path.join(CFG.image_dir, f"{tag}{ext}")
        with open(p, "rb") as fi, open(dst, "wb") as fo:
            fo.write(fi.read())
        return dst

    if src.lower().startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            blob = r.read()
        dst = os.path.join(CFG.image_dir, f"{tag}.jpg")
        with open(dst, "wb") as f:
            f.write(blob)
        return dst
    return None


# ---------------------------------------------------------------- 动作
def fire_popup(paths, text, meta, image_urls=None, images=None, local_paths=None):
    """拉起全屏弹窗。

    paths       : 已经落地到本地的图片（首选，最可靠）
    image_urls  : 兜底来源，弹窗拿不到本地文件时才去下载
    local_paths : 监听服务"预计"会写出的本地路径，供弹窗短暂等待
    关键：即使一张图都还没下载成功，也立刻弹窗（不然会白白浪费下载时间）。
    """
    if not CFG.popup:
        return
    try:
        import subprocess
        outbox = os.path.join(CFG.log_dir, "outbox")
        os.makedirs(outbox, exist_ok=True)
        req_path = os.path.join(
            outbox, datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump({"paths": paths or [],
                       "image_urls": image_urls or [],
                       "local_paths": local_paths or [],
                       "images": images or [],
                       "text": text,
                       "meta": meta},
                      f, ensure_ascii=False)
        # 只传一个文件路径，避免引号/中文/空格被 shell 吞掉
        subprocess.Popen(
            [PYTHON, POPUP_SCRIPT, req_path],
            cwd=BASE_DIR,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
        )
        STATS["弹窗"] += 1
        log(f"  已拉起全屏弹窗（本地 {len(paths or [])} 张，"
            f"待补 {len(image_urls or [])} 张）")
        prune_outbox(outbox)
    except Exception as e:
        log(f"  弹窗失败: {e}")


def prune_outbox(outbox, keep=40):
    try:
        files = sorted(
            (os.path.join(outbox, n) for n in os.listdir(outbox)),
            key=os.path.getmtime, reverse=True)
        for p in files[keep:]:
            os.remove(p)
    except Exception:
        pass


def fire_push(text, meta, paths):
    if not CFG.push_enabled or not CFG.send_key or "在这里填" in CFG.send_key:
        return
    title = meta.get("title") or "QQ 志愿活动提醒"
    body = []
    body.append(f"**群**: {meta.get('group_id')}")
    body.append(f"**发送者**: {meta.get('user_id')}")
    body.append(f"**时间**: {meta.get('time')}")
    body.append("")
    body.append(text or "(无文字)")
    body.append("")
    body.append("👉 打开 QQ 查看原图，长按识别小程序码报名")
    try:
        data = urllib.parse.urlencode({
            "title": title,
            "desp": "\n".join(body),
        }).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{CFG.send_key}.send", data=data)
        with urllib.request.urlopen(req, timeout=8) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
        if resp.get("code") == 0:
            STATS["推送成功"] += 1
            log("  手机推送已发出 ✓")
        else:
            STATS["推送失败"] += 1
            log(f"  手机推送返回异常: {resp}")
    except Exception as e:
        STATS["推送失败"] += 1
        log(f"  手机推送失败: {e}")


def fire_qq_images(paths, meta):
    """把原图私聊发到目标 QQ（可选），方便手机上长按识别。"""
    if not CFG.push_qq_image or not CFG.target_qq or not paths:
        return
    try:
        for p in paths:
            payload = json.dumps({
                "user_id": CFG.target_qq,
                "message": [{"type": "image", "data": {"file": p}}],
            }).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{CFG.onebot_port}/send_private_msg",
                data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()
        log(f"  已把 {len(paths)} 张原图私聊发到 {CFG.target_qq}")
    except Exception as e:
        log(f"  发原图到 QQ 失败: {e}")


def maybe_reload_config():
    """config.json 被改过就自动热重载（比较 mtime），省掉重启步骤。"""
    global _cfg_mtime
    try:
        m = os.path.getmtime(CFG.path)
    except OSError:
        return
    if m != _cfg_mtime:
        first = _cfg_mtime is None
        _cfg_mtime = m
        if first:
            return
        port_before = getattr(CFG, "onebot_port", None)
        CFG.reload()
        CFG.onebot_port = port_before or CFG.port + 1
        log("检测到 config.json 变更，已热重载")
        log(f"  干跑模式={CFG.dry_run} 弹窗={CFG.popup} 推送={bool(CFG.send_key)}")


_cfg_mtime = None

# 去重表：{第一张图URL: 时间戳}
# 为什么需要：NapCat 断线重连、消息重发、管理员自己重发同一条活动，
# 都会让同一条活动图再次进来。没有去重就会弹出一堆一模一样的全屏窗口，
# 反而把真正要扫的那张码埋在窗口堆里。
_SEEN = {}
_SEEN_TTL = 600.0  # 10 分钟内同一张图只提醒一次


def is_duplicate(info):
    urls = [i["url"] for i in info.get("images") or [] if i.get("url")]
    if not urls:
        return False
    key = urls[0]
    now = time.time()
    # 顺手清理过期项，避免字典无限增长
    for k in [k for k, t in _SEEN.items() if now - t > _SEEN_TTL]:
        _SEEN.pop(k, None)
    if key in _SEEN:
        return True
    _SEEN[key] = now
    return False


def worker():
    while True:
        item = TASK_Q.get()
        try:
            kind, payload = item
            if kind == "event":
                handle_event(payload)
            elif kind == "stats":
                log(f"统计: {STATS}")
        except Exception:
            log("worker 异常:\n" + traceback.format_exc())
        finally:
            TASK_Q.task_done()


def handle_event(event):
    maybe_reload_config()
    hit, info = judge(event)

    # 隐私考虑：NapCat 无法按群过滤，它会把该账号看到的全部事件推过来，
    # 本服务是唯一的过滤层。所以归档只记录【监听列表内的群】，
    # 其他群和私聊的内容一律不落盘。
    in_scope = (not CFG.groups) or (info["group_id"] in CFG.groups)

    if CFG.log_all and in_scope:
        log_event("all", {
            "ts": ts(), "hit": hit, "reasons": info["reasons"],
            "text": info["text"], "images": info["images"],
            "group_id": info["group_id"], "user_id": info["user_id"],
        })

    if not in_scope:
        # 不在监听范围内的（其他群、私聊、通知类事件）只记一行摘要，不落内容
        log(f"范围外忽略 类型={event.get('message_type') or event.get('post_type')} "
            f"群{info['group_id']} 用户{info['user_id']}")
        return

    tag_txt = "命中 ✓" if hit else "忽略"
    log(f"{tag_txt} 群{info['group_id']} 用户{info['user_id']} | {info['reasons']} | 文本: {info['text'][:80]}")

    if not hit:
        return

    STATS["命中"] += 1
    STATS["上次命中"] = ts()

    stamp = datetime.now().strftime("%m%d-%H%M%S")
    urls = [img["url"] for img in info["images"] if img.get("url")]

    meta = {
        "title": f"志愿活动! {stamp}",
        "group_id": info["group_id"],
        "user_id": info["user_id"],
        "time": ts(),
        "reasons": info["reasons"],
    }
    log_event("hit", {**meta, "text": info["text"], "images": urls,
                      "image_hosts": info.get("image_hosts", [])})

    if CFG.dry_run:
        log("  [干跑模式] 不弹窗、不推送。开启正式模式请把 config.json 的 干跑模式 改为 false")
        return

    if is_duplicate(info):
        log("  [去重] 这条活动的图片刚落过，跳过重复提醒")
        return

    # 分层：每件事各占一个后台线程，谁都不阻塞谁。
    # 抢名额最值钱的是"看到二维码"的秒数，所以手机推送必须立刻出发。
    threading.Thread(target=fire_push, args=(info["text"], meta, None),
                     daemon=True).start()

    # 图片先落地再用本地文件弹窗：QQ 图片链接带临时 rkey 会过期，
    # 本地文件则永远可靠。本地路径（笔记本上的 QQ 常见情形）几乎是瞬间的。
    stamp_imgs = datetime.now().strftime("%m%d-%H%M%S")
    paths, expected = [], []
    for i, img in enumerate(info["images"], 1):
        name = f"{stamp_imgs}-{info['user_id']}-{i}"
        try:
            p = download_image(img["url"], name)
            if p:
                paths.append(p)
        except Exception as e:
            log(f"  图片{i} 落地失败: {e}")
        # 预测落地后会用的路径，供弹窗进程等待（下载成功与否都要给）
        expected.append(os.path.join(CFG.image_dir, f"{name}.jpg"))
    if paths:
        log(f"  图片已存档 {len(paths)} 张")
        meta["images"] = paths
        threading.Thread(target=fire_qq_images, args=(paths, meta),
                         daemon=True).start()

    fire_popup(paths, info["text"], meta, image_urls=urls,
               images=info["images"], local_paths=expected)


def bg_download_images(urls, stamp, info, meta):
    """（保留给扩展用）纯后台落图，不参与弹窗时序。"""
    paths = []
    for i, u in enumerate(urls, 1):
        try:
            p = download_image(u, f"{stamp}-{info['user_id']}-{i}")
            if p:
                paths.append(p)
        except Exception as e:
            log(f"  图片{i} 落地失败: {e}")
    if paths:
        log(f"  图片已存档 {len(paths)} 张")
        meta["images"] = paths
        fire_qq_images(paths, meta)


# ---------------------------------------------------------------- HTTP 接收
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _reply(self, code=204, body=b""):
        """回包。

        两个都踩过的坑：

        1. 204 响应绝对不能带 Content-Length。
           RFC 7230 规定 204 (No Content) 不得包含消息体，其 Content-Length
           不能为 0。带了会让 Node.js 解析器判定响应非法。

        2. 回包后必须关闭连接（Connection: close + close_connection）。
           本服务用 HTTP/1.1 keep-alive 时，Node.js 客户端会复用同一个
           socket 连续发送事件；而 BaseHTTPRequestHandler 在一次请求后
           并不能可靠地重新对齐字节流，客户端下一次读取就会读到错位数据，
           报 "Parse Error: Expected HTTP/, RTSP/ or ICE/"。
           事件频率极低，不复用连接零成本，因此直接关闭最稳。
        """
        self.send_response(code)
        if code != 204:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        if code != 204 and body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._reply(200, json.dumps({"ok": True, "stats": STATS},
                                        ensure_ascii=False).encode())
        else:
            self._reply(404)

    def do_POST(self):
        STATS["POST总数"] += 1
        STATS["上次上报"] = ts()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            event = json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            log(f"事件解析失败: {e}")
            log_event("parseerror", {"ts": ts(), "err": str(e),
                                     "body": self._peek_raw if hasattr(self, "_peek_raw") else ""})
            self._reply(204)
            return

        # 立刻回包，NapCat 不会被拖住
        self._reply(204)

        etype = event.get("post_type") or "未知"
        STATS["事件类型"][etype] = STATS["事件类型"].get(etype, 0) + 1

        # 非 message 的事件以前只看计数，结果排查时完全不知道它们是什么。
        # 这里把每条非常规事件都记下来，便于诊断链路。
        if etype not in ("message", "meta_event"):
            log_event("otherevent", {
                "ts": ts(),
                "post_type": event.get("post_type"),
                "keys": list(event.keys())[:20],
                "preview": json.dumps(event, ensure_ascii=False)[:600],
            })

        if etype == "message":
            STATS["收到"] += 1
            try:
                TASK_Q.put_nowait(("event", event))
            except queue.Full:
                log("任务队列满，丢弃一条事件")
        elif STATS["POST总数"] <= 3 or STATS["POST总数"] % 50 == 0:
            # 心跳 / 生命周期：只记前几条和每 50 条一次，避免刷屏
            log(f"  收到 {etype} 事件（第 {STATS['POST总数']} 次上报，链路正常）")


def main():
    CFG.reload()
    # onebot 自身回调用端口（用于可选地发原图给自己），默认取接收端口+1
    CFG.onebot_port = CFG.port + 1

    log("=" * 68)
    log("QQ 志愿活动秒级提醒系统 启动")
    log(f"  监听群号      : {sorted(CFG.groups)}")
    log(f"  关键发送者    : {sorted(CFG.senders)}")
    log(f"  关键词        : {CFG.keywords}")
    log(f"  必须含图片    : {CFG.need_image}")
    log(f"  接收地址      : http://127.0.0.1:{CFG.port}/")
    log(f"  干跑模式      : {'是（只记录不动作）' if CFG.dry_run else '否（正式提醒）'}")
    log(f"  全屏弹窗      : {CFG.popup}   声音: {CFG.sound}")
    log(f"  手机推送      : {'已启用' if CFG.push_enabled and CFG.send_key else '未配置'}")
    log(f"  原图目录      : {CFG.image_dir}")
    log("=" * 68)

    for _ in range(3):
        threading.Thread(target=worker, daemon=True).start()

    # 后台检查上报链路。
    # NapCat 只在启动时连接一次 httpClients：如果它启动时本服务还没监听，
    # 那条推送连接就会永久失效——表现就是"两边都在跑，但一个事件都收不到"。
    # 所以启动后持续观察，长时间收不到事件就主动告警，
    # 而不是让你在错过名额之后才发现。
    threading.Thread(target=pipeline_health_check, daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", CFG.port), Handler)
    log(f"已就绪，等待 NapCat 推送事件…（健康检查 http://127.0.0.1:{CFG.port}/health）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("收到中断，退出")


def pipeline_health_check():
    """启动后观察一段时间：如果 NapCat 明明在线却一直没事件，主动告警。

    这一步专门用来抓 NapCat httpClients 没加载的情况——
    它是这个系统最隐蔽的失效形态：所有进程都活着，日志也正常，
    但事件从来不会到达。
    """
    import socket

    def napcat_alive():
        s = socket.socket()
        s.settimeout(1.0)
        try:
            return s.connect_ex(("127.0.0.1", CFG.onebot_port)) == 0
        finally:
            s.close()

    # 给 NapCat 足够的连接时间，再判断
    time.sleep(180)
    while True:
        try:
            if STATS["收到"] == 0 and not napcat_alive():
                log("  [链路检查] NapCat 未就绪（OneBot 端口未监听）——"
                    "请确认 NapCat 已登录")
            elif STATS["收到"] == 0 and napcat_alive():
                log("  [链路检查] NapCat 在线但本服务【一个事件都没收到】——"
                    "上报通道很可能没加载。")
                log("             解决办法：运行 一键重启NapCat.vbs，"
                    "或先手动退出 QQ 再重启 NapCat。")
        except Exception:
            pass
        time.sleep(600)


if __name__ == "__main__":
    main()

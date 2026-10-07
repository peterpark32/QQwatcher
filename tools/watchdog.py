# -*- coding: utf-8 -*-
"""看门狗：定时检查监听服务是否还活着，失效就告警。

为什么必须有这个：
监听服务是个普通后台进程，它可能因为各种原因静默死掉——Python 抛异常、
端口被占、系统休眠恢复、手动误关。死掉之后日志不再增长，而你不会主动去翻日志，
结果就是"以为在监控，实际早断了"，等名额出来才发现没提醒。
这正是这类工具最危险的失效形态：静默失败。

检查项：
  1. 监听服务健康接口是否响应
  2. 是否很久没收到任何 QQ 事件（默认 24 小时）
  3. 端口 18081（NapCat 的 OneBot API）是否在

告警通道：
  · Server酱（如果配了 SendKey）—— 会推到你手机
  · 本地告警文件 logs\\alerts.log
  · 桌面弹窗（复用 popup.py，醒目）

用法:
    python tools\\watchdog.py                # 常驻循环，每 60 秒检查一次
    python tools\\watchdog.py --once         # 只查一次（适合放进计划任务）
    python tools\\watchdog.py --interval 30
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "app"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from jsonio import load_json_loose  # noqa: E402

LOG_DIR = os.path.join(BASE, "logs")
ALERT_LOG = os.path.join(LOG_DIR, "alerts.log")
STATE_FILE = os.path.join(LOG_DIR, "watchdog-state.json")
POPUP = os.path.join(BASE, "app", "popup.py")
PYTHON = sys.executable


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_settings():
    cfg = load_json_loose(os.path.join(BASE, "config.json"), default={})
    listen = cfg.get("监听") or {}
    push = cfg.get("手机推送") or {}
    return {
        "port": int(listen.get("接收端口", 18080)),
        "onebot_port": int(listen.get("接收端口", 18080)) + 1,
        "send_key": str(push.get("ServerChanSendKey") or "").strip(),
        "push_enabled": bool(push.get("启用")),
        "stale_hours": 24,
    }


def http_get(url, timeout=6):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(1.5)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def log_alert(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{now()}] {msg}"
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def send_phone(settings, title, body):
    if not (settings["push_enabled"] and settings["send_key"] and "在这里填" not in settings["send_key"]):
        return False
    try:
        data = urllib.parse.urlencode({"title": title, "desp": body}).encode()
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{settings['send_key']}.send", data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
        return resp.get("code") == 0
    except Exception as e:
        print(f"  手机告警发送失败: {e}", flush=True)
        return False


def desktop_alert(title, body):
    """弹一个醒目的窗口。复用 popup.py 的渲染能力。"""
    try:
        req = os.path.join(LOG_DIR, "outbox", "watchdog.json")
        os.makedirs(os.path.dirname(req), exist_ok=True)
        with open(req, "w", encoding="utf-8") as f:
            json.dump({
                "paths": [],
                "image_urls": [],
                "text": f"{title}\n\n{body}",
                "meta": {"group_id": "看门狗", "user_id": "系统",
                         "time": now(), "alert": True},
            }, f, ensure_ascii=False)
        subprocess.Popen(
            [PYTHON, POPUP, req], cwd=BASE,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True)
        return True
    except Exception as e:
        print(f"  桌面告警失败: {e}", flush=True)
        return False


def load_state():
    return load_json_loose(STATE_FILE, default={}) or {}


def save_state(state):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_once(settings, state):
    """只做检测，返回 (是否健康, 问题列表)。发不发告警由调用方决定。"""
    problems = []

    # 1. 监听服务健康接口
    stats = None
    try:
        stats = http_get(f"http://127.0.0.1:{settings['port']}/health")
        state["last_ok"] = now()
    except Exception as e:
        problems.append(f"监听服务无响应（端口 {settings['port']}）: {e}")

    # 2. 是否很久没收到事件
    if stats:
        received = stats.get("stats", {}).get("收到", 0)
        state["last_received_count"] = received
        if received == 0:
            hours_up = state.get("first_seen_hours", 0)
            if hours_up >= settings["stale_hours"]:
                problems.append(
                    f"已经 {hours_up} 小时没收到任何 QQ 事件——"
                    f"NapCat 很可能没登录或没上报")
        else:
            state["first_seen_hours"] = 0
            state["last_event_at"] = now()

    # 3. NapCat 的 OneBot API 端口
    if not port_open(settings["onebot_port"]):
        problems.append(
            f"NapCat OneBot API 端口 {settings['onebot_port']} 未监听——"
            f"NapCat 未登录或未启动")

    return (not problems), problems


def raise_alert(settings, problems, recovered=False):
    """只在【状态发生变化】时告警一次。

    为什么不是每次都告警：常驻模式下每 60 秒检查一次，
    如果每次都推手机，你一小时会被轰炸 60 条通知，最后只能把通知关掉——
    那就等于没有告警。所以要"坏了报一次、好了报一次"。
    """
    if recovered:
        title = "✓ QQ监测系统已恢复"
        body = "监听服务重新正常了。"
    else:
        title = "⚠ QQ监测系统异常"
        body = "\n".join(f"· {p}" for p in problems)

    log_alert(title + " | " + body.replace("\n", " / "))
    sent = send_phone(settings, title, body)
    desktop_alert(title, body + ("\n\n（手机通知已发送）" if sent else
                                 "\n\n（手机通知未配置，仅本地告警）"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="检查间隔秒数")
    ap.add_argument("--once", action="store_true", help="只检查一次")
    ap.add_argument("--quiet", action="store_true", help="正常时不打印")
    args = ap.parse_args()

    settings = load_settings()
    state = load_state()
    state.setdefault("first_seen_hours", 0)
    state["watchdog_started"] = now()
    save_state(state)

    print("=" * 68)
    print("  QQ 监测系统 看门狗")
    print("=" * 68)
    print(f"  监听服务端口 : {settings['port']}")
    print(f"  NapCat 端口  : {settings['onebot_port']}")
    print(f"  手机告警     : {'已配置' if settings['send_key'] else '未配置（只写日志+弹窗）'}")
    print(f"  检查间隔     : {args.interval} 秒")
    print("=" * 68, flush=True)

    # 记录起始时间，用于"多久没收到事件"的判断
    start = time.time()
    was_ok = None  # None=还没查过，True=上次正常，False=上次异常

    while True:
        settings = load_settings()  # 每轮重读配置，改了立即生效
        state["first_seen_hours"] = round((time.time() - start) / 3600, 2)
        # 首次成功收到事件后重置计时基准
        try:
            st = http_get(f"http://127.0.0.1:{settings['port']}/health")
            if st.get("stats", {}).get("收到", 0) > 0:
                start = time.time()
        except Exception:
            pass

        ok, problems = check_once(settings, state)

        # 只在状态翻转时告警：正常->异常 报一次，异常->正常 报一次
        if was_ok is None:
            if not ok:
                raise_alert(settings, problems)   # 启动时就异常，立即报
        elif was_ok and not ok:
            print(f"[{now()}] 状态变化 正常->异常", flush=True)
            raise_alert(settings, problems)
        elif not was_ok and ok:
            print(f"[{now()}] 状态变化 异常->正常", flush=True)
            raise_alert(settings, problems, recovered=True)
        was_ok = ok

        if ok:
            if not args.quiet:
                print(f"[{now()}] 正常", flush=True)
        else:
            print(f"[{now()}] 异常: {' / '.join(problems)}", flush=True)

        save_state(state)
        if args.once:
            return 0 if ok else 2
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n看门狗已停止")

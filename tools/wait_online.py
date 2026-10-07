# -*- coding: utf-8 -*-
"""等待 NapCat 真正重启完成，并验证事件上报链路是否打通。

为什么要写得这么啰嗦：
"NapCat 端口能应答"并**不能**证明重启成功。QQ 有单实例保护——
如果旧进程没被真正结束，新启动的 QQ 会静默退出，而旧实例仍然占着
18081 端口继续应答。于是脚本会误判"已重启、已上线"，
而实际上你面对的还是那个没有上报通道的旧进程。

所以本脚本用两个硬判据：
  1. 18081 端口的持有者 PID 必须发生变化（证明进程真的换了）
  2. 监听服务的"收到"计数必须增长（证明上报通道真的通了）

用法: python tools\\wait_online.py [超时秒数]
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LISTEN_PORT = 18080
ONEBOT_PORT = 18081


def port_pid(port):
    """返回占用该端口的 PID，没有则 None。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP":
            local = parts[1]
            state = parts[3].upper() if len(parts) > 4 else ""
            if state == "LISTENING" and local.rsplit(":", 1)[-1] == str(port):
                try:
                    return int(parts[-1])
                except ValueError:
                    continue
    return None


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(1.0)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def onebot(action, payload=None, timeout=8):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{ONEBOT_PORT}/{action}", data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def received_count():
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{LISTEN_PORT}/health", timeout=4) as r:
            return json.loads(r.read().decode("utf-8", "replace")) \
                .get("stats", {}).get("收到", 0)
    except Exception:
        return None


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    baseline_pid = port_pid(ONEBOT_PORT)
    baseline_count = received_count()
    print(f"  baseline: onebot port held by PID {baseline_pid}, "
          f"listener received={baseline_count}", flush=True)

    if baseline_count is None:
        print("  [!!] 监听服务（18080）没响应。请先启动 start-watcher.bat", flush=True)
        return 3

    deadline = time.time() + timeout
    new_pid = None
    online = False

    while time.time() < deadline:
        pid = port_pid(ONEBOT_PORT)
        if pid and pid != baseline_pid:
            new_pid = pid
            try:
                info = onebot("get_login_info")
                if info.get("status") == "ok":
                    d = info.get("data") or {}
                    print(f"  [OK] NapCat restarted: PID {baseline_pid} -> {pid}, "
                          f"account {d.get('user_id')} ({d.get('nickname')})",
                          flush=True)
                    online = True
                    break
            except Exception:
                pass
        time.sleep(2)

    if not online:
        pid = port_pid(ONEBOT_PORT)
        print(f"  [!!] NapCat 没有真正重启。", flush=True)
        if pid == baseline_pid:
            print(f"       18081 仍由旧进程 PID {pid} 占用 —— 说明旧 QQ 没被结束，", flush=True)
            print(f"       新实例被 QQ 的单实例保护挡掉了。", flush=True)
            print(f"       请手动退出 QQ（托盘图标右键 -> 退出；不行就用任务管理器），", flush=True)
            print(f"       然后重新运行 一键重启NapCat.vbs。", flush=True)
        else:
            print(f"       NapCat 尚未就绪，可能需要扫码登录：", flush=True)
            print(f"         python tools\\show_qrcode.py", flush=True)
        return 2

    # 进程换了，现在验证上报通道：等它把事件推过来
    print("  waiting for events to reach the listener ...", flush=True)
    check_deadline = time.time() + 45
    count = baseline_count
    while time.time() < check_deadline:
        c = received_count()
        if c is not None and c > baseline_count:
            count = c
            print(f"  [OK] 上报链路已打通（收到事件 {baseline_count} -> {c}）", flush=True)
            print("       现在群里的新消息会自动进入监测流程。", flush=True)
            return 0
        # 主动触发一次 API 调用，NapCat 会把 API 响应事件也推给 httpClients
        try:
            onebot("get_login_info")
        except Exception:
            pass
        time.sleep(3)

    print(f"  [!!] NapCat 已重启，但监听服务仍未收到事件（收到={count}）", flush=True)
    print("       检查 napcat\\config\\onebot11_2014713076.json 的 httpClients[0].url", flush=True)
    print("       应为 http://127.0.0.1:18080/ 且 enable=true", flush=True)
    return 4


if __name__ == "__main__":
    sys.exit(main())

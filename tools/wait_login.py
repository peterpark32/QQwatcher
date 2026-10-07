import json, os, socket, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
base = r"C:\Users\wxzhe\Documents\deepseek-harness\default-workspace\qq-watcher"

def port(p):
    s = socket.socket(); s.settimeout(1)
    try: return s.connect_ex(("127.0.0.1", p)) == 0
    finally: s.close()

def call(action, payload=None):
    d = json.dumps(payload or {}).encode()
    r = urllib.request.Request("http://127.0.0.1:18081/" + action, data=d,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=8) as x:
        return json.loads(x.read().decode("utf-8", "replace"))

def health():
    with urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=5) as x:
        return json.loads(x.read().decode("utf-8", "replace"))

print("等待扫码登录（每 10 秒检查，最多 8 分钟）...", flush=True)
qr = os.path.join(base, "napcat", "cache", "qrcode.png")
for i in range(48):
    if port(18081):
        try:
            info = call("get_login_info")
            d = info.get("data") or {}
            print("", flush=True)
            print("=" * 60, flush=True)
            print(f"  登录成功！账号 {d.get('user_id')} ({d.get('nickname')})", flush=True)
            print("=" * 60, flush=True)
            time.sleep(5)
            h = health()
            print("  监听服务统计:", h.get("stats"), flush=True)
            n0 = h.get("stats", {}).get("收到", 0)
            for _ in range(4):
                try: call("get_login_info")
                except Exception: pass
                time.sleep(3)
            n1 = health().get("stats", {}).get("收到", 0)
            print("", flush=True)
            if n1 > n0:
                print(f"  ★★★ 上报链路已打通！（收到事件 {n0} -> {n1}）", flush=True)
                print("  群里的新消息现在会自动进入监测流程。", flush=True)
            else:
                print(f"  上报链路仍未收到事件（收到={n1}）", flush=True)
                print("  需要重启 NapCat 让它加载上报配置。", flush=True)
            sys.exit(0)
        except Exception as e:
            print(f"  [{i*10}s] 18081 已开但查询失败: {e}", flush=True)
    if i % 3 == 0:
        age = -1
        if os.path.exists(qr):
            age = round(time.time() - os.path.getmtime(qr))
        print(f"  [{i*10}s] 未登录  二维码年龄={age}s", flush=True)
    time.sleep(10)
print("超时：8 分钟内没有完成登录", flush=True)
sys.exit(1)
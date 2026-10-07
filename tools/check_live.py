"""启动后一键判定：链路到底通没通。"""
import json, os, socket, sys, time, urllib.request
sys.path.insert(0, r"C:\Users\wxzhe\Documents\deepseek-harness\default-workspace\qq-watcher")
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

def port(port):
    s = socket.socket(); s.settimeout(1)
    try: return s.connect_ex(("127.0.0.1", port)) == 0
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

print("=" * 62)
print("  启动后链路判定")
print("=" * 62)
print("  NapCat API (18081):", "在线" if port(18081) else "未启动")
print("  监听服务   (18080):", "在线" if port(18080) else "未启动")
print()
if not port(18081):
    print("  [!!] NapCat 还没起来。")
    print("       如果你刚双击了 一键启动NapCat.vbs 并同意了 UAC，")
    print("       请等 30-60 秒（QQ 启动 + 快速登录需要时间），然后重新跑本脚本。")
    print("       若超过 2 分钟仍是这样，说明需要扫码登录：")
    print("         python tools\\show_qrcode.py")
    sys.exit(1)

try:
    info = call("get_login_info")
    d = info.get("data") or {}
    print("  QQ 账号:", d.get("user_id"), "(", d.get("nickname"), ")")
except Exception as e:
    print("  [!!] 无法读取登录信息:", e)
    print("       NapCat 可能还没登录完成，等一会儿再试。")
    sys.exit(1)

h = health()
n0 = h.get("stats", {}).get("收到", 0)
print("  监听服务已收到事件数:", n0)
print()
print("  正在触发一次 API 调用，看事件能否送达监听服务 ...")
for _ in range(4):
    try: call("get_login_info")
    except Exception: pass
    time.sleep(3)
n1 = health().get("stats", {}).get("收到", 0)

print("=" * 62)
if n1 > n0:
    print("  成功！上报链路已打通（收到 %d -> %d）" % (n0, n1))
    print("  群里的新消息现在会自动进入监测流程。")
    print("=" * 62)
    sys.exit(0)
else:
    print("  仍未打通（收到事件始终为 %d）" % n1)
    print()
    print("  这意味着 NapCat 没有加载上报配置。请再重启一次 NapCat：")
    print("    1. 托盘退出 QQ")
    print("    2. 双击 一键重启NapCat.vbs 并同意 UAC")
    print("=" * 62)
    sys.exit(2)
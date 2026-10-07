# -*- coding: utf-8 -*-
"""端到端自测：伪装成 NapCat 往监听服务推一条假的活动消息。

用途：在真群来消息之前，就验证「接收 -> 判定 -> 落图 -> 弹窗 -> 推送」整条链。
用法:
    python tools/simulate.py            # 用样例二维码图片测试（正式模式会真弹窗）
    python tools/simulate.py nomatch    # 发一条不该命中的消息，验证不会误报
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.config import CFG  # noqa: E402

SAMPLE = os.path.join(BASE, "samples", "qr-sample-107.jpg")


def build_event(with_image=True, sender=2108873477, group=1034761242,
                text="【通知】10.7常西湖科技馆志愿 请在09月30日 18:21前加入 有意者快快报名吧",
                n_images=1, use_url=False, host="https://multimedia.nt.qq.com.cn/download"):
    """构造一条仿真群消息。

    n_images=1 且 text="" 就是真实活动消息的形态（管理员直接发二维码图）。
    use_url=True 时用远程 URL（模拟图床），否则用本地样例图。
    """
    msg = []
    if text:
        msg.append({"type": "text", "data": {"text": text}})
    for i in range(n_images):
        if use_url:
            data = {"url": f"{host}?fileid=sim{i}&rkey=sim",
                    "file": f"sim{i}.jpg", "filename": f"qr{i}.jpg"}
        else:
            data = {"file": SAMPLE,
                    "url": "file:///" + SAMPLE.replace("\\", "/"),
                    "filename": "qr.jpg"}
        msg.append({"type": "image", "data": data})
    return {
        "time": int(time.time()),
        "self_id": 2014713076,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 999001,
        "group_id": group,
        "user_id": sender,
        "raw_message": text + "".join("[CQ:image,file=sim%d.jpg]" % i for i in range(n_images)),
        "message": msg,
        "sender": {"user_id": sender, "nickname": "郑大电气青年志愿者", "role": "admin"},
    }


def send(event):
    url = f"http://127.0.0.1:{CFG.port}/"
    data = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000


def health():
    url = f"http://127.0.0.1:{CFG.port}/health"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "hit"
    try:
        h = health()
        print(f"监听服务在线  统计: {h.get('stats')}")
    except Exception as e:
        print(f"连不上监听服务 (127.0.0.1:{CFG.port})：{e}")
        print("请先运行 start-watcher.bat")
        raise SystemExit(1)

    if mode == "nomatch":
        ev = build_event(text="大家早上好，今天天气不错", with_image=False, n_images=0)
        print("发送：不含图片、无关键词的消息 -> 预期被忽略")
    elif mode == "wronggroup":
        ev = build_event(group=999999999)
        print("发送：其他群的消息 -> 预期被忽略")
    elif mode == "wrongsender":
        ev = build_event(sender=123456789)
        print("发送：普通群成员的消息 -> 预期被忽略")
    elif mode == "real":
        # 最贴近真实的形态：管理员发【单张纯图无文字】
        ev = build_event(text="", n_images=1)
        print("发送：★管理员单张纯图无文字（真实活动消息形态）-> 预期命中并弹窗")
    elif mode == "real3":
        ev = build_event(text="", n_images=3)
        print("发送：★管理员连发 3 张图无文字（截图里的模式）-> 预期命中")
    elif mode == "remote":
        ev = build_event(text="", n_images=1, use_url=True)
        print("发送：★图片只有远程URL（验证弹窗先出现、图随后补上）")
        print("      注意：这个URL是假的，弹窗会显示'正在取图'并最终取图失败，属正常")
    else:
        ev = build_event()
        print("发送：管理员 + 关键词 + 含二维码图片 -> 预期命中")

    ms = send(ev)
    print(f"推送耗时: {ms:.1f} ms（这是网络回环时间，不等于处理完成时间）")
    print("请查看 logs\\watcher.log 确认判定结果")

    time.sleep(2.5)
    try:
        h = health()
        print(f"推送后统计: {h.get('stats')}")
    except Exception:
        pass

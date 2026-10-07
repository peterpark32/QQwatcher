# -*- coding: utf-8 -*-
"""手机推送通道测试：直接发一条测试通知，验证 Server酱 是否真的可用。

为什么单独做这个：推送失败是静默的——程序照跑，日志照写，
但你手机上什么都没有。不主动测一次，你永远不知道通道通不通。

用法: python tools\\pushtest.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "app"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from jsonio import load_json_loose  # noqa: E402


def main():
    cfg = load_json_loose(os.path.join(BASE, "config.json"), default={})
    push = cfg.get("手机推送") or {}
    enabled = push.get("启用")
    key = str(push.get("ServerChanSendKey") or "").strip()

    print("=" * 62)
    print("  手机推送通道测试")
    print("=" * 62)
    print(f"  启用开关 : {enabled}")
    print(f"  SendKey  : {(key[:10] + '...' + key[-6:]) if len(key) > 20 else repr(key)}")
    print()

    if not key or "在这里填" in key or len(key) < 20:
        print("  [!!] SendKey 还没填（或仍是占位符）")
        print()
        print("  这样手机推送是【完全不可用】的——活动提醒和失效告警")
        print("  都只会在电脑上弹窗，你不在电脑前就收不到。")
        print()
        print("  获取方法：")
        print("    1. 打开 https://sct.ftqq.com")
        print("    2. 微信扫码登录")
        print("    3. 复制 SendKey")
        print("    4. 填进 config.json 的 手机推送.ServerChanSendKey")
        print("       （保存即生效，不用重启）")
        print("=" * 62)
        return 1

    data = urllib.parse.urlencode({
        "title": "QQ监测系统 · 通道测试",
        "desp": ("这是一条来自你电脑的测试通知。\n\n"
                 "如果你在手机上看到它，说明推送通道已打通，"
                 "以后志愿活动一出现你就会收到通知。"),
    }).encode()

    try:
        req = urllib.request.Request(f"https://sctapi.ftqq.com/{key}.send", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"  [!!] 请求失败: {e}")
        print("       检查网络，或确认 SendKey 有没有复制全")
        return 1

    print(f"  Server酱 返回: {json.dumps(resp, ensure_ascii=False)}")
    print()
    if resp.get("code") == 0:
        print("  [OK] 推送已发出 —— 请查看手机微信 ✓")
        print("=" * 62)
        return 0
    print("  [!!] 推送被拒绝，看上面的 message 字段")
    if "exceed" in str(resp).lower() or "limit" in str(resp).lower():
        print("       像是免费额度用完了")
    print("=" * 62)
    return 2


if __name__ == "__main__":
    sys.exit(main())

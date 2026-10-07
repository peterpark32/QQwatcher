# -*- coding: utf-8 -*-
"""判定逻辑回归测试。

不依赖网络、不依赖监听服务、不弹窗——直接喂事件给 filter.judge()，
验证"该命中的命中、不该命中的不误报"。

这些用例是照着真实群聊天记录建的：
管理员（2108873477）习惯把几个活动一次性连发，每条消息是【纯图片、无文字】，
图来自同一套微信小程序报名系统。

用法: python tools/test_judge.py
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.config import CFG  # noqa: E402
from app.filter import judge  # noqa: E402

GROUP = 1034761242
ADMIN = 2108873477
OWNER = 2483902860
MEMBER = 123456789

# 模拟 QQ 图床域名（真实环境里换成实际观察到的域名）
HOST = "https://multimedia.nt.qq.com.cn/download"

pass_n = 0
fail_n = 0


def ev(sender, segments, group=GROUP):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group,
        "user_id": sender,
        "message": segments,
    }


def img(i=1):
    return {"type": "image",
            "data": {"url": f"{HOST}?fileid=abc{i}&rkey=xyz", "file": f"a{i}.jpg"}}


def txt(s):
    return {"type": "text", "data": {"text": s}}


def single_image_expected():
    """单张纯图是否该命中，取决于当前配置。

    没有任何硬编码的期望值——测的是"逻辑是否符合配置意图"：
      · 配了域名白名单 -> 白名单内的单图必须命中
      · 多图阈值 <= 1   -> 单图必须命中
      · 否则            -> 单图不命中（靠关键词兜底）
    """
    if CFG.activity_hosts:
        return True
    return CFG.multi_image_threshold <= 1


def cases():
    one = single_image_expected()
    return [
        # (说明, 事件, 期望是否命中, 备注)
        ("★管理员发单张活动二维码图（纯图无文字）—— 真实场景",
         ev(ADMIN, [img(1)]), one, "真实活动消息就是这个形态"),
        ("★管理员一条消息连发 3 张活动图（截图里的模式）",
         ev(ADMIN, [img(1), img(2), img(3)]), True, "多图必命中"),
        ("★管理员发单张图 + 通知文字",
         ev(ADMIN, [txt("【通知】各位志愿者们晚上好，现招募郑州科技馆志愿者数名，有意者快快报名吧"), img(1)]),
         True, "关键词或图片任一命中即可"),
        ("群主发单张二维码图",
         ev(OWNER, [img(1)]), one, ""),
        ("普通群成员发图（不该理会）",
         ev(MEMBER, [img(1), img(2)]), False, "发送者过滤"),
        ("管理员发纯文字闲聊（无图，不该命中）",
         ev(ADMIN, [txt("大家早上好，今天天气不错")]), False, "必须含图"),
        ("管理员在别的群发图（不该命中）",
         ev(ADMIN, [img(1)], group=999999999), False, "群号过滤"),
        ("管理员发单张图 + 无关文字（可能误报）",
         ev(ADMIN, [txt("这个截图你们看看"), img(1)]), one,
         "配置的取舍点：宁可多弹不可漏"),
        ("★管理员发文字但无图（不该命中）",
         ev(ADMIN, [txt("【通知】招募志愿者，请在群文件查看报名表")]), False,
         "没有二维码图就没法报名，不该打扰"),
    ]


def run():
    global pass_n, fail_n
    print("=" * 70)
    print("  判定逻辑回归测试")
    print("=" * 70)
    print(f"  活动图域名白名单: {CFG.activity_hosts or '(空，用多图阈值兜底)'}")
    print(f"  多图触发阈值    : {CFG.multi_image_threshold}")
    print(f"  关键词          : {CFG.keywords}")
    print(f"  单张纯图期望结果: {single_image_expected()}  (由上面配置推导)")
    print("=" * 70)

    for desc, event, want, note_text in cases():
        hit, info = judge(event)
        n_img = len(info["images"])
        reason = " | ".join(info["reasons"])
        if hit == want:
            mark = "OK  "
            pass_n += 1
        else:
            mark = "FAIL"
            fail_n += 1
        print(f"\n[{mark}] {desc}")
        if note_text:
            print(f"       备注: {note_text}")
        print(f"       图{n_img}张 -> 判定={hit} (期望 {want})")
        print(f"       {reason}")

    print("\n" + "=" * 70)
    if fail_n == 0:
        print(f"  全部通过 {pass_n}/{pass_n} ✓")
    else:
        print(f"  通过 {pass_n} / 失败 {fail_n}")
        print("  失败的用例说明判定逻辑和配置意图不一致，需要修代码或改配置")
    print("=" * 70)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(run())

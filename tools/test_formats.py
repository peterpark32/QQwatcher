# -*- coding: utf-8 -*-
"""事件格式容错测试。

为什么必须做这个：
OneBot 协议允许上游用完全不同的格式表达同一条消息，而 NapCat 的
messagePostFormat 设置、QQ 版本、图片落地方式都会改变实际字段。
如果只按一种格式写解析代码，另一种格式下就会出现最危险的失效——
判定层认为"消息没有图片"，于是静默丢弃活动消息，
日志上一切正常，但你永远收不到提醒，直到错过名额。

本测试覆盖：
  1. message 是数组 vs 是 CQ 码字符串 vs 缺失（只有 raw_message）
  2. 图片地址是 http URL / file:/// / 裸路径 / base64 内嵌
  3. 字段名是 type/msg_type、url/file/path、filename/name
  4. 纯图片无文字（真实活动消息形态）
  5. 各种噪音：@某人、表情、语音、回复、多图连发

用法: python tools\\test_formats.py
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
from app.filter import judge, plain_text, image_segments, parse_cq  # noqa: E402

GROUP = 1034761242
ADMIN = 2108873477

HOST_URL = "https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=abc"
pass_n = 0
fail_n = 0


def check(desc, cond, detail=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print(f"  [OK]   {desc}")
    else:
        fail_n += 1
        print(f"  [FAIL] {desc}")
        if detail:
            print(f"         {detail}")


def base(sender=ADMIN, group=GROUP, **kw):
    e = {
        "post_type": "message",
        "message_type": "group",
        "group_id": group,
        "user_id": sender,
        "self_id": 2014713076,
    }
    e.update(kw)
    return e


def hit(e):
    return judge(e)[0]


def n_img(e):
    return len(image_segments(e))


print("=" * 72)
print("  事件格式容错测试")
print("=" * 72)
print(f"  多图触发阈值: {CFG.multi_image_threshold}（1 = 单图也命中）")
print("=" * 72)

# ---------------------------------------------------------------- 1. CQ 码字符串
print("\n【1】message 是 CQ 码字符串（messagePostFormat=string）")

e = base(message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL,
         raw_message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("单张 CQ 图片 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message="[CQ:image,file=a.jpg,url=%s][CQ:image,file=b.jpg,url=%s]"
                 % (HOST_URL, HOST_URL))
check("两张 CQ 图片 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message="【通知】招募志愿者[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("文字+CQ图片 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message="大家早上好")
check("纯文字 CQ 消息 -> 不命中", not hit(e))

check("parse_cq 能取出 url 字段",
      parse_cq("[CQ:image,file=a.jpg,url=http://x/a.jpg]")[0]["data"]["url"]
      == "http://x/a.jpg")

check("parse_cq 处理 CQ 转义 &#44;",
      parse_cq("[CQ:image,file=a&#44;b.jpg]")[0]["data"]["file"] == "a,b.jpg")

# ---------------------------------------------------------------- 2. 只有 raw_message
print("\n【2】message 缺失，只有 raw_message（部分实现会这样）")

e = base(raw_message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("从 raw_message 解析出图片 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[], raw_message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("message 为空数组时回退 raw_message -> 命中", hit(e), f"图片数={n_img(e)}")

# ---------------------------------------------------------------- 3. 图片地址形态
print("\n【3】图片地址的不同形态（决定二维码能不能显示）")

e = base(message=[{"type": "image", "data": {"file": "a.jpg", "url": HOST_URL}}])
check("数组格式 + http url -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[{"type": "image",
                   "data": {"file": "file:///C:/Users/x/AppData/a.jpg"}}])
check("file:/// 本地路径 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[{"type": "image",
                   "data": {"file": r"C:\Users\x\AppData\a.jpg"}}])
check("裸绝对路径 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[{"type": "image",
                   "data": {"file": "base64://iVBORw0KGgoAAAANS"}}])
check("base64 内嵌 -> 命中", hit(e), f"图片数={n_img(e)}")
imgs = image_segments(e)
check("base64 的 host 标记为 <base64内嵌>（不污染日志）",
      imgs and imgs[0]["host"] == "<base64内嵌>", f"host={imgs[0]['host'] if imgs else None}")

e = base(message=[{"type": "image", "data": {"path": "/root/qq/a.jpg"}}])
check("字段名是 path 而不是 file -> 命中", hit(e), f"图片数={n_img(e)}")

# ---------------------------------------------------------------- 4. 字段命名差异
print("\n【4】字段命名差异（不同 NapCat 版本）")

e = base(message=[{"msg_type": "image", "data": {"file": "a.jpg", "url": HOST_URL}}])
check("段类型叫 msg_type 而不是 type -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[{"type": "image",
                   "data": {"name": "a.jpg", "url": HOST_URL}}])
check("只有 name 字段但有 url -> 命中", hit(e), f"图片数={n_img(e)}")

# ---------------------------------------------------------------- 5. 噪音类型
print("\n【5】混合噪音：@、表情、语音、回复")

e = base(message=[
    {"type": "at", "data": {"qq": "123456"}},
    {"type": "text", "data": {"text": " 快看 "}},
    {"type": "face", "data": {"id": "1"}},
    {"type": "image", "data": {"file": "a.jpg", "url": HOST_URL}},
    {"type": "record", "data": {"file": "v.amr"}},
])
check("@+表情+语音混合，含 1 图 -> 命中", hit(e), f"图片数={n_img(e)}")

e = base(message=[
    {"type": "reply", "data": {"id": "999"}},
    {"type": "text", "data": {"text": "好的"}},
])
check("回复+纯文字，无图 -> 不命中", not hit(e))

e = base(message=[{"type": "record", "data": {"file": "v.amr"}}])
check("只有语音 -> 不命中", not hit(e))

e = base(message=[{"type": "mface", "data": {"url": HOST_URL}}])
check("商城表情 mface -> 也算图，命中", hit(e), f"图片数={n_img(e)}")

# ---------------------------------------------------------------- 6. 文本提取正确性
print("\n【6】文本提取（影响关键词匹配与推送摘要）")

e = base(message=[
    {"type": "text", "data": {"text": "【通知】"}},
    {"type": "image", "data": {"file": "a.jpg", "url": HOST_URL}},
    {"type": "text", "data": {"text": "请尽快报名"}},
])
t = plain_text(e)
check("数组格式文本拼接正确", "【通知】" in t and "请尽快报名" in t, repr(t))

e = base(message="[CQ:at,qq=1] 招募志愿者 [CQ:image,file=a.jpg]")
t = plain_text(e)
check("CQ 格式文本提取不含 CQ 码", "CQ:" not in t and "招募志愿者" in t, repr(t))

# ---------------------------------------------------------------- 7. 过滤层仍然有效
print("\n【7】过滤层没有被破坏")

e = base(sender=123456789, message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("普通成员 CQ 图片 -> 不命中", not hit(e))

e = base(group=999999, message="[CQ:image,file=a.jpg,url=%s]" % HOST_URL)
check("其他群 CQ 图片 -> 不命中", not hit(e))

e = base(message=[])
check("空消息 -> 不命中", not hit(e))

e = base(message="[CQ:image]")
check("CQ 图片缺 url/file -> 仍算图，命中", hit(e), f"图片数={n_img(e)}")

print("\n" + "=" * 72)
if fail_n == 0:
    print(f"  全部通过 {pass_n}/{pass_n} ✓")
    print("  结论：无论 NapCat 用哪种消息格式，活动消息都能被正确识别")
else:
    print(f"  通过 {pass_n} / 失败 {fail_n}")
    print("  失败的用例说明某种真实格式会漏报，必须修")
print("=" * 72)

sys.exit(0 if fail_n == 0 else 1)

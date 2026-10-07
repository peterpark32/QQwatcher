# -*- coding: utf-8 -*-
"""消息筛选：群号 + 发送者 + 关键词 + 图片特征。

关键点：必须同时支持 OneBot 的两种消息格式。
  · 数组格式（messagePostFormat=array）：message 是 [{"type":...,"data":{...}}]
  · CQ 码字符串格式（messagePostFormat=string）：message 是
    "文字[CQ:image,file=xx.jpg][CQ:image,file=yy.jpg]"

只支持其中一种会造成最危险的失效：格式不匹配时图片被当成文本，
判定层认为"没有图片"而静默丢弃活动消息，日志上看起来一切正常。
"""
import re

from .config import CFG

# OneBot / NapCat 的图片段类型名
IMAGE_TYPES = {"image", "flash", "mface"}

# [CQ:image,file=a.jpg,url=http://...,sub_type=0]
_CQ_RE = re.compile(r"\[CQ:([a-zA-Z_]+)((?:,[^\]]*)?)\]")


def parse_cq(text):
    """把 CQ 码字符串解析成 OneBot 数组格式的段列表。

    >>> parse_cq("hi[CQ:image,file=a.jpg,url=http://x/a.jpg]")
    [{'type': 'text', 'data': {'text': 'hi'}},
     {'type': 'image', 'data': {'file': 'a.jpg', 'url': 'http://x/a.jpg'}}]
    """
    out = []
    pos = 0
    for m in _CQ_RE.finditer(text):
        if m.start() > pos:
            seg_text = text[pos:m.start()]
            if seg_text:
                out.append({"type": "text", "data": {"text": seg_text}})
        ctype = m.group(1)
        data = {}
        for pair in (m.group(2) or "").lstrip(",").split(","):
            if not pair or "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            k = k.strip()
            v = v.strip()
            # OneBot 转义：&#44; -> ,   &#91;/&#93; -> [/]   &#38; -> &
            v = (v.replace("&#44;", ",").replace("&#91;", "[")
                  .replace("&#93;", "]").replace("&#38;", "&"))
            data[k] = v
        out.append({"type": ctype, "data": data})
        pos = m.end()
    if pos < len(text):
        tail = text[pos:]
        if tail:
            out.append({"type": "text", "data": {"text": tail}})
    return out


def msg_type(seg):
    """兼容 'type' 与 'message_type' / 'msg_type' 三种命名。"""
    return str(seg.get("type") or seg.get("message_type") or "").lower()


def normalize_segment(seg):
    """统一某些版本 NapCat 用下划线命名的字段（msg_type / sub_type 等）。"""
    if not isinstance(seg, dict):
        return {"type": "", "data": {}}
    if "type" not in seg and "msg_type" in seg:
        seg = dict(seg)
        seg["type"] = seg["msg_type"]
    return seg


def segments_of(event):
    """把事件统一成段列表，无论上游用的是数组格式还是 CQ 码字符串格式。"""
    msg = event.get("message")
    if isinstance(msg, list) and msg:
        return [normalize_segment(s) for s in msg]
    if isinstance(msg, str) and msg.strip():
        parsed = parse_cq(msg)
        if parsed:
            return parsed
    # 数组为空、或 message 缺失时，退回解析 raw_message
    raw = event.get("raw_message")
    if isinstance(raw, str) and raw.strip():
        parsed = parse_cq(raw)
        if parsed:
            return parsed
    return []


def plain_text(event):
    """把所有文本段拼起来，用于关键词匹配与推送摘要。"""
    parts = []
    for seg in segments_of(event):
        if msg_type(seg) == "text":
            data = seg.get("data") or {}
            parts.append(str(data.get("text", "")))
    text = " ".join(p for p in parts if p)
    return re.sub(r"\s+", " ", text).strip()


def image_segments(event):
    """返回 [{url, file, name, host}]。兼容 image 段的 url/file 两种字段。"""
    out = []
    for seg in segments_of(event):
        if msg_type(seg) not in IMAGE_TYPES:
            continue
        data = seg.get("data") or {}
        url = data.get("url") or data.get("file") or data.get("path") or ""
        out.append({
            "url": str(url),
            "file": str(data.get("file") or ""),
            "name": str(data.get("filename") or data.get("name") or ""),
            "host": url_host(str(url)),
        })
    return out


def url_host(url):
    """给图片地址打一个可读的"来源"标签，用于域名白名单判断与日志。

    除了真正的域名，还要能识别 NapCat 可能的几种非 HTTP 形态：
      · base64://...     图片直接内嵌在事件里（日志里绝不能把内容打出来）
      · file:///C:/...   本地文件路径
      · /home/x/a.jpg    裸绝对路径
    """
    if not url:
        return ""
    low = url.lower()
    if low.startswith("base64://"):
        return "<base64内嵌>"
    if low.startswith("file://"):
        return "<本地文件>"
    m = re.match(r"https?://([^/?#]+)", url, re.I)
    if m:
        return m.group(1).lower()
    # 剩下的当成本地路径
    return "<本地文件>" if (":" in url[:3] or url.startswith("/")) else ""


def activity_image_hits(images):
    """判断这组图片是否像"报名活动图"。返回 (是否像, 原因列表)。

    为什么需要这个函数：
    真实群里的活动消息是【纯图片、没有文字】（管理员直接发报名二维码图）。
    所以"关键词命中"这一层对真实消息完全不适用——如果只用关键词判定，
    系统会一条都命中不了。真正的信号是图片本身：
      · 管理员习惯把几个活动一次性连发 -> 同一条消息含多张图
      · 图都来自同一套报名系统 -> 域名一致且在配置的白名单里
    """
    reasons = []
    if not images:
        return False, ["无图片"]

    hosts = [i["host"] for i in images if i.get("host")]
    if CFG.activity_hosts:
        # 配置了白名单域名：任何一张图命中即可
        matched = [h for h in hosts if any(w in h for w in CFG.activity_hosts)]
        if matched:
            return True, [f"图片域名命中报名系统: {matched[0]}"]
        return False, [f"图片域名不在白名单（实际 {hosts[:3] or '未知'}）"]

    # 没配白名单时，用"多图连发"这个行为特征兜底
    if len(images) >= CFG.multi_image_threshold:
        return True, [f"连发 {len(images)} 张图，符合活动图特征"]
    return False, [f"仅 {len(images)} 张图且未配置域名白名单"]


def match_keywords(text):
    return [k for k in CFG.keywords if k and k in text]


def judge(event):
    """返回 (是否命中, 判定详情 dict)。

    判定链：群号 -> 发送者 -> 图片特征/关键词 三选一。
    每一层都记录原因，方便干跑时校准。
    """
    info = {
        "group_id": event.get("group_id"),
        "user_id": event.get("user_id"),
        "text": plain_text(event)[:500],
        "images": image_segments(event),
        "reasons": [],
    }
    try:
        gid = int(event.get("group_id") or 0)
    except (TypeError, ValueError):
        gid = 0
    try:
        uid = int(event.get("user_id") or 0)
    except (TypeError, ValueError):
        uid = 0
    info["group_id"], info["user_id"] = gid, uid

    if event.get("post_type") != "message" or event.get("message_type") != "group":
        info["reasons"].append("非群消息")
        return False, info

    if CFG.groups and gid not in CFG.groups:
        info["reasons"].append(f"群号 {gid} 不在监听列表")
        return False, info
    info["reasons"].append(f"群号 {gid} 匹配")

    if CFG.senders and uid not in CFG.senders:
        info["reasons"].append(f"发送者 {uid} 不是关键发送者")
        return False, info
    info["reasons"].append(f"发送者 {uid} 匹配")

    if info["images"]:
        info["reasons"].append(f"含 {len(info['images'])} 张图片")
        info["image_hosts"] = sorted({i["host"] for i in info["images"] if i["host"]})

    # 触发条件一：图片特征（真实活动消息走这条，因为纯图无文字）
    by_image, img_reasons = activity_image_hits(info["images"])
    info["reasons"].extend(img_reasons)
    info["by_image"] = by_image

    # 触发条件二：关键词（有些活动消息会带文字说明）
    hits = match_keywords(info["text"])
    info["keyword_hits"] = hits
    info["by_keyword"] = bool(hits)
    if hits:
        info["reasons"].append("关键词命中: " + "/".join(hits))
    else:
        info["reasons"].append("无关键词命中")

    # 触发条件三：有文字的图片消息（文字本来就是给人看的说明）
    info["by_text_with_image"] = bool(info["images"] and info["text"].strip())

    if CFG.need_image and not info["images"]:
        info["reasons"].append("必须含图但消息无图 -> 排除")
        return False, info

    # 开了"必须有文字"的模式时，纯图消息也要放行（否则会漏掉真实活动）
    if not (by_image or info["by_keyword"] or info["by_text_with_image"]):
        info["reasons"].append("三种触发条件都未满足 -> 排除")
        return False, info

    return True, info

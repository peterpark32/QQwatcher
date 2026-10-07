# -*- coding: utf-8 -*-
"""配置加载。中文键名是为了让你能直接改 config.json。"""
import json
import os

from .jsonio import load_json_loose

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULTS = {
    "监听": {
        "群号": [],
        "关键发送者": [],
        "关键词": [],
        "必须含图片": True,
        "接收端口": 18080,
        "活动图域名": [],
        "多图触发阈值": 2,
    },
    "行为": {
        "干跑模式": True,
        "全屏弹窗": True,
        "播放声音": True,
        "自动打开原图": False,
        "记录所有群消息": True,
    },
    "手机推送": {
        "启用": False,
        "ServerChanSendKey": "",
        "推送二维码原图到QQ": False,
        "目标QQ号": 0,
    },
    "路径": {
        "原图目录": "images",
        "日志目录": "logs",
    },
}


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.raw = {}
        self.reload()

    def reload(self):
        data = {}
        if os.path.exists(self.path):
            data = load_json_loose(self.path, default={})
        self.raw = _merge(DEFAULTS, data)
        self._resolve()

    def _resolve(self):
        r = self.raw
        self.groups = {int(x) for x in r["监听"]["群号"]}
        self.senders = {int(x) for x in r["监听"]["关键发送者"]}
        self.keywords = [str(x) for x in r["监听"]["关键词"]]
        self.need_image = bool(r["监听"]["必须含图片"])
        self.port = int(r["监听"]["接收端口"])
        self.activity_hosts = [str(x).lower() for x in r["监听"].get("活动图域名", []) if str(x).strip()]
        try:
            self.multi_image_threshold = max(1, int(r["监听"].get("多图触发阈值", 2)))
        except (TypeError, ValueError):
            self.multi_image_threshold = 2

        self.dry_run = bool(r["行为"]["干跑模式"])
        self.popup = bool(r["行为"]["全屏弹窗"])
        self.sound = bool(r["行为"]["播放声音"])
        self.open_raw = bool(r["行为"]["自动打开原图"])
        self.log_all = bool(r["行为"]["记录所有群消息"])

        self.push_enabled = bool(r["手机推送"]["启用"])
        self.send_key = str(r["手机推送"]["ServerChanSendKey"]).strip()
        self.push_qq_image = bool(r["手机推送"]["推送二维码原图到QQ"])
        self.target_qq = int(r["手机推送"]["目标QQ号"] or 0)

        self.image_dir = os.path.join(BASE_DIR, r["路径"]["原图目录"])
        self.log_dir = os.path.join(BASE_DIR, r["路径"]["日志目录"])
        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)


CFG = Config()

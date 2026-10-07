# -*- coding: utf-8 -*-
"""登录后的一键配置：把 OneBot 上报配置写到 NapCat 真正读取的位置。

为什么要这个脚本：
NapCat 的配置目录取决于它自己的数据目录策略。如果它在登录后没有读到
我们放在 napcat\\config\\ 里的配置，那么事件就不会上报到监听服务，
整个系统看起来"在跑"但收不到任何消息——这是最难排查的失效形态。
本脚本会把配置同时写入所有候选目录，做到无论 NapCat 用哪个都能生效。

用法: python tools/sync_napcat_config.py
"""
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "app"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from jsonio import load_json_loose  # noqa: E402

QQ = "2014713076"
LISTEN_PORT = 18080     # 我们的监听服务
ONEBOT_PORT = 18081     # NapCat 的 OneBot HTTP API

NAPCAT_DIR = os.path.join(BASE, "napcat")


def report_config():
    """按用户配置生成标准的 onebot11 配置。"""
    cfg = load_json_loose(os.path.join(BASE, "config.json"), default={})
    listen_port = int((cfg.get("监听") or {}).get("接收端口", LISTEN_PORT))
    return {
        "network": {
            "httpServers": [{
                "name": "watcher-api",
                "enable": True,
                "port": ONEBOT_PORT,
                "host": "127.0.0.1",
                "enableCors": True,
                "enableWebsocket": True,
                "messagePostFormat": "array",
                "reportSelfMessage": False,
                "token": "",
                "debug": False,
            }],
            "httpClients": [{
                "name": "watcher-report",
                "enable": True,
                "url": f"http://127.0.0.1:{listen_port}/",
                "messagePostFormat": "array",
                "reportSelfMessage": False,
                "token": "",
                "debug": False,
            }],
            "websocketServers": [],
            "websocketClients": [],
        },
        "musicSignUrl": "",
        "enableLocalFile2Url": True,
        "parseMultMsg": False,
        "imageDownloadProxy": "",
    }


def candidate_dirs():
    """NapCat 可能读取配置的所有位置。"""
    dirs = [
        os.path.join(NAPCAT_DIR, "config"),
        os.path.join(NAPCAT_DIR, "napcat", "config"),
        os.path.join(os.environ.get("APPDATA", ""), "QQ", "NapCat", "config"),
        os.path.join(os.path.expanduser("~"), ".napcat", "config"),
    ]
    # QQ 数据目录下所有 napcat_<qq> 形式的分区
    qqdata = os.path.join(os.environ.get("APPDATA", ""), "QQ")
    if os.path.isdir(qqdata):
        for name in os.listdir(qqdata):
            if name.lower().startswith("napcat"):
                dirs.append(os.path.join(qqdata, name, "config"))
            p = os.path.join(qqdata, name, "NapCat", "config")
            if os.path.isdir(p):
                dirs.append(p)
    out = []
    for d in dirs:
        if d and d not in out:
            out.append(d)
    return out


def main():
    payload = report_config()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target = f"onebot11_{QQ}.json"

    print("=" * 68)
    print("  同步 NapCat OneBot 配置")
    print("=" * 68)
    print(f"  上报目标: http://127.0.0.1:{LISTEN_PORT}/")
    print(f"  API 端口: {ONEBOT_PORT}")
    print()

    written, skipped = [], []
    for d in candidate_dirs():
        exists = os.path.isdir(d)
        # 不主动创建 APPDATA 下的目录，只写已经存在的（避免污染）
        if not exists:
            skipped.append((d, "目录不存在"))
            continue
        path = os.path.join(d, target)
        try:
            if os.path.exists(path):
                shutil.copy2(path, path + ".bak")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            written.append(path)
            print(f"  [已写入] {path}")
        except Exception as e:
            print(f"  [失败]   {path} -> {e}")

    for d, why in skipped:
        print(f"  [跳过]   {d}  ({why})")

    print()
    if not written:
        print("  没有写入任何位置！请检查 NapCat 是否已解压。")
        return 1
    print(f"  共写入 {len(written)} 处。")
    print()
    print("  下一步：重启 NapCat（关闭 QQ 后重新运行 一键启动NapCat.vbs），")
    print("  然后确认监听服务收到事件：")
    print("    curl http://127.0.0.1:18080/health")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())

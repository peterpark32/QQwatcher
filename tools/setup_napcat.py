# -*- coding: utf-8 -*-
"""一键部署 NapCat + 自动写入 OneBot 配置。

做的事：
1. 解压 NapCat.Shell.zip 到指定目录
2. 找到/生成 onebot11_<QQ号>.json，把 HTTP 上报指向本机监听服务
3. 生成启动批处理

可重复运行，已存在的配置会先备份再改。
"""
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from jsonio import load_json_loose  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(BASE, "download", "NapCat.Shell.zip")
INSTALL_DIR = os.path.join(BASE, "napcat")
QQ = "2014713076"
LISTEN_PORT = 18080          # 我们监听服务的端口
HTTP_SERVER_PORT = 18081     # NapCat 自己的 OneBot HTTP API 端口（可选功能用）


def step(msg):
    print(f"\n>>> {msg}", flush=True)


def unzip():
    step("解压 NapCat.Shell.zip")
    if not os.path.exists(ZIP):
        raise SystemExit(f"找不到安装包: {ZIP}")
    size = os.path.getsize(ZIP)
    print(f"    包大小: {size/1024/1024:.2f} MB")
    if os.path.isdir(INSTALL_DIR):
        print(f"    目录已存在，先备份为 napcat.bak")
        bak = INSTALL_DIR + ".bak"
        if os.path.isdir(bak):
            shutil.rmtree(bak, ignore_errors=True)
        shutil.move(INSTALL_DIR, bak)
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"压缩包损坏，首个坏文件: {bad}")
        z.extractall(INSTALL_DIR)
    n = sum(len(f) for _, _, f in os.walk(INSTALL_DIR))
    print(f"    解压完成，共 {n} 个文件 -> {INSTALL_DIR}")


def find_config_dir():
    """NapCat 的配置可能在 napcat/config 或 config。"""
    for rel in ("config", os.path.join("napcat", "config")):
        p = os.path.join(INSTALL_DIR, rel)
        if os.path.isdir(p):
            return p
    p = os.path.join(INSTALL_DIR, "config")
    os.makedirs(p, exist_ok=True)
    return p


def patch_onebot():
    step("写入 OneBot 网络配置")
    cfg_dir = find_config_dir()
    print(f"    配置目录: {cfg_dir}")
    existing = [f for f in os.listdir(cfg_dir) if f.startswith("onebot11")]
    print(f"    已有配置: {existing or '无'}")

    path = os.path.join(cfg_dir, f"onebot11_{QQ}.json")
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
        cfg = load_json_loose(path, default={})
        print(f"    已备份原配置 -> {os.path.basename(path)}.bak")
    else:
        cfg = {}

    cfg.setdefault("network", {})
    net = cfg["network"]

    # 上报目标：本机监听服务
    net["httpServers"] = [{
        "name": "watcher-report",
        "enable": True,
        "port": HTTP_SERVER_PORT,
        "host": "127.0.0.1",
        "enableCors": True,
        "enableWebsocket": True,
        "messagePostFormat": "array",
        "reportSelfMessage": False,
        "token": "",
        "debug": False,
    }]
    net["httpClients"] = [{
        "name": "watcher-push",
        "enable": True,
        "url": f"http://127.0.0.1:{LISTEN_PORT}/",
        "messagePostFormat": "array",
        "reportSelfMessage": False,
        "token": "",
        "debug": False,
    }]
    net.setdefault("websocketServers", [])
    net.setdefault("websocketClients", [])

    cfg.setdefault("musicSignUrl", "")
    cfg.setdefault("enableLocalFile2Url", True)
    cfg.setdefault("parseMultMsg", False)
    cfg.setdefault("imageDownloadProxy", "")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"    已写入: {path}")
    print(f"    HTTP 上报目标 -> http://127.0.0.1:{LISTEN_PORT}/")
    print(f"    OneBot API 端口 -> {HTTP_SERVER_PORT}")


def write_launcher():
    step("生成启动批处理")
    # launcher.bat 是官方入口，优先用它
    entry = None
    for cand in ("launcher.bat", "launcher-win10.bat", "napcat.bat", "NapCatWinBootMain.exe"):
        if os.path.exists(os.path.join(INSTALL_DIR, cand)):
            entry = cand
            break
    print(f"    找到官方入口: {entry}")

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "title NapCat - QQ " + QQ + " (请勿关闭)",
        'cd /d "%~dp0"',
        "echo 启动 NapCat，首次运行会弹出二维码，请用手机 QQ 扫码登录 " + QQ,
        "echo.",
    ]
    if entry and entry.endswith(".bat"):
        lines.append(f'call "{entry}" {QQ}')
    elif entry == "NapCatWinBootMain.exe":
        lines.append(f'"{entry}" {QQ}')
    else:
        lines.append("echo [错误] 未找到可用的启动入口，请手动查看目录内容")
    lines.append("pause")

    out = os.path.join(INSTALL_DIR, "启动NapCat.bat")
    with open(out, "w", encoding="gbk", errors="replace") as f:
        f.write("\r\n".join(lines))
    print(f"    已生成: {out}")


def report():
    step("目录结构概览")
    for name in sorted(os.listdir(INSTALL_DIR))[:25]:
        p = os.path.join(INSTALL_DIR, name)
        kind = "DIR " if os.path.isdir(p) else "FILE"
        sz = "" if os.path.isdir(p) else f"{os.path.getsize(p)/1024:.0f}KB"
        print(f"    [{kind}] {name} {sz}")


if __name__ == "__main__":
    unzip()
    patch_onebot()
    write_launcher()
    report()
    step("部署完成")
    print("    下一步：运行 napcat\\启动NapCat.bat，手机 QQ 扫码登录")

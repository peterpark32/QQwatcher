# -*- coding: utf-8 -*-
"""分段并行下载器：专治国内下 GitHub Release 大文件断流。

原理：gh-proxy 类镜像单连接很慢且约 100 秒断流，但支持 HTTP Range。
于是把文件切成 N 段并行拉，各自控制在断流阈值内，最后按序合并。

用法:
    python tools/fetch_napcat.py                 # 默认分 8 段
    python tools/fetch_napcat.py --segments 12
    python tools/fetch_napcat.py --url <直链>
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DL_DIR = os.path.join(BASE, "download")
TAG = "v4.18.30"
ASSET = "NapCat.Shell.zip"
GH = f"https://github.com/NapNeko/NapCatQQ/releases/download/{TAG}/{ASSET}"
MIRROR = f"https://gh-proxy.com/{GH}"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_size_and_digest():
    """从 GitHub API 拿文件大小和官方 sha256（校验用）。"""
    url = f"https://api.github.com/repos/NapNeko/NapCatQQ/releases/tags/{TAG}"
    req = urllib.request.Request(url, headers={"User-Agent": "dsh"})
    with urllib.request.urlopen(req, timeout=40) as r:
        rel = json.loads(r.read().decode("utf-8"))
    for a in rel.get("assets", []):
        if a["name"] == ASSET:
            return a["size"], a.get("digest", "")
    raise SystemExit("API 里找不到该文件")


def curl_range(url, start, end, out, timeout=150):
    cmd = ["curl.exe", "-L", "-s", "--fail", "--retry", "3",
           "--retry-delay", "2", "--max-time", str(timeout),
           "-r", f"{start}-{end}", "-o", out, url]
    r = subprocess.run(cmd, capture_output=True)
    ok = r.returncode == 0 and os.path.exists(out)
    size = os.path.getsize(out) if ok else 0
    want = end - start + 1
    return ok and size == want, size, want


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", type=int, default=8)
    ap.add_argument("--url", default=MIRROR)
    ap.add_argument("--out", default=os.path.join(DL_DIR, ASSET))
    args = ap.parse_args()

    os.makedirs(DL_DIR, exist_ok=True)
    total, digest = get_size_and_digest()
    print(f"文件: {ASSET}")
    print(f"大小: {total/1024/1024:.2f} MB")
    print(f"官方摘要: {digest or '(未提供)'}")

    # 断点续传：如果已有同样大小的完整文件，直接校验返回
    if os.path.exists(args.out) and os.path.getsize(args.out) == total:
        print("已存在完整文件，跳过下载")
        verify(args.out, digest)
        return

    seg = args.segments
    chunk = (total + seg - 1) // seg
    parts_dir = os.path.join(DL_DIR, "parts")
    shutil.rmtree(parts_dir, ignore_errors=True)
    os.makedirs(parts_dir, exist_ok=True)

    jobs = []
    for i in range(seg):
        start = i * chunk
        end = min(start + chunk - 1, total - 1)
        if start > end:
            break
        out = os.path.join(parts_dir, f"part{i:02d}")
        jobs.append({"i": i, "start": start, "end": end, "out": out,
                     "state": "pending", "size": 0, "want": end - start + 1})

    print(f"\n分 {len(jobs)} 段并行下载（每段约 {chunk/1024/1024:.2f} MB）")
    print(f"下载源: {args.url}\n", flush=True)

    t0 = time.time()
    pending = list(jobs)
    attempt = {j["i"]: 0 for j in jobs}

    while pending:
        # 并发拉起所有待下载分段
        procs = []
        for j in pending:
            attempt[j["i"]] += 1
            p = subprocess.Popen(
                ["curl.exe", "-L", "-s", "--fail", "--retry", "2",
                 "--retry-delay", "2", "--max-time", "150",
                 "-r", f"{j['start']}-{j['end']}", "-o", j["out"], args.url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append((j, p))

        for j, p in procs:
            p.wait()

        still = []
        for j in pending:
            if not os.path.exists(j["out"]):
                still.append(j)
                continue
            size = os.path.getsize(j["out"])
            j["size"] = size
            if size == j["want"]:
                print(f"  [完成] 段{j['i']:02d}  {size/1024/1024:.2f} MB", flush=True)
            elif attempt[j["i"]] < 4:
                still.append(j)
            else:
                print(f"  [失败] 段{j['i']:02d}  {size}/{j['want']} 字节，重试次数用尽",
                      flush=True)

        if still:
            done = len(jobs) - len(still)
            print(f"  ...重试 {len(still)} 段（已完成 {done}/{len(jobs)}）", flush=True)
            time.sleep(2)
        pending = still

    print(f"\n合并分段... 用时 {time.time()-t0:.0f} 秒")
    with open(args.out, "wb") as fo:
        for j in jobs:
            with open(j["out"], "rb") as fi:
                shutil.copyfileobj(fi, fo, 1024 * 1024)
    shutil.rmtree(parts_dir, ignore_errors=True)
    got = os.path.getsize(args.out)
    print(f"合并完成: {got/1024/1024:.2f} MB / 应为 {total/1024/1024:.2f} MB")
    verify(args.out, digest)


def verify(path, digest):
    print("\n计算 SHA256...", flush=True)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    actual = h.hexdigest()
    print(f"  实际: {actual}")
    if digest:
        want = digest.replace("sha256:", "")
        print(f"  官方: {want}")
        print("  校验: " + ("通过 ✓" if actual == want else "不一致 ✗"))
    else:
        print("  （官方未提供摘要，跳过比对）")
    with open(path, "rb") as f:
        magic = f.read(4)
    print(f"  ZIP 魔数: {magic.hex()} " + ("✓" if magic == b"PK\x03\x04" else "✗ 不是有效 ZIP"))


if __name__ == "__main__":
    main()

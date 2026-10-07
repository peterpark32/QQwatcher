# -*- coding: utf-8 -*-
"""统一 JSON 读取。

必须存在的原因：Windows 记事本 / PowerShell 的 Set-Content -Encoding UTF8
会写入 UTF-8 BOM，而 Python 的 json 解析器遇到 BOM 会直接报错。
用户手改配置时极容易踩到，所以所有 JSON 读入口径统一走这里。
"""
import json
import os


def load_json_loose(path, default=None):
    if not path or not os.path.exists(path):
        return {} if default is None else default
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except json.JSONDecodeError as e:
            last_err = e
            continue
    if default is not None:
        return default
    raise last_err

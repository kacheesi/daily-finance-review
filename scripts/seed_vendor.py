"""下载 ECharts 离线包到 data/vendor/（网络不可用时报告自动降级纯表格）
用法: python scripts/seed_vendor.py
"""
import os
import sys

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(PROJECT_ROOT, "data", "vendor", "echarts.min.js")
URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"


def main():
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    if os.path.exists(TARGET) and os.path.getsize(TARGET) > 100000:
        print("已存在:", TARGET, os.path.getsize(TARGET), "bytes")
        return
    print("下载 ECharts ...")
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    with open(TARGET, "wb") as f:
        f.write(r.content)
    print("已保存:", TARGET, len(r.content), "bytes")


if __name__ == "__main__":
    main()

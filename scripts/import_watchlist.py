"""自选股票池导入：支持 Excel/CSV/JSON，合并到 config/watchlist.json
用法: python scripts/import_watchlist.py --file xxx.csv
格式: 表头含 code(6位代码) 与 name(名称)；JSON 可为 {"watchlist":[{"code":"600519","name":"贵州茅台"}]} 或列表
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(PROJECT_ROOT, "config", "watchlist.json")


def _normalize(rows) -> list:
    out = []
    for r in rows:
        if isinstance(r, dict):
            code = str(r.get("code", r.get("symbol", ""))).strip()
            name = str(r.get("name", code)).strip()
        else:
            continue
        code = code.split(".")[0].lower().replace("sh", "").replace("sz", "").replace("bj", "")
        if code.isdigit() and len(code) == 6:
            out.append({"code": code, "name": name})
    # 去重保序
    seen, dedup = set(), []
    for item in out:
        if item["code"] not in seen:
            seen.add(item["code"])
            dedup.append(item)
    return dedup


def main():
    ap = argparse.ArgumentParser(description="导入自选股池")
    ap.add_argument("--file", required=True, help="Excel/CSV/JSON 文件路径")
    ap.add_argument("--replace", action="store_true", help="替换现有池（默认合并去重）")
    args = ap.parse_args()

    fpath = args.file
    ext = os.path.splitext(fpath)[1].lower()
    if ext == ".json":
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("watchlist", data) if isinstance(data, dict) else data
    elif ext in (".csv", ".txt"):
        import csv
        with open(fpath, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    elif ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError:
            print("解析 Excel 需要 pandas: pip install pandas openpyxl")
            return
        df = pd.read_excel(fpath)
        rows = df.to_dict("records")
    else:
        print("不支持的文件类型:", ext)
        return

    new_items = _normalize(rows)
    if not new_items:
        print("未解析到有效股票（需 code/name 列）")
        return

    if args.replace:
        merged = new_items
    else:
        with open(WATCHLIST_PATH, encoding="utf-8") as f:
            existing = json.load(f).get("watchlist", [])
        merged = _normalize(existing + new_items)

    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"watchlist": merged}, f, ensure_ascii=False, indent=2)
    print(f"已更新自选股池: {len(merged)} 只 -> {WATCHLIST_PATH}")


if __name__ == "__main__":
    main()

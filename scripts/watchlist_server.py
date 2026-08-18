#!/usr/bin/env python3
"""自选股管理服务（零依赖，仅标准库）
启动: python scripts/watchlist_server.py [--port 8787]
- 打开 http://127.0.0.1:8787 即可添加/删除自选股（写 config/watchlist.json）
- 报告页右上角「＋ 管理自选股」按钮会跳转到本服务
"""
import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(PROJECT_ROOT, "config", "watchlist.json")
PORT = 8787

_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}


def load_watchlist() -> list:
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        return json.load(f).get("watchlist", [])


def save_watchlist(items: list) -> None:
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"watchlist": items}, f, ensure_ascii=False, indent=2)


def lookup_name(code: str) -> str:
    """通过腾讯行情接口获取股票名称（失败返回空串）"""
    try:
        sym = f"sh{code}" if code.startswith(("6", "9", "5")) else f"sz{code}"
        r = requests.get(f"https://qt.gtimg.cn/q={sym}", headers=_H, timeout=8)
        if r.status_code == 200 and "=" in r.text:
            fields = r.text.split('="')[1].split('"')[0].split("~")
            if len(fields) > 2 and fields[2]:
                return fields[1]
    except Exception:
        pass
    return ""


def api_add(code: str, name: str = "") -> (bool, str):
    code = code.strip()
    if not re.fullmatch(r"\d{6}", code):
        return False, "股票代码须为 6 位数字"
    items = load_watchlist()
    if any(x["code"] == code for x in items):
        return False, f"该股票已在自选池中"
    if not name.strip():
        name = lookup_name(code)
    if not name.strip():
        return False, "未能自动获取股票名称，请手动填写名称"
    items.append({"code": code, "name": name.strip()})
    save_watchlist(items)
    return True, f"已添加 {name}({code})"


def api_remove(code: str) -> (bool, str):
    items = load_watchlist()
    remain = [x for x in items if x["code"] != code.strip()]
    if len(remain) == len(items):
        return False, f"未找到 {code}"
    save_watchlist(remain)
    return True, f"已移除 {code}"


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>自选股管理</title>
<style>
:root{--bg:#101319;--card:#191d26;--border:#2a3040;--text:#e8eaf0;--sub:#9aa3b5;--red:#e64545;--green:#1a9e5a;--blue:#5a8cff;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:"Microsoft YaHei","PingFang SC",sans-serif;padding:30px 20px}
.wrap{max-width:720px;margin:0 auto}
h1{font-size:20px;margin-bottom:6px}
.sub{color:var(--sub);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.card h2{font-size:15px;margin-bottom:14px;color:var(--blue)}
form{display:flex;gap:10px;flex-wrap:wrap}
input[type=text]{flex:1;min-width:200px;background:#202531;border:1px solid var(--border);color:var(--text);padding:9px 12px;border-radius:8px;font-size:14px}
input[type=text]:focus{outline:none;border-color:var(--blue)}
button{background:var(--blue);color:#fff;border:none;padding:9px 18px;border-radius:8px;font-size:14px;cursor:pointer}
button:hover{opacity:.85}
button.ghost{background:transparent;border:1px solid var(--border);color:var(--sub)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{color:var(--sub);text-align:left;padding:8px;border-bottom:1px solid var(--border);font-weight:600}
td{padding:8px;border-bottom:1px solid rgba(42,48,64,.5)}
.del{color:var(--red);cursor:pointer;background:none;border:none;font-size:13px;text-decoration:underline}
#msg{color:var(--green);font-size:13px;margin-top:10px;min-height:18px}
#msg.err{color:var(--red)}
.hint{color:var(--sub);font-size:12px;margin-top:8px}
</style></head><body><div class="wrap">
<h1>📌 自选股管理</h1>
<div class="sub">添加/删除后，下次运行每日复盘即生效（保存至 config/watchlist.json）</div>
<div class="card">
<h2>＋ 添加自选股</h2>
<form id="addForm">
<input type="text" id="code" placeholder="股票代码，如 600519（可不带前缀）" required>
<input type="text" id="name" placeholder="股票名称（留空自动获取）">
<button type="submit">添加</button>
</form>
<div id="msg"></div>
</div>
<div class="card">
<h2>当前自选池（{{count}} 只）</h2>
<table><thead><tr><th>代码</th><th>名称</th><th style="text-align:right">操作</th></tr></thead>
<tbody id="list"></tbody></table>
<div class="hint">提示：可添加 A 股 6 位代码（沪/深/京）。删除后立即生效。</div>
</div>
<script>
const $=id=>document.getElementById(id);
async function load(){const r=await fetch('/api/watchlist');const d=await r.json();
$('list').innerHTML=d.items.map(x=>`<tr><td>${x.code}</td><td>${x.name}</td><td style="text-align:right"><button class="del" onclick="del('${x.code}')">删除</button></td></tr>`).join('');}
async function del(code){const r=await fetch('/api/watchlist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
const d=await r.json();show(d.ok,d.msg);if(d.ok)load();}
function show(ok,msg){$('msg').textContent=msg;$('msg').className=ok?'':'err';}
$('addForm').onsubmit=async e=>{e.preventDefault();
const r=await fetch('/api/watchlist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('code').value,name:$('name').value})});
const d=await r.json();show(d.ok,d.msg);if(d.ok){$('code').value='';$('name').value='';load();}};
load();
</script></div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._html(PAGE.replace("{{count}}", str(len(load_watchlist()))))
        elif self.path == "/api/watchlist":
            self._json({"ok": True, "items": load_watchlist()})
        else:
            self._json({"ok": False, "msg": "404"}, 404)

    def do_POST(self):
        try:
            body = self._body()
            if self.path == "/api/watchlist/add":
                ok, msg = api_add(body.get("code", ""), body.get("name", ""))
                self._json({"ok": ok, "msg": msg}, 200 if ok else 400)
            elif self.path == "/api/watchlist/remove":
                ok, msg = api_remove(body.get("code", ""))
                self._json({"ok": ok, "msg": msg}, 200 if ok else 400)
            else:
                self._json({"ok": False, "msg": "404"}, 404)
        except Exception as e:
            self._json({"ok": False, "msg": f"服务器错误: {e}"}, 500)

    def log_message(self, fmt, *args):
        sys.stderr.write("[watchlist] " + fmt % args + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    print(f"自选股管理服务已启动: http://127.0.0.1:{args.port}")
    print("当前自选股:", [x['name'] for x in load_watchlist()])
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()

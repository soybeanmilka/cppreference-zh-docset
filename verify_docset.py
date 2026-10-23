# -*- coding: utf-8 -*-
"""verify_docset.py <docset 目录> —— 校验产出是否真的能用。

三件事：
  1. docSet.dsidx 存在、能查出条目（Zeal 靠它搜索）
  2. 站内 html 跳转能不能落到文件
  3. css / 图片 / 字体这些资源引用能不能落地
"""
import io
import os
import re
import sqlite3
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

docset = sys.argv[1] if len(sys.argv) > 1 else "."
docs = os.path.join(docset, "Contents", "Resources", "Documents")
db = os.path.join(docset, "Contents", "Resources", "docSet.dsidx")

if not os.path.isfile(db):
    print(f"FAIL 没有 {db} —— Zeal 会搜不到任何东西")
    sys.exit(1)

con = sqlite3.connect(db)
total = con.execute("select count(*) from searchIndex").fetchone()[0]
by_type = con.execute("select type, count(*) from searchIndex group by type").fetchall()
con.close()
print(f"索引条目 {total} 条 {by_type}")

pages = [
    os.path.join(d, f)
    for d, _, fs in os.walk(docs)
    for f in fs
    if f.endswith(".html")
]
print(f"页面 {len(pages)} 个")

EXT = (".css", ".js", ".png", ".svg", ".gif", ".ico", ".jpg", ".jpeg",
       ".webp", ".ttf", ".woff", ".woff2", ".eot")

html_total = html_bad = res_total = res_bad = 0
html_samples, res_samples = [], []
for p in pages:
    with open(p, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for attr, url in re.findall(r'(href|src)="([^"]+)"', text):
        if url.startswith(("http://", "https://", "//", "#", "mailto:", "javascript:", "data:")):
            continue
        clean = url.split("#")[0].split("?")[0]
        target = os.path.normpath(os.path.join(os.path.dirname(p), clean))
        if clean.endswith(".html"):
            html_total += 1
            if not os.path.exists(target):
                html_bad += 1
                if len(html_samples) < 5:
                    html_samples.append(os.path.relpath(p, docs) + " -> " + url)
        elif clean.lower().endswith(EXT):
            res_total += 1
            if not os.path.exists(target):
                res_bad += 1
                if len(res_samples) < 5:
                    res_samples.append(os.path.relpath(p, docs) + " -> " + url)
        # 其余（/w/xxx、index.php 这类站内路由）不是静态资源，跳过

print(
    f"站内 html 跳转 {html_total} 条，落不到 {html_bad} 条 "
    f"({html_bad / max(1, html_total) * 100:.2f}%)"
)
for s in html_samples:
    print("   ", s)
print(
    f"资源引用 {res_total} 条，落不到 {res_bad} 条 "
    f"({res_bad / max(1, res_total) * 100:.2f}%)"
)
for s in res_samples:
    print("   ", s)

sys.exit(0 if html_bad == 0 else 1)

#!/usr/bin/env python3
"""
本地预览：重建成分卡片 → 用 GitHub 自己的 markdown 接口渲染 README → 生成 preview.html 并打开。

用法：
    python scripts/preview.py            重建 + 预览 + 打开浏览器
    python scripts/preview.py --no-open  只生成，不打开

依赖：gh CLI 已登录（脚本要用它拿 token 调 GitHub 的渲染接口）。
preview.html 在 .gitignore 里，不会被提交。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import urllib.request
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

CSS = """
:root{--bg:#fff;--fg:#1f2328;--mu:#59636e;--bd:#d1d9e0;--sub:#f6f8fa}
html[data-theme=dark]{--bg:#0d1117;--fg:#e6edf3;--mu:#9198a1;--bd:#3d444d;--sub:#151b23}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans','PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.5;transition:background .2s,color .2s}
.bar{position:sticky;top:0;z-index:9;display:flex;gap:14px;align-items:center;padding:10px 20px;background:var(--sub);border-bottom:1px solid var(--bd);font-size:13px;color:var(--mu)}
.bar b{color:var(--fg);font-weight:500}.bar .sp{flex:1}
.bar button{font:inherit;cursor:pointer;padding:5px 12px;border-radius:6px;border:1px solid var(--bd);background:var(--bg);color:var(--fg)}
.md{max-width:1012px;margin:0 auto;padding:36px 32px 60px;word-wrap:break-word}
.md img{max-width:100%}
.md p{margin:0 0 16px}
.md ul{padding-left:2em;margin:0 0 16px}
.md ul li{margin:.25em 0}
.md ul li>p{margin:16px 0 0}
.md strong{font-weight:600}
.md em{font-style:italic}
.md code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:85%;background:var(--sub);padding:.2em .4em;border-radius:6px}
.md hr{border:0;border-top:1px solid var(--bd);margin:24px 0}
.md h1,.md h2{font-weight:600;padding-bottom:.3em;border-bottom:1px solid var(--bd);margin:24px 0 16px}
.md h3{font-weight:600;font-size:1.25em;margin:24px 0 16px}
"""

JS = """
const r=document.documentElement,b=document.getElementById('t');
document.querySelectorAll('themed-picture, picture').forEach(function(tp){
  const s=tp.querySelector('source'), i=tp.querySelector('img');
  if(!s||!i) return;
  i.dataset.l=i.getAttribute('src');
  i.dataset.d=s.getAttribute('srcset');
});
b.addEventListener('click',()=>{
  const d=r.getAttribute('data-theme')==='dark';
  r.setAttribute('data-theme',d?'light':'dark');
  document.querySelectorAll('img[data-l]').forEach(i=>{i.src=d?i.dataset.l:i.dataset.d});
  b.textContent=d?'切换到深色':'切换到浅色';
});
"""


def github_markdown(text: str) -> str:
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    body = json.dumps({"text": text, "mode": "gfm"}).encode()
    req = urllib.request.Request(
        "https://api.github.com/markdown", data=body,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "readme-preview"})
    return urllib.request.urlopen(req, timeout=30).read().decode()


def main() -> None:
    # 1. 重建成分卡片（改过 content/ingredients.json 才会真正有变化）
    try:
        import build_ingredients
        build_ingredients.main()
    except Exception as exc:
        print(f"  跳过卡片重建：{exc}")

    # 2. 用 GitHub 的接口渲染 README
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    body = github_markdown(readme)

    # 3. 套上近似 GitHub 的样式
    html = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>README 预览</title>
<style>{CSS}</style></head><body>
<div class="bar"><b>真实渲染</b><span>由 GitHub 的 markdown 接口生成</span><span class="sp"></span><button id="t">切换到深色</button></div>
<div class="md markdown-body">{body}</div>
<script>{JS}</script></body></html>"""

    out = ROOT / "preview.html"
    out.write_text(html, encoding="utf-8")
    print(f"  → {out.name}")

    if "--no-open" not in sys.argv:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()

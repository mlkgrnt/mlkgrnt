#!/usr/bin/env python3
"""
把 content/ingredients.json 渲染成一张"配料表"风格的 SVG 卡片。

内容和表现是分开的：
  改文字 → 只改 content/ingredients.json
  改样式 → 只改这个脚本里的布局常量

用法：python scripts/build_ingredients.py
输出：assets/ingredients-light.svg / assets/ingredients-dark.svg
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "ingredients.json"
ASSETS = ROOT / "assets"

# 八套果冻配色，依次分配给每一条
PALETTE = ["#8ef0d8", "#ffb3d1", "#9db8ff", "#ffe08a",
           "#c4a4ff", "#ffb894", "#8ff0c8", "#7fd4ff"]

W = 860
PAD = 40
ROW = 44
TOP = 104
BOTTOM = 32
RADIUS = 20

THEMES = {
    "light": {
        "bg": ("#f7fdfb", "#f1f8ff"),
        "border": "#dcece9",
        "title": "#22405e",
        "name": "#22405e",
        "note": "#5f7d78",
        "accent": "#3fcbb0",
        "dot_op": 0.95,
    },
    "dark": {
        "bg": ("#0f1a1d", "#101420"),
        "border": "#223035",
        "title": "#f0f6fc",
        "name": "#e6edf3",
        "note": "#8b9a97",
        "accent": "#3fd9ac",
        "dot_op": 0.9,
    },
}

SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', "
        "'PingFang SC', 'Microsoft YaHei', sans-serif")
EMOJI_FONT = ("'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif")


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def text_width(s: str, size: float) -> float:
    """粗估文字宽度：中日韩字符按 1em，其余按 0.55em。只用来对齐，不需要精确。"""
    total = 0.0
    for ch in s:
        total += size * (1.0 if ord(ch) > 0x2E80 else 0.55)
    return total


def build(theme: str) -> str:
    cfg = THEMES[theme]
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    items = data["items"]
    title = data.get("title", "")

    # 说明列起点跟着最长的类别名走，避免长短不一时撞在一起
    name_x = 100
    widest = max(text_width(it["name"], 14) for it in items)
    note_x = round(name_x + widest + 26)

    height = TOP + ROW * len(items) + BOTTOM
    p: list[str] = []

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
             f'width="100%" role="img" aria-label="{esc(title)}">')
    p.append(f'<title>{esc(title)}</title>')
    # desc 里也要转义：内容里出现 & 会把 XML 直接弄坏
    p.append("<desc>" + esc("；".join(f"{it['name']}：{it['note']}" for it in items)) + "</desc>")

    # 背景
    p.append(f'<defs><linearGradient id="card" x1="0" y1="0" x2="1" y2="1">'
             f'<stop offset="0" stop-color="{cfg["bg"][0]}"/>'
             f'<stop offset="1" stop-color="{cfg["bg"][1]}"/></linearGradient></defs>')
    p.append(f'<rect width="{W}" height="{height}" rx="{RADIUS}" fill="url(#card)"/>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="{RADIUS}" '
             f'fill="none" stroke="{cfg["border"]}" stroke-width="1"/>')

    # 标题区
    p.append(f'<rect x="{PAD}" y="38" width="3" height="26" rx="1.5" fill="{cfg["accent"]}"/>')
    p.append(f'<text x="{PAD + 16}" y="57" font-family="{SANS}" font-size="18" font-weight="600" '
             f'fill="{cfg["title"]}" dominant-baseline="central">{esc(title)}</text>')
    p.append(f'<line x1="{PAD}" y1="82" x2="{W - PAD}" y2="82" '
             f'stroke="{cfg["border"]}" stroke-width="1"/>')

    # 条目
    for i, it in enumerate(items):
        cy = TOP + i * ROW + ROW // 2
        color = PALETTE[i % len(PALETTE)]
        begin = f"-{i * 0.42:.2f}s"

        # 呼吸的色点：SMIL 改 r 和 opacity，比 CSS transform 在各种环境下都稳
        p.append(f'<circle cx="{PAD + 8}" cy="{cy}" r="4.5" fill="{color}" opacity="{cfg["dot_op"]}">'
                 f'<animate attributeName="r" values="4;6.2;4" dur="3.2s" begin="{begin}" '
                 f'repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="0.6;1;0.6" dur="3.2s" begin="{begin}" '
                 f'repeatCount="indefinite"/></circle>')

        p.append(f'<text x="{PAD + 30}" y="{cy}" font-family="{EMOJI_FONT}" font-size="15" '
                 f'dominant-baseline="central">{it["icon"]}</text>')

        p.append(f'<text x="{name_x}" y="{cy}" font-family="{SANS}" font-size="14" font-weight="600" '
                 f'fill="{cfg["name"]}" dominant-baseline="central">{esc(it["name"])}</text>')

        p.append(f'<text x="{note_x}" y="{cy}" font-family="{SANS}" font-size="13" '
                 f'fill="{cfg["note"]}" dominant-baseline="central">{esc(it["note"])}</text>')

    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    for theme in ("light", "dark"):
        out = ASSETS / f"ingredients-{theme}.svg"
        out.write_text(build(theme), encoding="utf-8")
        print(f"  → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

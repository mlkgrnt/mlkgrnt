#!/usr/bin/env python3
"""
统计 GitHub 账号下所有仓库的语言字节数，生成深浅两版 SVG 条形图。

数据来源：GitHub REST API
  GET /users/{owner}/repos          列出仓库（默认只公开）
  GET /repos/{owner}/{repo}/languages   每个仓库的语言字节数

用法：
  python scripts/lang_stats.py                # 真实数据，写入 assets/
  python scripts/lang_stats.py --demo         # 示例数据，写入 assets/sample/

环境变量：
  GH_OWNER        账号名，默认 mlkgrnt
  GH_TOKEN        可选。想统计私有仓库就传个人 PAT（scope: repo）
  EXCLUDE_REPOS   逗号分隔，例如 "dotfiles,scratch"
  EXCLUDE_LANGS   逗号分隔，例如 "Jupyter Notebook,HTML,CSS"
  INCLUDE_FORKS   设为 1 则把 fork 也算进去（一般不要）
  TOP_N           显示前几名，默认 7
"""

from __future__ import annotations

import colorsys
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
OWNER = os.environ.get("GH_OWNER") or "mlkgrnt"
TOKEN = os.environ.get("GH_TOKEN") or ""
EXCLUDE_REPOS = {s.strip() for s in (os.environ.get("EXCLUDE_REPOS") or "").split(",") if s.strip()}
EXCLUDE_LANGS = {s.strip() for s in (os.environ.get("EXCLUDE_LANGS") or "").split(",") if s.strip()}
INCLUDE_FORKS = os.environ.get("INCLUDE_FORKS") == "1"
TOP_N = int(os.environ.get("TOP_N") or 7)


def api(path: str):
    url = path if path.startswith("http") else API + path
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "lang-stats/1.0",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_repos() -> list[dict]:
    repos, page = [], 1
    while True:
        try:
            batch = api(f"/users/{OWNER}/repos?per_page=100&page={page}&type=owner&sort=pushed")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise SystemExit(f"找不到账号 {OWNER}")
            if e.code in (403, 429):
                raise SystemExit("触发 API 限流。给 GH_TOKEN 传一个 PAT 可以提升到 5000 次/小时。")
            raise
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def collect() -> tuple[dict[str, int], list[str]]:
    totals: dict[str, int] = {}
    counted: list[str] = []
    for repo in list_repos():
        if repo.get("fork") and not INCLUDE_FORKS:
            continue
        if repo["name"] in EXCLUDE_REPOS:
            continue
        try:
            langs: dict[str, int] = api(repo["languages_url"])
        except Exception as exc:  # 单个仓库失败不该拖垮整次统计
            print(f"  ! 跳过 {repo['name']}: {exc}", file=sys.stderr)
            continue
        if not langs:
            continue
        counted.append(repo["name"])
        for lang, size in langs.items():
            if lang in EXCLUDE_LANGS:
                continue
            totals[lang] = totals.get(lang, 0) + size
    return totals, counted


# GitHub linguist 的官方语言色，缺的走灰色兜底
COLORS = {
    "Python": "#3572A5", "Kotlin": "#A97BFF", "Java": "#b07219", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "HTML": "#e34c26", "CSS": "#563d7c", "SCSS": "#c6538c",
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Rust": "#dea584", "Go": "#00ADD8",
    "Shell": "#89e051", "Dockerfile": "#384d54", "Jupyter Notebook": "#DA5B0B",
    "Dart": "#00B4AB", "Swift": "#F05138", "Ruby": "#701516", "PHP": "#4F5D95",
    "Vue": "#41b883", "Svelte": "#ff3e00", "GLSL": "#5686a5", "ShaderLab": "#222c37",
    "Assembly": "#6E4C13", "MATLAB": "#e16737", "Lua": "#000080", "Perl": "#0298c3",
    # GitHub 的 linguist 没给 OCaml 配色（所以官方页面上它显示为灰），这里自定义一个
    "OCaml": "#e8823a",
}
FALLBACK = "#8b9a97"
OTHER = "#b9c2c0"


def readable(hex_color: str, theme: str) -> str:
    """浅色底上把过亮的语言色压暗并提饱和，否则黄绿条几乎看不见。"""
    if theme != "light":
        return hex_color
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if light <= 0.58:
        return hex_color
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, min(1.0, sat * 1.25))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def build_rows(totals: dict[str, int], theme: str) -> list[tuple[str, float, str]]:
    if not totals:
        return []
    total = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    rows = [(lang, size / total * 100, readable(COLORS.get(lang, FALLBACK), theme))
            for lang, size in ranked[:TOP_N]]
    rest = total - sum(size for _, size in ranked[:TOP_N])
    if rest > 0 and len(ranked) > TOP_N:
        rows.append(("Other", rest / total * 100, OTHER))
    return rows


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(rows: list[tuple[str, float, str]], repo_count: int, theme: str, out: Path) -> None:
    light = theme == "light"
    ink = "#22405e" if light else "#f0f6fc"
    dim = "#6b8f88" if light else "#8b949e"
    track = "#edf2f0" if light else "#21262d"
    font = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', "
            "'PingFang SC', 'Microsoft YaHei', sans-serif")

    W, ROW, PAD = 860, 34, 4
    H = PAD + ROW * len(rows) + 28
    bar_x, bar_w = 200, 540

    p: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
        f'role="img" aria-label="Language breakdown">',
        f'<title>Language breakdown</title>',
        f'<g font-family="{font}">',
    ]

    for i, (lang, pct, color) in enumerate(rows):
        y = PAD + i * ROW
        cy = y + ROW / 2
        width = max(8.0, bar_w * pct / 100)
        label = "<1%" if pct < 1 else f"{pct:.0f}%"
        p.append(f'<rect x="{bar_x}" y="{y + 11:.0f}" width="{bar_w}" height="12" rx="6" fill="{track}"/>')
        p.append(f'<rect x="{bar_x}" y="{y + 11:.0f}" width="{width:.1f}" height="12" rx="6" fill="{color}"/>')
        p.append(f'<text x="30" y="{cy:.0f}" font-size="13" fill="{ink}" '
                 f'dominant-baseline="central">{esc(lang)}</text>')
        p.append(f'<text x="830" y="{cy:.0f}" font-size="13" fill="{dim}" text-anchor="end" '
                 f'dominant-baseline="central">{label}</text>')

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p.append(f'<text x="30" y="{H - 8}" font-size="11" fill="{dim}">'
             f'{repo_count} repos · excluding forks · updated {stamp}</text>')
    p.append("</g></svg>")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(p), encoding="utf-8")
    print(f"  → {out}")


DEMO = {"Python": 268_400, "Kotlin": 92_100, "TypeScript": 41_800, "HTML": 22_300,
        "C": 14_600, "Shell": 9_200, "CSS": 7_400, "JavaScript": 5_100, "Dockerfile": 900}


def main() -> None:
    demo = "--demo" in sys.argv
    out_dir = Path("assets/sample") if demo else Path("assets")

    if demo:
        print("使用示例数据（不是真实统计结果）")
        totals, counted = dict(DEMO), ["demo-a", "demo-b", "demo-c"]
    else:
        print(f"统计 {OWNER} 的仓库…")
        totals, counted = collect()
        if not totals:
            raise SystemExit("没有拿到任何语言数据，检查账号名 / token / 网络。")

    print(f"  计入 {len(counted)} 个仓库，{len(totals)} 种语言")
    for lang, size in sorted(totals.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {lang:<18}{size:>10,}")

    for theme in ("light", "dark"):
        render(build_rows(totals, theme), len(counted), theme, out_dir / f"langs-{theme}.svg")


if __name__ == "__main__":
    main()

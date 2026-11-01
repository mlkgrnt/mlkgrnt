#!/usr/bin/env python3
"""
把 GitHub 的贡献日历渲染成一条蛇扫过的动画 SVG。

和常见的 snake 贡献图的区别：格子用果冻方的圆角比例，配色取自 jelly-cube-ocean，
蛇不是一格格跳，而是一条平滑路径滑过去，被扫过的格子当场放大回弹。

用法：
    python scripts/build_snake.py
输出：
    assets/snake-light.svg / snake-dark.svg

依赖：gh CLI 已登录（贡献日历只能走 GraphQL，REST 没有这个接口）。
"""

from __future__ import annotations

import json
import os
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

OWNER = os.environ.get("GH_OWNER") or "mlkgrnt"

# 必须用 user(login:) 而不是 viewer：CI 里的 token 属于 bot，viewer 会查成 bot 自己
QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

CELL = 12
GAP = 3
STEP = CELL + GAP
LEFT = 34
TOP = 52
DUR = 13.0          # 一轮动画秒数
SNAKE_LEN = 62      # 蛇身长度，按 pathLength=1000 归一化

# 0 次 → 4 档递增
LEVELS = {
    "light": ["#edf6f3", "#c9f2e6", "#93e5d0", "#57d2b6", "#26a892"],
    "dark": ["#161e21", "#1f3d37", "#2f6f63", "#4fb39c", "#7fe8cf"],
}
SNAKE = {"light": "#1f9b85", "dark": "#7fe8cf"}
LABEL = {"light": "#6b8f88", "dark": "#8b949e"}
SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', "
        "'PingFang SC', 'Microsoft YaHei', sans-serif")


def fetch() -> dict:
    out = subprocess.check_output(
        ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"login={OWNER}"],
        text=True, encoding="utf-8")
    cal = json.loads(out)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal


def level_of(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


def build(theme: str, cal: dict) -> str:
    weeks = cal["weeks"]
    cols = len(weeks)
    rows = 7
    width = cols * STEP - GAP
    height = TOP + rows * STEP - GAP + 34

    # 蛇形路径：偶数列从下往上，奇数列从上往下
    points: list[tuple[float, float]] = []
    for c in range(cols):
        order = range(rows - 1, -1, -1) if c % 2 == 0 else range(rows)
        for r in order:
            points.append((LEFT + c * STEP + CELL / 2, TOP + r * STEP + CELL / 2))

    # 段数：每列 7 个点之间的 6 段，加上列间横移 1 段
    seg_per_col = 6 + 1
    total_segments = (cols - 1) * seg_per_col + (rows - 1)

    d = "M {:.1f} {:.1f}".format(*points[0]) + "".join(
        " L {:.1f} {:.1f}".format(x, y) for x, y in points[1:])

    p: list[str] = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 {height:.0f}" '
             f'width="100%" role="img" aria-label="Contribution snake">')
    p.append("<title>Contribution snake</title>")
    p.append(f"<desc>过去一年的贡献日历，共 {cal['totalContributions']} 次贡献，蛇扫过时格子会亮起。</desc>")

    p.append("""<style>
      .cell { transform-box: fill-box; transform-origin: center;
              animation: hit """ + f"{DUR:g}s" + """ cubic-bezier(.3,0,.2,1) infinite; }
      @keyframes hit {
        0%   { transform: scale(1.38); }
        2.4% { transform: scale(1); }
        100% { transform: scale(1); }
      }
      .snake { fill: none; stroke-linecap: round; stroke-linejoin: round;
               animation: crawl """ + f"{DUR:g}s" + """ linear infinite; }
      @keyframes crawl {
        0%   { stroke-dashoffset: 0; opacity: 0; }
        2%   { opacity: 1; }
        96%  { opacity: 1; }
        100% { stroke-dashoffset: -""" + f"{1000 + SNAKE_LEN}" + """; opacity: 0; }
      }
      @media (prefers-reduced-motion: reduce) {
        .cell { animation: none; }
        .snake { display: none; }
      }
    </style>""")

    # 标题
    p.append(f'<text x="{LEFT}" y="30" font-family="{SANS}" font-size="12" letter-spacing="3" '
             f'fill="{LABEL[theme]}">CONTRIBUTION SNAKE</text>')

    # 格子
    for c, week in enumerate(weeks):
        for r, day in enumerate(week["contributionDays"]):
            lv = level_of(day["contributionCount"])
            seg = c * seg_per_col + (rows - 1 - r if c % 2 == 0 else r)
            if c > 0:
                seg += 1  # 列间横移那一段
            # 蛇头在 seg/total 处时，dashoffset 已经走了 seg/total*1000 个单位；
            # 而整条 dash 要走 1000+SNAKE_LEN，所以格子要比朴素比例提前这么多。
            t = seg / total_segments * DUR * (1000 / (1000 + SNAKE_LEN))
            p.append(
                f'<rect class="cell" x="{LEFT + c * STEP}" y="{TOP + r * STEP}" '
                f'width="{CELL}" height="{CELL}" rx="4" fill="{LEVELS[theme][lv]}" '
                f'style="animation-delay:-{t:.2f}s"/>')

    # 蛇：一段固定长度的 dash 沿路径滑动
    p.append(f'<path class="snake" d="{d}" pathLength="1000" stroke="{SNAKE[theme]}" '
             f'stroke-width="10" stroke-dasharray="{SNAKE_LEN} 1000" opacity="0.62"/>')

    # 右下角说明
    p.append(f'<text x="{860 - LEFT}" y="{height - 14:.0f}" font-family="{SANS}" font-size="11" '
             f'text-anchor="end" fill="{LABEL[theme]}">'
             f'{cal["totalContributions"]} contributions · last {cols} weeks</text>')

    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    cal = fetch()
    print(f"  {cal['totalContributions']} contributions, {len(cal['weeks'])} weeks")
    for theme in ("light", "dark"):
        out = ASSETS / f"snake-{theme}.svg"
        out.write_text(build(theme, cal), encoding="utf-8", newline="\n")
        print(f"  → {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
把 GitHub 贡献日历渲染成一条蛇在啃格子的动画 SVG。

算法照搬 platane/snk（packages/svg-creator + packages/solver），只换美术：
- 蛇身是若干个圆角方块，按 index 从头部 0.9*cell 递减到尾端 0.8*dot
- 每一节蛇自己一条 @keyframes，按帧写 transform:translate()，中间线性插值 → 看起来是滑过去的
- 被蛇头碰到的格子当场从彩色翻成空白色（这就是"吃"）
- 走位用 BFS 找最近的还没吃的格子，蛇身当障碍（同 snk 的 getPathToNextPoint）

跟 snk 的差异只有两处，都是为了适配这张卡：
1. 不搬 tunnel 打包算法（那是为了极速通关，视觉上看不出差别），
   改成贪心最近邻 + BFS，蛇一样会把所有彩色格子吃干净
2. 结尾让蛇从顶部滑出画面、开头从顶部滑入，两头都在裁剪区外，
   所以循环是无缝的，不需要 snk 那段"走回初始姿态"的收尾路径

用法：
    python scripts/build_snake.py
输出：
    assets/snake-light.svg / snake-dark.svg
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import pathlib
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

OWNER = os.environ.get("GH_OWNER") or "mlkgrnt"
STEP_MS = int(os.environ.get("SNAKE_STEP_MS") or 75)

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

# —— 布局（与 snk 同名参数对齐，方便对照源码）——
SIZE_CELL = 15      # 格子间距，对应 snk 的 sizeCell
SIZE_DOT = 12       # 贡献点尺寸，对应 snk 的 sizeDot
STEP = SIZE_CELL
RX = 4              # 果冻方的圆角比例：12px 的 ~31% ≈ 4
LEFT = 34
TOP = 52
WIDTH = 860

SNAKE_N = 4         # 蛇长，对应 snk 的 snake4

LEVELS = {
    "light": ["#edf6f3", "#c9f2e6", "#93e5d0", "#57d2b6", "#26a892"],
    "dark": ["#161e21", "#1f3d37", "#2f6f63", "#4fb39c", "#7fe8cf"],
}
SNAKE = {"light": "#22405e", "dark": "#e6f6f1"}
LABEL = {"light": "#6b8f88", "dark": "#8b949e"}
SANS = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', "
        "'PingFang SC', 'Microsoft YaHei', sans-serif")

Point = tuple[int, int]
Body = tuple[Point, ...]          # 头在前，长度恒为 SNAKE_N

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def fetch() -> dict:
    out = subprocess.check_output(
        ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"login={OWNER}"],
        text=True, encoding="utf-8")
    return json.loads(out)["data"]["user"]["contributionsCollection"]["contributionCalendar"]


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


# ———————————————————————————— 走位 ————————————————————————————

def bfs_path(body: Body, targets: set[Point], w: int, h: int,
             limit: int = 400_000) -> list[Body] | None:
    """BFS over snake states → 到最近目标格的每一帧（同 snk 的 getPathToNextPoint）。"""
    start = body
    if start[0] in targets:
        return []

    parent: dict[Body, Body | None] = {start: None}
    q = deque([start])

    while q and len(parent) < limit:
        cur = q.popleft()
        hx, hy = cur[0]
        for dx, dy in DIRS:
            nx, ny = hx + dx, hy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) in cur[:-1]:          # 尾巴这一帧会挪走，不算障碍
                continue
            nxt = ((nx, ny),) + cur[:-1]
            if nxt in parent:
                continue
            parent[nxt] = cur
            if (nx, ny) in targets:
                out: list[Body] = []
                node: Body | None = nxt
                while node is not None and node != start:
                    out.append(node)
                    node = parent[node]
                out.reverse()
                return out
            q.append(nxt)
    return None


def route(grid: dict[Point, int], w: int, h: int) -> list[Body]:
    """吃掉所有彩色格子的整条轨迹，一头一尾都在画面外。"""
    targets = {p for p, lv in grid.items() if lv > 0}
    # snk 固定从 (0,-1) 进场；这里改成从第一个目标所在列的顶端进场，
    # 免得开头白白横穿十几格空列（进场点本身在裁剪区外，看不出来）
    c0 = min((x for x, _ in targets), default=0)
    body: Body = ((c0, -1), (c0 + 1, -1), (c0 + 2, -1), (c0 + 3, -1))
    chain: list[Body] = [body]

    while targets:
        path = bfs_path(body, targets, w, h)
        if path is None:
            # 兜底：朝最近的格子挪一格（正常不会走到这里）
            tgt = min(targets, key=lambda p: abs(p[0] - body[0][0]) + abs(p[1] - body[0][1]))
            dx = (tgt[0] > body[0][0]) - (tgt[0] < body[0][0])
            dy = (tgt[1] > body[0][1]) - (tgt[1] < body[0][1])
            step = (dx, 0) if dx else (0, dy)
            body = ((body[0][0] + step[0], body[0][1] + step[1]),) + body[:-1]
            chain.append(body)
            continue
        for st in path:
            body = st
            chain.append(body)
            if body[0] in targets:
                targets.discard(body[0])

    # 收尾：把头一路顶出画面，整条蛇都在裁剪区外之后循环就无缝了
    for _ in range(32):
        if all(p[1] < 0 for p in body):
            break
        hx, hy = body[0]
        for dx, dy in ((0, -1), (-1, 0), (1, 0)):
            nx, ny = hx + dx, hy + dy
            if not (-3 <= nx < w + 3 and ny >= -10):
                continue
            if (nx, ny) in body[1:]:
                continue
            body = ((nx, ny),) + body[:-1]
            chain.append(body)
            break
        else:
            break

    return chain


# ———————————————————————————— 渲染 ————————————————————————————

def pct(x: float) -> str:
    return f"{float(f'{x * 100:.2f}'):g}%"


def create_animation(name: str, keyframes: list[tuple[float, str]]) -> str:
    """同 snk 的 mergeKeyFrames：相同样式合并成一个规则，多挂几个百分比。"""
    merged: dict[str, list[float]] = {}
    for t, style in keyframes:
        merged.setdefault(style, []).append(t)
    body = "".join(",".join(pct(t) for t in ts) + "{" + st + "}"
                   for st, ts in sorted(merged.items(), key=lambda kv: kv[1][0]))
    return f"@keyframes {name}{{{body}}}"


def lerp(k: float, a: float, b: float) -> float:
    return (1 - k) * a + k * b


def remove_interpolated(pts: list[Point]) -> list[tuple[Point, int]]:
    """同 snk：连续三点共线且中间点正好是中点时丢掉，关键帧少一半。"""
    out: list[tuple[Point, int]] = []
    n = len(pts)
    for i, p in enumerate(pts):
        if 0 < i < n - 1:
            a, b = pts[i - 1], pts[i + 1]
            if abs((a[0] + b[0]) / 2 - p[0]) < 0.01 and abs((a[1] + b[1]) / 2 - p[1]) < 0.01:
                continue
        out.append((p, i))
    return out


def build(theme: str, cal: dict, cols: int, rows: int, chain: list[Body],
          static_frame: int | None = None) -> str:
    """static_frame 给定帧号时输出一张静态图（不带动画），用于视觉核对。"""
    total = len(chain)
    duration = total * STEP_MS
    grid_w = cols * STEP - (STEP - SIZE_DOT)
    grid_h = rows * STEP - (STEP - SIZE_DOT)
    height = TOP + grid_h + 36

    elems: list[str] = []
    css: list[str] = [
        f".c{{fill:{LEVELS[theme][0]};animation:none linear {duration}ms infinite}}",
        f".p{{fill:{SNAKE[theme]};shape-rendering:geometricPrecision;"
        f"animation:none linear {duration}ms infinite}}",
    ]

    elems.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:.0f}" '
        f'width="100%" role="img" aria-label="Contribution snake">')
    elems.append("<title>Contribution snake</title>")
    elems.append(f"<desc>过去一年的贡献日历，共 {cal['totalContributions']} 次贡献，"
                 f"一条蛇从左上角爬进来，边爬边把贡献格子吃掉。</desc>")
    elems.append(f'<text x="{LEFT}" y="30" font-family="{SANS}" font-size="12" '
                 f'letter-spacing="3" fill="{LABEL[theme]}">CONTRIBUTION SNAKE</text>')

    # ---- 格子 ----
    cells: dict[Point, int] = {}
    for c, week in enumerate(cal["weeks"]):
        for r, day in enumerate(week["contributionDays"]):
            cells[(c, r)] = level_of(day["contributionCount"])

    eaten: dict[Point, int] = {}
    for j, body in enumerate(chain):
        head = body[0]
        if cells.get(head, 0) > 0 and head not in eaten:
            eaten[head] = j

    m = (SIZE_CELL - SIZE_DOT) / 2
    empty = LEVELS[theme][0]
    rects: list[str] = []
    for (x, y) in sorted(cells):
        lv = cells[(x, y)]
        t = eaten.get((x, y))
        if static_frame is not None:
            done = t is not None and static_frame >= t
            fill = empty if (done or lv == 0) else LEVELS[theme][lv]
            # 必须写行内 style：presentation attribute 会被 .c 的 fill 覆盖掉
            rects.append(f'<rect x="{LEFT + x * STEP + m:.1f}" '
                         f'y="{TOP + y * STEP + m:.1f}" width="{SIZE_DOT}" '
                         f'height="{SIZE_DOT}" rx="{RX}" ry="{RX}" style="fill:{fill}"/>')
            continue
        cls = "c"
        if t is not None:
            name = f"c{x}-{y}"
            cls = f"c {name}"
            tc = t / total
            color = LEVELS[theme][lv]
            css.append(create_animation(name, [
                (max(tc - 0.0001, 0), f"fill:{color}"),
                (min(tc + 0.0001, 1), f"fill:{empty}"),
                (1, f"fill:{empty}"),
            ]))
            css.append(f".c.{name}{{fill:{color};animation-name:{name}}}")
        rects.append(f'<rect class="{cls}" x="{LEFT + x * STEP + m:.1f}" '
                     f'y="{TOP + y * STEP + m:.1f}" width="{SIZE_DOT}" '
                     f'height="{SIZE_DOT}" rx="{RX}" ry="{RX}"/>')

    # ---- 蛇身 ----
    parts = min(SNAKE_N, len(chain[0]))
    d_min = SIZE_DOT * 0.8
    d_max = SIZE_CELL * 0.9
    i_max = min(4, parts)

    part_elems: list[str] = []
    for i in range(parts):
        u = (1 - min(i, i_max) / i_max) ** 2
        s = lerp(u, d_min, d_max)
        off = (SIZE_CELL - s) / 2
        r = min(4.5, (4 * s) / SIZE_DOT)

        positions = [chain[j][i] for j in range(total)]
        name = f"p{i}"
        if static_frame is not None:
            px, py = positions[min(static_frame, total - 1)]
            tf = f'transform="translate({px * SIZE_CELL},{py * SIZE_CELL})"'
            cls = "p"
        else:
            tfs = remove_interpolated(positions)
            css.append(create_animation(
                name,
                [(t / total, f"transform:translate({p[0] * SIZE_CELL}px,{p[1] * SIZE_CELL}px)")
                 for p, t in tfs]))
            x0, y0 = positions[0]
            css.append(f".p.{name}{{transform:translate({x0 * SIZE_CELL}px,{y0 * SIZE_CELL}px);"
                       f"animation-name:{name}}}")
            tf = ""
            cls = f"p {name}"

        if i == 0:
            # 头：加一点果冻方的镜面高光，跟着头一起平移
            part_elems.append(
                f'<g class="{cls}" {tf}>'
                f'<rect x="{off:.1f}" y="{off:.1f}" width="{s:.1f}" height="{s:.1f}" '
                f'rx="{r:.1f}" ry="{r:.1f}"/>'
                f'<ellipse cx="{off + s * 0.30:.1f}" cy="{off + s * 0.26:.1f}" '
                f'rx="{s * 0.17:.1f}" ry="{s * 0.13:.1f}" fill="#fff" opacity="0.5"/>'
                f'</g>')
        else:
            part_elems.append(
                f'<rect class="{cls}" {tf} x="{off:.1f}" y="{off:.1f}" '
                f'width="{s:.1f}" height="{s:.1f}" rx="{r:.1f}" ry="{r:.1f}"/>')

    elems.append("<style>")
    elems.append("".join(css))
    elems.append("@media (prefers-reduced-motion:reduce){.c,.p{animation:none!important}}")
    elems.append("</style>")

    # 只裁网格：蛇进出画面时才不会飞到标题上
    elems.append(f'<clipPath id="g"><rect x="{LEFT - 2}" y="{TOP - 2}" '
                 f'width="{grid_w + 4:.1f}" height="{grid_h + 4:.1f}" rx="6"/></clipPath>')
    elems.append('<g clip-path="url(#g)">')
    elems.extend(rects)
    elems.extend(part_elems)
    elems.append("</g>")

    elems.append(f'<text x="{WIDTH - LEFT}" y="{height - 12:.0f}" font-family="{SANS}" '
                 f'font-size="11" text-anchor="end" fill="{LABEL[theme]}">'
                 f'{cal["totalContributions"]} contributions · last {cols} weeks</text>')
    elems.append("</svg>")
    return "\n".join(elems)


def main() -> None:
    cal = fetch()
    cols = len(cal["weeks"])
    rows = max(len(w["contributionDays"]) for w in cal["weeks"])
    print(f"  {cal['totalContributions']} contributions, {cols} weeks")

    grid = {(c, r): level_of(d["contributionCount"])
            for c, week in enumerate(cal["weeks"])
            for r, d in enumerate(week["contributionDays"])}

    chain = route(grid, cols, rows)
    lit = sum(1 for v in grid.values() if v > 0)
    print(f"  route: {len(chain)} frames / {len(chain) * STEP_MS / 1000:.1f}s, "
          f"吃掉 {lit} 格")

    # --frame N：只吐一张静态图，用来肉眼核对某个瞬间（不参与提交）
    if "--frame" in sys.argv:
        k = int(sys.argv[sys.argv.index("--frame") + 1])
        theme = "dark" if "--dark" in sys.argv else "light"
        out = ASSETS / f"_frame{k}-{theme}.svg"
        out.write_text(build(theme, cal, cols, rows, chain, static_frame=k),
                       encoding="utf-8", newline="\n")
        print(f"  → {out.relative_to(ROOT)} (静态第 {k} 帧)")
        return

    for theme in ("light", "dark"):
        out = ASSETS / f"snake-{theme}.svg"
        out.write_text(build(theme, cal, cols, rows, chain), encoding="utf-8", newline="\n")
        print(f"  → {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

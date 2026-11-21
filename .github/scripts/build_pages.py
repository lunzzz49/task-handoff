#!/usr/bin/env python3
"""把仓库里的 Markdown 渲染成 GitHub Pages 站点。

不依赖 Jekyll：输出结构完全由这里决定，避免隐式规则导致链接 404。
CI 里只需 `pip install markdown`，本地无需任何第三方库即可干跑 `--check`。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_site"

# 参与构建的 Markdown：路径 -> 输出路径（相对 _site）
PAGES = {
    "README.md": "index.html",
    "examples/README.md": "examples/index.html",
    "SKILL.md": "skill.html",
    # 输出路径必须与正文里的相对链接一致：README 写的是 references/integration.md，
    # fix_links 会把它改成 references/integration.html，放在根目录就会 404。
    "references/integration.md": "references/integration.html",
}

CSS = """
:root { --fg:#1f2328; --mute:#656d76; --line:#d0d7de; --bg:#ffffff; --code:#f6f8fa; --accent:#0969da; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 48px 24px 96px; }
h1 { font-size: 2em; margin: .6em 0 .4em; letter-spacing:-.01em; }
h2 { font-size: 1.4em; margin: 2em 0 .6em; padding-bottom:.3em; border-bottom:1px solid var(--line); }
h3 { font-size: 1.1em; margin: 1.6em 0 .5em; }
p, li { color: var(--fg); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code { font-family: Consolas,"SF Mono",Menlo,monospace; font-size: .88em;
  background: var(--code); padding: .15em .35em; border-radius: 5px; }
pre { background: var(--code); padding: 14px 16px; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; font-size: .86em; line-height: 1.55; }
blockquote { margin: 1em 0; padding: .2em 1em; color: var(--mute); border-left: 3px solid var(--line); }
table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: .93em; }
th, td { border: 1px solid var(--line); padding: 7px 12px; text-align: left; vertical-align: top; }
th { background: var(--code); font-weight: 600; }
hr { border:0; border-top:1px solid var(--line); margin: 2.4em 0; }
img { max-width: 100%; }
.nav { margin-bottom: 2.5em; font-size: .9em; color: var(--mute); }
.nav a { margin-right: 1em; }
"""

TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main>
<nav class="nav"><a href="{home}">task-handoff</a><a href="{examples}">真实产出</a><a href="{skill}">SKILL.md</a><a href="{integration}">接入</a></nav>
{body}
</main>
</body>
</html>
"""


def strip_front_matter(text: str) -> str:
    """去掉 SKILL.md 顶部的 YAML front matter，它不该出现在网页正文里。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def fix_links(html: str) -> str:
    """Markdown 渲染后的 .md 链接指向 GitHub 而非本站，改成 .html。"""
    html = re.sub(r'href="([^"]*?)\.md(#[^"]*)?"', lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', html)
    # 目录链接补 index
    html = html.replace('href="examples/"', 'href="examples/index.html"')
    html = html.replace('href="./"', 'href="index.html"')
    return html


def render(md_text: str) -> str:
    import markdown

    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )


def build(write: bool = True) -> list[str]:
    """生成站点。write=False 时只检查文件是否存在、能否渲染。"""
    try:
        import markdown  # noqa: F401
    except ImportError:
        if write:
            print("需要 markdown 库：pip install markdown", file=sys.stderr)
            raise SystemExit(1)
        print("[!] 未安装 markdown，跳过渲染检查（CI 里会装）")
        markdown = None

    if write:
        OUT.mkdir(exist_ok=True)

    produced = []
    for src_rel, out_rel in PAGES.items():
        src = ROOT / src_rel
        if not src.exists():
            print(f"[!] 缺少 {src_rel}，跳过", file=sys.stderr)
            continue
        text = strip_front_matter(src.read_text(encoding="utf-8"))
        body = fix_links(render(text)) if write else ""
        title = "task-handoff" if out_rel == "index.html" else src.stem
        depth = len(Path(out_rel).parts) - 1
        prefix = "../" * depth
        html = TEMPLATE.format(
            title=title,
            css=CSS,
            body=body,
            home=prefix + "index.html",
            examples=prefix + "examples/index.html",
            skill=prefix + "skill.html",
            integration=prefix + "references/integration.html",
        )
        target = OUT / out_rel
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        produced.append(out_rel)

    # examples 下其余文档
    for src in sorted((ROOT / "examples").glob("*.md")):
        if src.name == "README.md":
            continue
        rel_out = f"examples/{src.stem}.html"
        text = strip_front_matter(src.read_text(encoding="utf-8"))
        body = fix_links(render(text)) if write else ""
        html = TEMPLATE.format(
            title=f"{src.stem} · 交接示例",
            css=CSS,
            body=body,
            home="../index.html",
            examples="index.html",
            skill="../skill.html",
            integration="../references/integration.html",
        )
        target = OUT / rel_out
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        produced.append(rel_out)

    return produced


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    files = build(write=not check_only)
    action = "检查" if check_only else "生成"
    print(f"{action}完成，{len(files)} 个页面：")
    for f in files:
        print(f"  {f}")

#!/usr/bin/env python3
"""交接文档工具（零第三方依赖，Python 3.8+）。

子命令：
  new     [--slug 主题] [--root 路径]       创建 .handoff/ 并生成带时间戳的骨架
  latest  [--root 路径]                     打印最新一份交接文档的绝对路径
  check   [文件] [--root 路径]              校验章节完整性 / 占位符 / 密钥 / 空泛下一步
  log     --event 描述 [--files 路径] [--verify 说明]
                                            把一条进展追加进「附录：进展时间线」，写前自动快照
  journal [--root 路径]                     列出所有进展条目及其 ID
  undo    [--id 短ID] [文件]                撤销一条进展（默认最后一条）
  restore [文件]                            把文档整体回滚到最近一次 log 之前的快照

撤回保障：每次 log 前把文档复制到 .handoff/.snapshots/，保留最近 20 份。
骨架的唯一来源是 references/handoff-template.md 里第一个 markdown 代码块。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "references" / "handoff-template.md"
HANDOFF_DIR = ".handoff"
SNAPSHOT_DIR = ".snapshots"
MAX_SNAPSHOTS = 20
TIMELINE_HEADING = "## 附录：进展时间线（自动追加）"
ARCHIVE_HEADING = "## 附录：已归档进展"

# 跨阶段不变的章节：新建交接文档时从上一份继承
INHERIT_SECTIONS = (1, 4)

ROOT_MARKERS = (
    ".git",
    "requirements.txt", "pyproject.toml", "package.json",  # Python / Node
    "go.mod", "Cargo.toml",                                 # Go / Rust
    "pom.xml", "settings.gradle", "settings.gradle.kts",    # JVM
    "CMakeLists.txt",                                       # C / C++
    "composer.json", "Gemfile",                             # PHP / Ruby
)

REQUIRED_SECTIONS = {
    1: "一句话目标",
    2: "阶段结论",
    3: "当前状态",
    4: "技术栈与既定契约",
    5: "关键决策",
    6: "坑与约束",
    7: "文件地图",
    8: "验证方法",
    9: "下一步",
    10: "接手方式",
}

# 只匹配「有值」的密钥；仅写变量名（如 OPENAI_API_KEY）不算
SECRET_PATTERNS = [
    (r"\bsk-[A-Za-z0-9]{16,}", "疑似 OpenAI/Anthropic 风格密钥"),
    (r"\bghp_[A-Za-z0-9]{20,}", "疑似 GitHub token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "疑似 AWS Access Key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥内容"),
    (r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}", "明文凭据赋值"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}", "Bearer token"),
]

VAGUE_WORDS = ("继续", "优化", "完善", "推进", "跟进", "进一步", "打磨", "收尾", "完善细节")

# 数量断言：「19 个测试文件」这类。机械校验验不了真伪，只能在 --stale 时提醒人去数。
COUNT_RE = re.compile(
    r"\d+\s*个\s*(?:测试文件|测试用例|测试|模块|接口|文件|组件|类|表|包|函数|字段|脚本)"
)

# 条目必须同时满足：6 位短 ID + 紧跟「日期 时间」+「· 」分隔。
# 只要求 ID 会误伤正文——`c9f1a2` 这类租户编号、commit 短 SHA、色值 #a1b2c3
# 写在列表项里时，会被当成进展条目从原位置搬走。日期时间这一层把误判概率压到可忽略。
ENTRY_RE = re.compile(r"^- `([0-9a-f]{6})` \d{4}-\d{2}-\d{2} \d{2}:\d{2} · .*$", re.M)

# 骨架里未填的占位符一定含中文 / 空格 / 斜杠 / 省略号；纯 ASCII 的标识符形态
# （<String>、<T>、<K,V>、<Response[T]>）是代码里的类型参数，不是没填。
HTML_TAG_RE = re.compile(
    r"</?(br|div|span|p|b|i|code|sup|sub|table|tr|td|th|ul|ol|li|a|em|strong|pre|hr)\b"
)
TYPE_ARG_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*"
    r"(\[\s*[A-Za-z0-9_,\s\[\]]*\])?$"
)


def is_scaffold_placeholder(token: str) -> bool:
    """<...> 片段是否真的是「未填的骨架占位符」，而不是 HTML/XML 标签或类型参数。"""
    if HTML_TAG_RE.match(token):
        return False
    inner = token[1:-1].strip()
    if not inner:
        return False
    # 闭合标签 </source>、</module>：占位符不会以 / 开头
    if inner.startswith("/"):
        return False
    return not TYPE_ARG_RE.match(inner)


def find_placeholders(text: str):
    """列出文档里所有未填的骨架占位符。"""
    return [p for p in re.findall(r"<[^<>\n]{2,60}>", text) if is_scaffold_placeholder(p)]

FALLBACK_SCAFFOLD = """# 交接：<阶段主题>

- 生成时间：{{TIME}}
- 项目：{{PROJECT}}（{{ROOT}}）
- 覆盖范围：<...>
- 上一份交接：<路径，或「无」>
- 状态：<已完成 / 进行中 / 阻塞>

## 1. 一句话目标

## 2. 阶段结论

## 3. 当前状态

## 4. 技术栈与既定契约

## 5. 关键决策

## 6. 坑与约束

## 7. 文件地图

## 8. 验证方法

## 9. 下一步

## 10. 接手方式
"""


def setup_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def find_root(start: Path) -> Path:
    p = start.resolve()
    # .git 是最可靠的项目根信号：多模块项目里每个子模块都有自己的 pom.xml /
    # build.gradle，「最近标记」会停在子模块，但仓库根只有一个。
    for candidate in (p, *p.parents):
        if (candidate / ".git").exists():
            return candidate
    # 没有版本控制时，退而用构建文件标记（最近优先，是近似值）
    for candidate in (p, *p.parents):
        if any((candidate / m).exists() for m in ROOT_MARKERS):
            return candidate
    return p


def root_of_doc(doc: Path, fallback: Path) -> Path:
    """文档在 .handoff/ 下时，项目根就是它的上两级，比 cwd 探测更可靠。"""
    if doc.parent.name == HANDOFF_DIR:
        return doc.parent.parent
    return fallback


def git_branch(root: Path):
    """返回当前分支名；非 git 仓库或游离 HEAD 返回 None。

    用 symbolic-ref 而不是 rev-parse --abbrev-ref：后者在「已 init 但还没有首次
    提交」的空仓库里会 fatal，导致空仓库被误判成「非 git 仓库」，分支隔离静默失效。
    """
    try:
        sym = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        if sym.returncode == 0:
            name = sym.stdout.strip()
            if name and name != "HEAD":
                return name
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            name = out.stdout.strip()
            return None if not name or name == "HEAD" else name
    except Exception:
        pass
    return None


def header_branch(text: str):
    m = re.search(r"^-\s*分支[：:]\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def generated_time(text: str):
    m = re.search(r"^-\s*生成时间[：:]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text, re.M)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return None


PATH_RE = re.compile(r"`([^`\n]+)`")
PATH_EXT_RE = re.compile(
    r"\.(py|ts|tsx|js|jsx|json|md|txt|ya?ml|toml|sql|css|scss|html|sh|bat|ps1|cfg|ini|env|lock)$",
    re.I,
)


def looks_like_path(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 200:
        return False
    if s.startswith(("git@", "-", "~")):
        return False
    # 任意 URI scheme（http://、chrome://、file://、vscode://）都不是项目内文件路径。
    # 浏览器扩展与 IDE 插件的文档里 chrome:// 出现频率很高。
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", s):
        return False
    # 以 / 开头的是 HTTP 路由（`/api/orders`）或系统绝对路径，不在项目根下核对，
    # 否则每个接口路径都会被 --stale 报成「路径已不存在」。
    if s.startswith("/"):
        return False
    # 域名形态：Go module path、npm 包名、文档站地址（charm.land/bubbletea/v2、
    # github.com/org/repo）。它们不是文件系统里的相对路径，核对毫无意义。
    if re.match(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+/", s):
        return False
    if " " in s or "*" in s or "?" in s or "=" in s:
        return False
    if re.search(r"[/\\]", s):
        return True
    return bool(PATH_EXT_RE.search(s))


# 目录简写（文中写 `api/`，实际在 `backend/api/`）不该被 --stale 判成「文档撒谎」。
# 根下找不到时按目录名在项目内搜一次，搜到就说明只是写简了。
SEARCH_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build",
    ".idea", ".vscode", "target", ".next", ".pytest_cache", ".mypy_cache",
}
MAX_SEARCH_DEPTH = 4
MAX_SEARCH_HITS = 5


def find_entries_by_name(root: Path, name: str, want_dir=None):
    """在项目内按名字搜文件/目录，返回相对路径列表（剪掉依赖目录、限深度）。

    want_dir=True 只找目录，False 只找文件，None 两者都找。
    """
    if not name or name in (".", ".."):
        return []
    hits = []
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        rel_dir = os.path.relpath(dirpath, root_str)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        dirnames[:] = [d for d in dirnames if d not in SEARCH_SKIP_DIRS]
        candidates = []
        if want_dir in (None, True) and name in dirnames:
            candidates.append(name)
        if want_dir in (None, False) and name in filenames:
            candidates.append(name)
        for cand in candidates:
            rel = cand if rel_dir == "." else f"{rel_dir.replace(os.sep, '/')}/{cand}"
            hits.append(rel)
            if len(hits) >= MAX_SEARCH_HITS:
                return hits
        if depth >= MAX_SEARCH_DEPTH:
            dirnames[:] = []
    return hits


def find_dir_by_name(root: Path, name: str):
    """只找目录的便捷包装。"""
    return find_entries_by_name(root, name, want_dir=True)


# 与路径同一行出现这些词，说明它属于「说到但不存在」的语境（蓝图 / 已排除 / 明确说没有）。
# 不过滤会把 --stale 的语义弄反：文档写「项目根无 `AGENTS.md`」，工具却报「AGENTS.md 不存在」。
NEGATION_WORDS = (
    "无", "没有", "不存在", "未创建", "未建", "不建", "不提前", "排除", "忽略",
    "蓝图", "规划", "待建", "暂不", "不改", "不要", "勿动",
    # 「说明某路径不在了」的常见说法，写布局差异时高频出现
    "不是", "省掉", "去掉", "移除", "删除", "不设", "无需",
)


def line_has_negation(text: str, pos: int) -> bool:
    """pos 所在的那一行是否含否定词。"""
    start = text.rfind("\n", 0, pos) + 1
    stop = text.find("\n", pos)
    line = text[start:stop if stop != -1 else len(text)]
    return any(word in line for word in NEGATION_WORDS)


def extract_paths(text: str):
    """从反引号片段里提取疑似项目内路径，去重保序。

    三类必须剔除，否则真路径会被淹掉：
    - `> ` 引用块（骨架里的填写说明）
    - `<...>` 占位符（骨架示例路径）
    - 同一行含否定词的路径（蓝图、已排除、明确说「没有」）
    """
    cleaned = re.sub(r"^[ \t]*>.*$", "", text, flags=re.M)
    # 等长替换，保住后面判断「路径在哪一行」用的下标
    cleaned = re.sub(r"<[^<>\n]{1,120}>", lambda m: " " * len(m.group(0)), cleaned)
    seen, out = set(), []
    for match in PATH_RE.finditer(cleaned):
        raw = match.group(1)
        if not looks_like_path(raw):
            continue
        if line_has_negation(cleaned, match.start()):
            continue
        s = raw.strip().replace("\\", "/")
        if s.startswith("./"):
            s = s[2:]
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def section_span(text: str, num: int):
    """返回 '## N. xxx' 章节正文的起止下标（不含标题行）。"""
    m = re.search(rf"^##\s*{num}\.\s*.*$", text, re.M)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"^##\s", text[start:], re.M)
    end = start + nxt.start() if nxt else len(text)
    return start, end


def section_bounds(text: str, heading: str):
    """按完整标题行定位任意「## 」章节，返回正文起止下标；没有该节返回 None。"""
    m = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"\n## ", text[start:])
    end = start + nxt.start() + 1 if nxt else len(text)
    return start, end


def section_body(text: str, num: int) -> str:
    span = section_span(text, num)
    return text[span[0]:span[1]].strip("\n") if span else ""


def set_section_body(text: str, num: int, body: str) -> str:
    span = section_span(text, num)
    if not span:
        return text
    s, e = span
    return text[:s] + "\n\n" + body.strip("\n") + "\n\n" + text[e:]


def constraint_block(text: str) -> str:
    """取第 6 节里「约束与红线」子块的内容。"""
    m = re.search(r"\*\*约束与红线\*\*\s*\n(.*?)(?=\n\*\*[^\n]*\*\*|\n##\s|\Z)", text, re.S)
    return m.group(1).strip("\n") if m else ""


def set_constraint_block(text: str, body: str) -> str:
    m = re.search(r"(\*\*约束与红线\*\*\s*\n)(.*?)(?=\n\*\*[^\n]*\*\*|\n##\s|\Z)", text, re.S)
    if not m:
        return text
    return text[:m.start(2)] + "\n" + body.strip("\n") + "\n" + text[m.end(2):]


def is_filled(body: str) -> bool:
    """内容够长且没有残留的「未填占位符」，才算「填过」。

    用 is_scaffold_placeholder 过滤：否则含 `List<String>` 这类类型参数的技术栈
    一节会被判成没填，跨阶段永远继承不过来。
    """
    if not body or len(body.strip()) < 20:
        return False
    tokens = re.findall(r"<[^<>\n]{1,120}>", body)
    return not any(is_scaffold_placeholder(t) for t in tokens)


def load_scaffold() -> str:
    """抽取模板里第一个 markdown 代码块，优先四反引号（内容可能嵌套三反引号）。"""
    if TEMPLATE.exists():
        text = TEMPLATE.read_text(encoding="utf-8")
        for fence in ("````", "```"):
            match = re.search(re.escape(fence) + r"markdown\n(.*?)\n" + re.escape(fence), text, re.S)
            if match:
                return match.group(1)
    return FALLBACK_SCAFFOLD


def handoff_files(root: Path):
    folder = root / HANDOFF_DIR
    if not folder.is_dir():
        return []
    return sorted(folder.glob("handoff-*.md"))


def create_doc(root: Path, slug: str, inherit: bool = False):
    """新建交接文档，返回 (路径, 继承说明列表)。永不覆盖既有文件。"""
    folder = root / HANDOFF_DIR
    folder.mkdir(exist_ok=True)
    existing = handoff_files(root)
    prev = existing[-1] if (inherit and existing) else None

    now = datetime.now()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", slug or "session").strip("-") or "session"
    target = folder / f"handoff-{now:%Y-%m-%d-%H%M%S}-{safe}.md"
    index = 1
    while target.exists():
        target = folder / f"handoff-{now:%Y-%m-%d-%H%M%S}-{safe}-{index}.md"
        index += 1

    branch = git_branch(root) or "无（非 git 仓库）"
    body = (
        load_scaffold()
        .replace("YYYY-MM-DD HH:mm", f"{now:%Y-%m-%d %H:%M}")
        .replace("<项目名>", root.name)
        .replace("<项目根绝对路径>", str(root).replace("\\", "/"))
        .replace("{{TIME}}", f"{now:%Y-%m-%d %H:%M}")
        .replace("{{PROJECT}}", root.name)
        .replace("{{ROOT}}", str(root).replace("\\", "/"))
        .replace("{{BRANCH}}", branch)
        .replace("<git 分支名，非 git 项目写「无」>", branch)
    )

    notes = []
    if prev:
        old = prev.read_text(encoding="utf-8")
        for num in INHERIT_SECTIONS:
            chunk = section_body(old, num)
            if is_filled(chunk):
                body = set_section_body(
                    body, num,
                    f"> 继承自 `{prev.name}`，请核对是否仍然有效\n\n{chunk}",
                )
                notes.append(f"第 {num} 节")
        block = constraint_block(old)
        if is_filled(block):
            body = set_constraint_block(body, f"> 继承自 `{prev.name}`，请核对\n\n{block}")
            notes.append("第 6 节「约束与红线」")

    target.write_text(body, encoding="utf-8")
    return target, notes


def resolve_doc(arg, root: Path):
    """定位目标文档：显式路径 > 最新一份 > None。"""
    if arg:
        p = Path(arg).resolve()
        return p if p.exists() else None
    files = handoff_files(root)
    return files[-1] if files else None


def drop_empty_archive(text: str) -> str:
    """归档区被撤空后连标题一起删掉，避免文档尾部留一个空壳章节。"""
    m = re.search(rf"^{re.escape(ARCHIVE_HEADING)}\s*$", text, re.M)
    if not m:
        return text
    bounds = section_bounds(text, ARCHIVE_HEADING)
    if not bounds:
        return text
    s, e = bounds
    # 只剩空白或分隔线时视为空
    if text[s:e].strip(" \t\n-—="):
        return text
    head = text[:m.start()].rstrip("\n")
    tail = text[e:].lstrip("\n")
    merged = head + ("\n\n" + tail if tail.strip() else "")
    return merged.rstrip("\n") + "\n"


def snapshot(doc: Path) -> Path:
    d = doc.parent / SNAPSHOT_DIR
    d.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dst = d / f"{doc.stem}.{ts}.bak"
    shutil.copy2(doc, dst)
    olds = sorted(d.glob(f"{doc.stem}.*.bak"))
    for old in olds[:-MAX_SNAPSHOTS]:
        try:
            old.unlink()
        except OSError:
            pass
    return dst


def append_to_section(text: str, heading: str, block: str) -> str:
    """把一段内容插到指定章节末尾；没有该节就追加到文末。"""
    idx = text.find(heading)
    if idx == -1:
        return text.rstrip() + "\n\n" + heading + "\n\n" + block.rstrip() + "\n"
    after = idx + len(heading)
    nxt = re.search(r"\n## ", text[after:])
    if nxt:
        pos = after + nxt.start() + 1
        head = text[:pos].rstrip() + "\n"
        rest = text[pos:]
        if rest.strip():
            return head + block.rstrip() + "\n\n" + rest
        return head + block.rstrip() + "\n"
    return text.rstrip() + "\n" + block.rstrip() + "\n"


def append_entry(text: str, line: str) -> str:
    return append_to_section(text, TIMELINE_HEADING, line)


def latest_snapshot(doc: Path):
    d = doc.parent / SNAPSHOT_DIR
    if not d.is_dir():
        return None
    snaps = sorted(d.glob(f"{doc.stem}.*.bak"))
    return snaps[-1] if snaps else None


def cmd_new(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    inherit = getattr(args, "inherit", False)
    target, notes = create_doc(root, args.slug, inherit=inherit)
    print(f"已创建：{target}")
    print(f"项目根：{root}")
    print(f"骨架来源：{'references/handoff-template.md' if load_scaffold() != FALLBACK_SCAFFOLD else '内置兜底'}")
    if notes:
        print(f"已继承上一份的：{'、'.join(notes)}")
        print("继承内容带「请核对是否仍然有效」标记，确认后请删掉该行")
    elif inherit:
        print("上一份没有可继承的内容（不存在或未填写）")
    return 0


def cmd_latest(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    files = handoff_files(root)
    if not files:
        print(f"{root / HANDOFF_DIR} 下没有交接文档", file=sys.stderr)
        return 1
    latest = files[-1]
    text = latest.read_text(encoding="utf-8")
    status = re.search(r"^-\s*状态[：:]\s*(.+)$", text, re.M)
    print(str(latest))
    print(f"行数：{len(text.splitlines())}    状态：{status.group(1).strip() if status else '未填'}")
    entries = ENTRY_RE.findall(text)
    if entries:
        print(f"进展条目：{len(entries)} 条")
    if len(files) > 1:
        print(f"同目录共 {len(files)} 份，这是最新的一份")

    # 刚 new 完就中断的情况：骨架没填，连头部的「状态」都是占位符。
    # 不提示的话，接手的人可能把空骨架当成真实交接读，把「进行中」当真。
    left = find_placeholders(text)
    if left:
        print(f"[!] 这份还有 {len(left)} 处未填占位符，可能是刚建好还没写")
        if len(files) > 1:
            print(f"    上一份（更可能是你要读的）：{files[-2]}")
    return 0


def cmd_check(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    target = resolve_doc(args.file, root)
    if not target:
        print("找不到交接文档", file=sys.stderr)
        return 1
    root = root_of_doc(target, root)

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    problems = []
    warnings = []

    print(f"校验：{target}")
    print(f"行数：{len(lines)}")
    print()

    headings = {}
    for line in lines:
        m = re.match(r"^##\s*(\d+)\.\s*(.+?)\s*$", line)
        if m:
            headings[int(m.group(1))] = m.group(2)

    for num, title in REQUIRED_SECTIONS.items():
        if num not in headings:
            problems.append(f"缺少第 {num} 节「{title}」")
        elif title not in headings[num] and headings[num] not in title:
            warnings.append(f"第 {num} 节标题为「{headings[num]}」，标准要求包含「{title}」")

    placeholders = find_placeholders(text)
    if placeholders:
        shown = "、".join(dict.fromkeys(placeholders[:5]))
        problems.append(f"残留占位符 {len(placeholders)} 处：{shown}{' 等' if len(placeholders) > 5 else ''}")

    seen_secrets = set()
    for pattern, label in SECRET_PATTERNS:
        for m in re.finditer(pattern, text):
            snippet = m.group(0)[:24].replace("\n", " ")
            if (label, snippet) in seen_secrets:
                continue
            seen_secrets.add((label, snippet))
            problems.append(f"疑似敏感信息（{label}）：{snippet}…")

    action_block = re.search(r"\*\*第一步动作\*\*\s*\n+((?:>.*\n?)+)", text)
    if not action_block:
        problems.append("找不到「第一步动作」区块（应是 > 引用块）")
    else:
        action = action_block.group(1)
        if len(action.strip()) < 15:
            problems.append("「第一步动作」过短，无法执行")
        elif any(w in action for w in VAGUE_WORDS) and "`" not in action:
            warnings.append("「第一步动作」含空泛词且没有具体路径/命令，参考 standards.md 自检第 1 条")

    if len(lines) > 400:
        warnings.append(f"篇幅 {len(lines)} 行，超过 400 行上限（见 standards.md 篇幅界标）")
    elif len(lines) < 40:
        warnings.append(f"篇幅仅 {len(lines)} 行，可能过于稀疏")

    # standards.md 3.1 要求每条进展都带验证方式；这里把「必填」从文字要求变成可查项
    tl = section_bounds(text, TIMELINE_HEADING)
    if tl:
        tl_scope = text[tl[0]:tl[1]]
        no_verify = [
            m.group(1) for m in ENTRY_RE.finditer(tl_scope) if "· 验证：" not in m.group(0)
        ]
        if no_verify:
            shown = "、".join(no_verify[:5])
            warnings.append(
                f"{len(no_verify)} 条进展缺「验证：」（{shown}），等于假账，见 standards.md 3.1"
            )

    # standards.md 2.6：决策表必须标来源，否则分不清项目立场与你的推断
    decision = section_body(text, 5)
    if decision:
        header = next((ln for ln in decision.splitlines() if ln.strip().startswith("|")), "")
        if header and "来源" not in header:
            warnings.append(
                "第 5 节「关键决策」表缺少「来源」列，分不清事实与推断（见 standards.md 2.6）"
            )

    if getattr(args, "stale", False):
        doc_time = generated_time(text) or datetime.fromtimestamp(target.stat().st_mtime)
        paths = extract_paths(text)
        missing, changed, relocated = [], [], []
        for p in paths:
            fp = root / p
            if not fp.exists():
                # 简写容忍：文中写 `api/` 或 `Start.bat`，实际在 `backend/api`、`sub/Start.bat`。
                # 按名字搜一次再判定，搜到说明只是没写全路径，不算文档撒谎。
                base = p.rstrip("/").split("/")[-1]
                hits = find_entries_by_name(
                    root, base, want_dir=True if p.endswith("/") else None
                )
                if hits:
                    relocated.append((p, hits))
                    continue
                missing.append(p)
                continue
            mtime = datetime.fromtimestamp(fp.stat().st_mtime)
            # 生成时间只精确到分钟，留 60 秒容差，避免同分钟内建的文件被误判
            if mtime > doc_time + timedelta(seconds=60):
                changed.append((p, mtime))
        print(f"事实核对：基准 {doc_time:%Y-%m-%d %H:%M} · 文中路径 {len(paths)} 个")
        for p, hits in relocated:
            shown = "、".join(hits[:3])
            more = f" 等 {len(hits)} 处" if len(hits) > 3 else ""
            print(f"[i] 路径简写：{p} → 实际位于 {shown}{more}")
        for p in missing:
            problems.append(f"路径已不存在（删除或改名）：{p}")
        for p, t in changed:
            warnings.append(f"文档写完后被改过：{p}（{t:%Y-%m-%d %H:%M}）")
        if paths and not missing and not changed:
            print("[ok] 文中路径均存在，且未在文档写完后改动")
        elif not paths:
            print("[!] 未提取到可核对的路径——文中请用反引号写相对路径")

        # 数字是 check 唯一验不了的东西：路径能 stat，数字只能人眼数
        raw = COUNT_RE.findall(text)
        if len(raw) >= 3:
            shown = "、".join(dict.fromkeys(raw))
            print(f"[!] {len(raw)} 处数量断言无法自动核实（{shown}），按自检第 4 条自己数一遍")
        print()

    for item in problems:
        print(f"[x] {item}")
    for item in warnings:
        print(f"[!] {item}")

    if not problems and not warnings:
        print("[ok] 结构完整，未发现占位符 / 密钥 / 空泛下一步")
    elif not problems:
        print(f"\n通过（{len(warnings)} 条提醒）")
    else:
        print(f"\n不通过：{len(problems)} 个问题，{len(warnings)} 条提醒")

    return 1 if problems else 0


def cmd_log(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    doc = resolve_doc(args.doc, root)
    if doc is not None:
        root = root_of_doc(doc, root)

    branch = git_branch(root)
    created = False
    switched = None

    if doc is None:
        doc, _ = create_doc(root, args.slug)
        created = True
    else:
        doc_branch = header_branch(doc.read_text(encoding="utf-8"))
        if branch and doc_branch and doc_branch not in ("无（非 git 仓库）", "无") and doc_branch != branch:
            safe_branch = re.sub(r"[^A-Za-z0-9_-]+", "-", branch).strip("-")
            switched = (doc_branch, doc)
            doc, _ = create_doc(root, f"{args.slug}-{safe_branch}")
            created = True

    snap = snapshot(doc)
    text = doc.read_text(encoding="utf-8")

    entry_id = uuid.uuid4().hex[:6]
    now = datetime.now()
    line = f"- `{entry_id}` {now:%Y-%m-%d %H:%M} · {args.event.strip()}"
    if args.files:
        # 多个文件必须各自成段。整串包一个反引号会因含空格被判成「不像路径」而静默跳过，
        # 结果是这些文件永远不参与 --stale 事实核对，改名/删除都不会被提示。
        parts = [p.strip() for p in re.split(r"[,，、]", args.files) if p.strip()]
        line += " · " + "、".join(f"`{p}`" for p in parts)
    if args.verify:
        line += f" · 验证：{args.verify.strip()}"

    doc.write_text(append_entry(text, line), encoding="utf-8")

    if switched:
        print(f"检测到分支切换：{switched[0]} → {branch}")
        print(f"已另建文档记录，原文档保持不变：{switched[1]}")
    print(f"已记录：{entry_id}")
    print(f"文档：{doc}{'（新建，骨架待填）' if created else ''}")
    print(f"分支：{branch or '无（非 git 仓库）'}")
    print(f"快照：{snap}")
    print(f"撤销：python handoff.py undo --id {entry_id}")
    if not args.verify:
        print(
            "[!] 未提供 --verify：这条条目没有验证方式，等于假账，下个会话无法核对。"
            "standards.md 3.1 要求「验证方式」必填。"
        )
    return 0


def cmd_journal(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    doc = resolve_doc(args.doc, root)
    if not doc:
        print("找不到交接文档", file=sys.stderr)
        return 1
    text = doc.read_text(encoding="utf-8")
    entries = ENTRY_RE.findall(text)
    print(f"文档：{doc}")
    if not entries:
        print("暂无自动记录的进展条目")
        return 0
    print(f"共 {len(entries)} 条（越靠后越新）：\n")
    for m in ENTRY_RE.finditer(text):
        print(m.group(0)[2:])
    print("\n撤销某条：python handoff.py undo --id <ID>")
    return 0


def cmd_undo(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    doc = resolve_doc(args.file, root)
    if not doc:
        print("找不到交接文档", file=sys.stderr)
        return 1

    text = doc.read_text(encoding="utf-8")
    matches = list(ENTRY_RE.finditer(text))
    if not matches:
        print("文档里没有可撤销的进展条目", file=sys.stderr)
        return 1

    if args.id:
        target = next((m for m in matches if m.group(1) == args.id), None)
        if not target:
            ids = "、".join(m.group(1) for m in matches)
            print(f"找不到 ID {args.id}。可用：{ids}", file=sys.stderr)
            return 1
    else:
        target = matches[-1]

    entry_id = target.group(1)
    snapshot(doc)  # 撤销前也备份，这样 restore 能回退「撤错」的动作
    start, end = target.span()
    if end < len(text) and text[end] == "\n":
        end += 1
    new_text = drop_empty_archive(text[:start] + text[end:])

    doc.write_text(new_text, encoding="utf-8")
    print(f"已撤销：{entry_id}")
    print(f"文档：{doc}")
    print(f"若整体回滚到最近一次写入前：python handoff.py restore")
    return 0


def cmd_restore(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    doc = resolve_doc(args.file, root)
    if not doc:
        print("找不到交接文档", file=sys.stderr)
        return 1
    snap = latest_snapshot(doc)
    if not snap:
        print(f"没有快照：{doc.parent / SNAPSHOT_DIR}", file=sys.stderr)
        return 1
    shutil.copy2(snap, doc)
    print(f"已回滚到：{snap.name}")
    print(f"文档：{doc}")
    return 0


def cmd_summarize(args) -> int:
    root = Path(args.root).resolve() if args.root else find_root(Path.cwd())
    doc = resolve_doc(args.doc, root)
    if not doc:
        print("找不到交接文档", file=sys.stderr)
        return 1

    text = doc.read_text(encoding="utf-8")
    bounds = section_bounds(text, TIMELINE_HEADING)
    if not bounds:
        print("文档里没有「进展时间线」章节，无需归档")
        return 0
    t_start, t_end = bounds
    scope = text[t_start:t_end]
    matches = list(ENTRY_RE.finditer(scope))
    if not matches:
        print("时间线里没有条目")
        return 0

    groups = {}
    for m in matches:
        line = m.group(0)[2:].strip()
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        groups.setdefault(dm.group(1) if dm else "未知日期", []).append(line)

    total = sum(len(v) for v in groups.values())
    print(f"文档：{doc}")
    print(f"共 {total} 条，分布在 {len(groups)} 天：\n")
    for day in sorted(groups):
        print(f"{day}（{len(groups[day])} 条）")
        for line in groups[day]:
            print(f"  {line}")
        print()

    if not args.apply:
        print("以上仅预览。加 --apply 把这批条目移入归档区，时间线只留活跃条目。")
        print("注意：脚本只做搬运和分组，第 2 节「阶段结论」需要你自己压缩成 3–5 条。")
        return 0

    snap = snapshot(doc)
    entries_text = "\n".join(m.group(0) for m in matches)
    # 只从时间线区摘除条目：正文里长得像条目的行保持原样，不破坏语义位置
    new_scope = re.sub(r"\n{3,}", "\n\n", ENTRY_RE.sub("", scope))
    rest = text[:t_start] + new_scope + text[t_end:]
    rest = append_to_section(rest, ARCHIVE_HEADING, entries_text)
    doc.write_text(rest, encoding="utf-8")

    print(f"已归档 {total} 条 → 「{ARCHIVE_HEADING}」")
    print(f"快照：{snap}")
    print("时间线已清空，请把要点压缩进第 2 节「阶段结论」。")
    return 0


def main() -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(description="交接文档工具")
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="创建交接文档骨架")
    p_new.add_argument("--slug", default="session", help="英文短主题，如 user-export")
    p_new.add_argument("--inherit", action="store_true", help="继承上一份的目标 / 技术栈 / 约束红线")
    p_new.add_argument("--root", help="项目根目录，默认自动探测")
    p_new.set_defaults(func=cmd_new)

    p_latest = sub.add_parser("latest", help="打印最新一份交接文档路径")
    p_latest.add_argument("--root", help="项目根目录，默认自动探测")
    p_latest.set_defaults(func=cmd_latest)

    p_check = sub.add_parser("check", help="校验交接文档")
    p_check.add_argument("file", nargs="?", help="目标文件，默认取最新一份")
    p_check.add_argument("--stale", action="store_true", help="额外核对事实：文中路径是否还在、文档写完后是否被改过")
    p_check.add_argument("--root", help="项目根目录，默认自动探测")
    p_check.set_defaults(func=cmd_check)

    p_log = sub.add_parser("log", help="追加一条进展到时间线（写前自动快照）")
    p_log.add_argument("--event", required=True, help="进展描述，一句话")
    p_log.add_argument("--files", help="涉及文件，多个用逗号分隔")
    p_log.add_argument("--verify", help="怎么验证的，例：Excel 打开中文正常")
    p_log.add_argument("--slug", default="auto", help="无既有文档时新建用的主题名")
    p_log.add_argument("--doc", help="目标文档，默认取最新一份")
    p_log.add_argument("--root", help="项目根目录，默认自动探测")
    p_log.set_defaults(func=cmd_log)

    p_journal = sub.add_parser("journal", help="列出所有进展条目")
    p_journal.add_argument("--doc", help="目标文档，默认取最新一份")
    p_journal.add_argument("--root", help="项目根目录，默认自动探测")
    p_journal.set_defaults(func=cmd_journal)

    p_undo = sub.add_parser("undo", help="撤销一条进展")
    p_undo.add_argument("--id", help="短 ID，省略则撤销最后一条")
    p_undo.add_argument("file", nargs="?", help="目标文件，默认取最新一份")
    p_undo.add_argument("--root", help="项目根目录，默认自动探测")
    p_undo.set_defaults(func=cmd_undo)

    p_restore = sub.add_parser("restore", help="整体回滚到最近一次 log 之前的快照")
    p_restore.add_argument("file", nargs="?", help="目标文件，默认取最新一份")
    p_restore.add_argument("--root", help="项目根目录，默认自动探测")
    p_restore.set_defaults(func=cmd_restore)

    p_sum = sub.add_parser("summarize", help="按日期汇总时间线，可选归档")
    p_sum.add_argument("--apply", action="store_true", help="把条目移入归档区，时间线只留活跃条目")
    p_sum.add_argument("--doc", help="目标文档，默认取最新一份")
    p_sum.add_argument("--root", help="项目根目录，默认自动探测")
    p_sum.set_defaults(func=cmd_summarize)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

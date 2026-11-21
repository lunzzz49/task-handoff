#!/usr/bin/env python3
"""通用事件入口：把「记进展」从靠自觉变成事件触发。任何 agent 都能接。

契约只有一条：事件发生时执行一条命令，把事件写进 stdin，读它的 stdout。
stdout 为空 = 什么也不做；有内容 = 交给模型作为上下文。

  python hook_entry.py prompt-submit              # 用户提交输入后
  python hook_entry.py post-tool                  # 命令执行完后
  python hook_entry.py self-test                  # 接入前自检，不写任何文件

输入可以是 JSON（字段名见 references/integration.md 的别名表），
也可以是裸文本：不是 JSON 就整段当作用户输入，`echo "收工了" | ...` 就能跑。

输出格式：
  --format claude   默认，Claude Code 的 hookSpecificOutput
  --format json     {"action": "context", "event": "...", "text": "..."}
  --format plain    纯文本一行，自己拼到 system / user 消息里

四条硬约束，都是为了不打扰：

  1. 项目里没有 .handoff/ 就静默退出，绝不凭空建骨架
  2. 同一条条目 10 分钟内不重复记
  3. 任何异常都 exit 0 —— 入口崩了不能挡住用户干活
  4. 没有命中时 stdout 一个字节都不输出

只记「测试通过」这类确定性事实。某件事算不算突破（4.1）、算不算假账（4.2），
需要语义判断，仍然归 AI，这里不越界。
"""

import importlib.util
import io
import json
import re
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "handoff_tool", Path(__file__).resolve().parent / "handoff.py"
)
handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(handoff)

# 收尾信号。命中任意一个才注入提醒，正常对话一个字都不多说。
WRAP_UP_WORDS = (
    "收工", "先这样", "今天就到", "换个窗口", "换窗口",
    "交接", "handoff", "总结一下", "上下文太长",
)
WRAP_UP_RE = re.compile("|".join(re.escape(w) for w in WRAP_UP_WORDS), re.I)

# 只认这些测试命令。「npm run dev」这类常驻命令不能算。
# 不锚定行首：venv 里常写成 `.venv/Scripts/python -m pytest`，前面还挂着解释器路径。
TEST_CMD_RE = re.compile(
    r"\b(?:pytest|py\.test|"
    r"(?:python[0-9.]*|py)\s+-m\s+pytest|"
    r"npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+test|"
    r"go\s+test|cargo\s+test|mvn\s+(?:-\S+\s+)*test|"
    r"gradlew?\s+test|dotnet\s+test|make\s+test|ctest)\b",
    re.I,
)
# 监听模式永远「正在通过」，记下来就是假账。
WATCH_RE = re.compile(r"--watch\b|--watchAll|--watch-only|\s-w\b|--loop", re.I)

FAIL_RE = re.compile(
    r"\bFAILED\b|\bFAIL\b|Traceback \(most recent call last\)|"
    r"BUILD FAILURE|\berror TS\d+|"
    r"\b[1-9]\d*\s+(?:failed|errors?)\b",
)
PASS_RE = re.compile(
    r"\b\d+\s+passed\b|\bAll tests passed\b|\bBUILD SUCCESS\b|"
    r"Tests run:.*Failures: 0|^\s*ok\s+\S+",
    re.I | re.M,
)

DEDUP_MINUTES = 10
FORMATS = ("claude", "json", "plain")

# 字段别名。接入方的 payload 长什么样不由我们决定，能认的都认。
PROMPT_PATHS = (
    ("prompt",), ("message",), ("text",), ("user_input",),
    ("input",), ("content",), ("query",),
)
COMMAND_PATHS = (
    ("tool_input", "command"), ("command",), ("cmd",),
    ("input", "command"), ("arguments", "command"),
)
STDOUT_PATHS = (
    ("tool_response", "stdout"), ("stdout",), ("output",), ("result",), ("response",),
)
STDERR_PATHS = (("tool_response", "stderr"), ("stderr",))
EXIT_PATHS = (
    ("exit_code",), ("returncode",), ("tool_response", "exit_code"), ("code",),
)
CWD_PATHS = (("cwd",), ("working_dir",), ("workdir",), ("project_root",), ("root",))
TOOL_PATHS = (("tool_name",), ("tool",))


def setup_io():
    """三个流都钉成 UTF-8。

    Windows CI 的管道默认走 cp1252，中文从 stdin 读进来就成乱码，关键词匹配不上，
    而且异常会被 main 的兜底吞掉，表现成「静默不响应」。本地控制台多是 UTF-8，
    这个问题只在 CI 上出现，不能靠环境碰运气。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def get_path(payload, path):
    cur = payload
    for part in path:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def first_str(payload, paths) -> str:
    for path in paths:
        value = get_path(payload, path)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def read_event():
    """读 stdin。JSON 就按字段取；不是 JSON 就整段当作 prompt。绝不抛。"""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {"prompt": raw}
    if isinstance(data, str):
        return {"prompt": data}
    return data if isinstance(data, dict) else {}


def emit(event_name, text, fmt="claude"):
    """把一段上下文交还给客户端。fmt 决定用哪种壳。"""
    if not text:
        return
    if fmt == "plain":
        print(text)
        return
    if fmt == "json":
        print(json.dumps(
            {"action": "context", "event": event_name, "text": text},
            ensure_ascii=False,
        ))
        return
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}},
        ensure_ascii=False,
    ))


def latest_doc(root: Path):
    """项目里已有的最新一份交接文档；没有就返回 None（不创建）。"""
    folder = root / handoff.HANDOFF_DIR
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("handoff-*.md"))
    return files[-1] if files else None


def recently_logged(text: str, event: str, minutes: int = DEDUP_MINUTES) -> bool:
    """时间线里最近 N 分钟内是否已有同一条事件。

    只比较事件正文，不比较 ID —— 同一份文档里 ID 必然不同。
    解析失败一律当作「没记过」，宁可多记一条，也不要因为格式变动而漏记。
    """
    now = datetime.now()
    for line in text.splitlines():
        if not handoff.ENTRY_RE.match(line):
            continue
        head, _, rest = line[2:].partition(" · ")
        try:
            ts = datetime.strptime(head[-16:], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if now - ts > timedelta(minutes=minutes):
            continue
        if rest == event or rest.startswith(event + " ·"):
            return True
    return False


def record(root: Path, event: str, verify: str) -> str:
    """调 handoff.py 的 log 写入，返回条目 ID（拿不到就返回空串）。"""
    ns = Namespace(event=event, files=None, verify=verify, slug="auto", doc=None, root=str(root))
    buf = io.StringIO()
    with redirect_stdout(buf):
        handoff.cmd_log(ns)
    m = re.search(r"已记录：([0-9a-f]{6})", buf.getvalue())
    return m.group(1) if m else ""


def is_wrap_up(prompt: str) -> bool:
    return bool(prompt) and bool(WRAP_UP_RE.search(prompt))


def judge_test_run(command: str, output: str, exit_code=None) -> str:
    """返回空串表示该记；否则返回不记的理由。自检和正式路径共用同一套判定。"""
    if not command:
        return "没有命令"
    if not TEST_CMD_RE.search(command):
        return "不是测试命令"
    if WATCH_RE.search(command):
        return "监听模式，没有确定的终态"
    if isinstance(exit_code, int) and exit_code != 0:
        return "退出码非 0"
    if FAIL_RE.search(output):
        return "输出里有失败标记"
    if not PASS_RE.search(output):
        return "输出里没有通过标记"
    return ""


def mode_prompt_submit(payload, fmt) -> int:
    prompt = first_str(payload, PROMPT_PATHS)
    if not is_wrap_up(prompt):
        return 0
    emit(
        "UserPromptSubmit",
        "检测到收尾信号。按 SKILL.md 4.6 自查：回看本轮有无「已完成并验证、"
        "但时间线里没有条目」的动作，列成具体候选问用户（例：① CSV 导出跑通 "
        "② 修好中文文件名下载）。默认不要自动补记，等用户确认。",
        fmt,
    )
    return 0


def mode_post_tool(payload, fmt) -> int:
    tool = first_str(payload, TOOL_PATHS).lower()
    # 有的 agent 不报工具名，放行；报了但不是执行类命令的，直接跳过。
    if tool and not any(k in tool for k in ("bash", "shell", "exec", "command", "terminal")):
        return 0

    command = first_str(payload, COMMAND_PATHS)
    output = "{}\n{}".format(
        first_str(payload, STDOUT_PATHS), first_str(payload, STDERR_PATHS)
    )
    exit_code = get_path(payload, EXIT_PATHS[0])
    for path in EXIT_PATHS[1:]:
        if exit_code is None:
            exit_code = get_path(payload, path)

    if judge_test_run(command, output, exit_code):
        return 0

    cwd = first_str(payload, CWD_PATHS)
    root = handoff.find_root(Path(cwd) if cwd else Path.cwd())
    doc = latest_doc(root)
    if doc is None:
        return 0

    short = command.strip().splitlines()[0][:80]
    event = "{} 执行通过".format(short)
    if recently_logged(doc.read_text(encoding="utf-8"), event):
        return 0

    entry_id = record(root, event, "命令执行完成，输出无失败标记")
    if entry_id:
        emit(
            "PostToolUse",
            "已自动记一条进展 {}：{}。撤销：python handoff.py undo --id {}".format(
                entry_id, event, entry_id
            ),
            fmt,
        )
    return 0


def mode_self_test(fmt) -> int:
    """接入前自检：只跑判定，不读写项目文件。"""
    print("task-handoff 事件入口自检")
    failures = []

    print("\n[1] 收尾识别")
    cases = [
        ("收工了，明天继续", True),
        ("今天就到这吧", True),
        ("换个窗口接着做", True),
        ("把导出改成 xlsx", False),
        ("这个函数为什么报错", False),
    ]
    for text, expect in cases:
        got = is_wrap_up(text)
        mark = "ok" if got == expect else "FAIL"
        if got != expect:
            failures.append(text)
        print("  [{}] {}  {}".format(mark, "命中" if got else "不中", text))

    print("\n[2] 测试命令判定")
    runs = [
        ("pytest -q", "3 passed in 0.1s", None, True),
        ("pytest -q", "1 failed, 3 passed", None, False),
        ("pytest -q", "3 passed, 0 failed", None, True),
        (r".venv\Scripts\python.exe -m pytest tests", "5 passed", None, True),
        ("npm test -- --watch", "12 passed", None, False),
        ("pytest -q", "3 passed", 1, False),
        ("ls -la", "3 passed", None, False),
    ]
    for cmd, out, code, expect in runs:
        reason = judge_test_run(cmd, out, code)
        got = not reason
        mark = "ok" if got == expect else "FAIL"
        if got != expect:
            failures.append(cmd)
        print("  [{}] {}  {}".format(mark, "该记" if got else "不记：" + reason, cmd))

    print("\n[3] 输出格式")
    for name in FORMATS:
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            emit("PostToolUse", "示例", name)
        finally:
            sys.stdout = old
        line = buf.getvalue().strip()
        ok = bool(line)
        if name in ("json", "claude"):
            try:
                json.loads(line)
            except Exception:
                ok = False
        if not ok:
            failures.append(name)
        print("  [{}] {}".format("ok" if ok else "FAIL", name))

    print("\n静默检查：没有命中时必须零输出。")
    if failures:
        print("不通过：{} 项".format(len(failures)))
        return 1
    print("全部通过。可以接入：把 prompt-submit / post-tool 挂到对应事件上。")
    return 0


def parse_format(argv):
    fmt = "claude"
    if "--format" in argv:
        i = argv.index("--format")
        if i + 1 < len(argv):
            fmt = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    return (fmt if fmt in FORMATS else "claude"), argv


def main(argv=None) -> int:
    setup_io()
    handoff.setup_stdout()
    argv = sys.argv[1:] if argv is None else argv
    try:
        fmt, argv = parse_format(argv)
        mode = argv[0] if argv else ""
        if mode == "self-test":
            return mode_self_test(fmt)
        if mode == "prompt-submit":
            return mode_prompt_submit(read_event(), fmt)
        if mode == "post-tool":
            return mode_post_tool(read_event(), fmt)
        # 参数不认识时必须静默成功：UserPromptSubmit 的 exit 2 会阻断用户输入，
        # 配置写错不能变成「每句话都发不出去」。
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""把 hook_entry.py 装进 Claude Code 的 settings.json。

这只是 Claude Code 的适配器。其它客户端不需要等适配——事件入口本身是通用的，
接入方式见 references/integration.md。

  python install_hooks.py                    # 装到用户级 ~/.claude/settings.json
  python install_hooks.py --scope project    # 装到当前目录 .claude/settings.json
  python install_hooks.py --dry-run          # 只看要写什么，不落盘
  python install_hooks.py --uninstall        # 卸掉，只删自己的条目

幂等：重复运行不会叠出第二份。别人写的 hook 原样保留。
写盘前会把原文件备份成 settings.json.bak；JSON 解析失败时直接退出，绝不覆盖。
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTRY = HERE / "hook_entry.py"
MARKER = "hook_entry.py"


def setup_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def settings_path(scope: str, explicit) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if scope == "project":
        return (Path.cwd() / ".claude" / "settings.json").resolve()
    return (Path.home() / ".claude" / "settings.json").resolve()


def command_for(mode: str) -> str:
    # 用解释器绝对路径：用户的 PATH 里未必有 python，尤其 Windows。
    return '"{}" "{}" {}'.format(sys.executable, ENTRY, mode)


def our_groups():
    return {
        "UserPromptSubmit": [{
            "hooks": [{"type": "command", "command": command_for("prompt-submit")}],
        }],
        "PostToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": command_for("post-tool")}],
        }],
    }


def is_ours(group) -> bool:
    handlers = group.get("hooks") if isinstance(group, dict) else None
    if not isinstance(handlers, list):
        return False
    return any(MARKER in str(h.get("command", "")) for h in handlers if isinstance(h, dict))


def install(settings: dict):
    hooks = settings.setdefault("hooks", {})
    added = []
    for event, groups in our_groups().items():
        current = hooks.setdefault(event, [])
        if any(is_ours(g) for g in current):
            continue
        current.extend(groups)
        added.append(event)
    return added


def uninstall(settings: dict):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    removed = []
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not is_ours(g)]
        if len(kept) != len(groups):
            removed.append(event)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    return removed


def load(path: Path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print("设置文件不是合法 JSON，已停止，未做任何改动：{}".format(path), file=sys.stderr)
        print("  {}".format(exc), file=sys.stderr)
        print("  请先修好这份文件，或换一个 --settings 路径。", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print("设置文件顶层不是对象，已停止：{}".format(path), file=sys.stderr)
        return None
    return data


def main(argv=None) -> int:
    setup_stdout()
    parser = argparse.ArgumentParser(description="安装 / 卸载 task-handoff 的客户端 hook")
    parser.add_argument("--scope", choices=("user", "project"), default="user",
                        help="user 写 ~/.claude/settings.json；project 写 ./.claude/settings.json")
    parser.add_argument("--settings", help="直接指定 settings.json 路径（优先于 --scope）")
    parser.add_argument("--uninstall", action="store_true", help="删除本工具写入的 hook")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容，不落盘")
    args = parser.parse_args(argv)

    if not ENTRY.exists():
        print("找不到 hook_entry.py：{}".format(ENTRY), file=sys.stderr)
        return 1

    path = settings_path(args.scope, args.settings)
    settings = load(path)
    if settings is None:
        return 1

    changed = uninstall(settings) if args.uninstall else install(settings)
    action = "卸载" if args.uninstall else "安装"

    if not changed:
        print("{}：无需改动（当前配置里没有可{}的条目）".format(path, action))
        return 0

    if args.dry_run:
        print("{}（试运行，未落盘）：{}".format(path, "、".join(changed)))
        print(json.dumps(settings, ensure_ascii=False, indent=2))
        return 0

    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("已{}：{} 上的 {}".format(action, path, "、".join(changed)))
    if args.uninstall:
        print("本文件其它 hook 未动；要彻底删除 task-handoff 请自行移除 skill 目录。")
    else:
        print("生效方式：重开一个 Claude Code 会话。")
        print("验证：说一句「收工」应看到自查提醒；跑一次会通过的测试应多出一条进展。")
        print("按触发条件看：收尾词命中才说话，测试通过才记录，其余时候完全静默。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

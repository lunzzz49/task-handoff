# 接入任何 agent

这个 skill 不绑定客户端。它分成两层，可以只接第一层，也可以两层都接。

| 层 | 依赖什么 | 接入成本 |
|---|---|---|
| 能力层：写、读、校验、记录交接 | agent 能读 `SKILL.md`、能执行 Python 命令 | 零适配 |
| 事件层：收尾时自动提醒、测试通过自动记录 | agent 能在事件上执行一条命令、读 stdout | 一个 `if` |

**只接能力层就已经完整可用**。事件层是可选增强，接不接都不影响交接本身。

---

## 第一层：能力（所有 agent）

两件事做到就能用：

1. **让 agent 能读到 `SKILL.md`**。注入系统提示、放进可检索的上下文、或给它一个「读这个文件」的入口，都算。
2. **让 agent 能执行 `python <skill目录>/scripts/handoff.py`**。需要 Python 3.9+，零第三方依赖。

注册信息直接用 `SKILL.md` 的 frontmatter：

```yaml
name: task-handoff
description: 会话交接与阶段总结技能。当用户要把一个阶段的工作压缩成交接文档…
```

`description` 里的触发词是给模型看的，不是给正则用的。各客户端如果有自己的注册格式，把这两个字段搬过去即可。

这一层之上，`SKILL.md` 是流程，`references/standards.md` 是判据，`scripts/` 是工具。agent 按流程做事，不需要理解脚本源码。

---

## 第二层：事件（可选，跨客户端）

### 契约只有一条

> 事件发生时执行一条命令，把事件写进 stdin，读它的 stdout。

- **stdout 为空** → 什么也不做
- **stdout 有内容** → 作为额外上下文交给模型
- **退出码恒为 0** → 不用它做控制流，也没有阻断语义

这条契约故意定得很低：所有 agent 都有「执行命令」和「读输出」，所以所有 agent 都能接。

### 两个事件

| 事件 | 命令 | 何时调用 |
|---|---|---|
| 用户输入后、模型处理前 | `python hook_entry.py prompt-submit` | 每轮用户提交输入 |
| 命令执行后 | `python hook_entry.py post-tool` | 每次 shell / 命令类工具返回 |

`prompt-submit` 只在收尾词命中时输出；`post-tool` 只在「测试命令 + 有通过标记 + 无失败标记 + 项目里已有 `.handoff/`」时输出并写一条进展。

### 输入：认别名，也认裸文本

不想拼 JSON 就直接传文本，整段会被当作 prompt：

```bash
echo "今天就到这吧" | python hook_entry.py prompt-submit --format plain
```

传 JSON 时，下列字段名任一存在即可，不必完全照抄：

| 语义 | 认的字段 |
|---|---|
| 用户输入 | `prompt` `message` `text` `user_input` `input` `content` `query` |
| 命令 | `tool_input.command` `command` `cmd` `input.command` `arguments.command` |
| 标准输出 | `tool_response.stdout` `stdout` `output` `result` `response` |
| 标准错误 | `tool_response.stderr` `stderr` |
| 退出码 | `exit_code` `returncode` `tool_response.exit_code` `code` |
| 工作目录 | `cwd` `working_dir` `workdir` `project_root` `root` |
| 工具名 | `tool_name` `tool` |

工具名缺失时放行；有值但不像执行类（不含 `bash` / `shell` / `exec` / `command` / `terminal`）时跳过。

工作目录缺失时用当前目录。项目根按 `.git` 优先、构建文件次之自动探测。

### 输出：三种壳，按客户端选

| `--format` | 输出 | 适合 |
|---|---|---|
| `claude`（默认） | `{"hookSpecificOutput":{"hookEventName":…,"additionalContext":…}}` | Claude Code |
| `json` | `{"action":"context","event":…,"text":…}` | 自建 agent、能解析 JSON 的框架 |
| `plain` | 纯文本一行 | 拼进 system / user 消息的任何地方 |

三种格式在「没有命中」时都是**零输出**。

---

## 自建 agent：最小实现

```python
import json
import subprocess

ENTRY = r"<skill目录>/scripts/hook_entry.py"


def run_hook(mode, payload, fmt="json"):
    proc = subprocess.run(
        ["python", ENTRY, mode, "--format", fmt],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return ""
    data = json.loads(proc.stdout)
    return data.get("text") or data.get("hookSpecificOutput", {}).get("additionalContext", "")


# 每轮：用户输入后、调用模型前
note = run_hook("prompt-submit", {"prompt": user_text, "cwd": project_dir})
if note:
    messages.append({"role": "system", "content": note})

# 每次执行命令后
note = run_hook("post-tool", {
    "tool_name": "bash",
    "command": command,
    "stdout": stdout,
    "stderr": stderr,
    "exit_code": code,
    "cwd": project_dir,
})
if note:
    messages.append({"role": "system", "content": note})
```

两个位置的选择理由：

- 注入到**模型调用之前**，模型才会在同一轮里看到提醒
- 用 `system` 而不是 `user`，避免污染对话历史

如果框架不允许中途插 system 消息，拼到下一次 user 消息前面也可以，效果一致。

---

## 各客户端怎么挂

| 客户端 | 方式 |
|---|---|
| Claude Code | `python scripts/install_hooks.py`，自动写 `settings.json` |
| 自建 agent | 上面的最小实现，两个调用点 |
| 支持 shell hook 的 IDE agent | 按它的配置格式写命令，建议加 `--format plain` |
| WorkBuddy | hook 配置格式未公开。能配命令就配 `--format plain`；不能配时退回第一层，手动流程完整可用 |
| 只能用提示词的场景 | 把 4.5 的自查规则写进系统提示，属软提醒，不保证触发 |

**发现机制无法统一**。各客户端怎么知道有这个 skill、放在哪个目录、要不要 frontmatter，各有一套。这部分只能按客户端自己的规则注册，本文档不假装能覆盖。

**验证状态**：输出字段已对齐 Claude Code 2.1.316（其二进制里 `hookSpecificOutput`、`additionalContext`、`hookEventName` 三个字段均存在），但**没有做真实会话的注入验证**。第一次接上时，请按下一节的四步自己跑一遍——尤其是第 4 步，它才会真正写到盘上。

---

## 接入验收

四步，全部通过才算接好：

```bash
# 1. 判定逻辑本身没问题（不读写项目文件）
python hook_entry.py self-test

# 2. 该说话时说话
echo "今天就到这吧" | python hook_entry.py prompt-submit --format plain

# 3. 不该说话时一个字都没有
echo "把导出改成 xlsx" | python hook_entry.py prompt-submit --format plain

# 4. 在已有 .handoff/ 的项目里跑一次会通过的测试，看时间线是否多一条
```

第 4 步要在项目目录下执行，`self-test` 不覆盖它——真实的写盘路径只能实测。

---

## 边界

- **需要 Python 3.9+**。没有解释器时，第一层的命令可以手抄骨架绕过（`references/handoff-template.md`），事件层不可用。
- **只记确定性事实**。测试通过、退出码为 0 这类；「这个功能算不算做完」仍需模型判断。
- **不是守护进程**。没有常驻进程、没有网络、没有后台轮询，纯粹是一次命令调用。
- **事件层不改变交付物**。它只往时间线追加条目，交接文档的十节结构仍由 `SKILL.md` 的流程决定。

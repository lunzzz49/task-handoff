# 交接：转换器注册机制调研，准备扩展新格式

- 生成时间：2026-11-21 09:53
- 项目：markitdown（D:/Temp/skill-eval/markitdown）
- 分支：main
- 覆盖范围：从通读 README 与贡献规则 → 到摸清转换器注册链路与插件扩展点
- 上一份交接：无
- 状态：调研完成，尚未动代码

## 1. 一句话目标

把各类文件（Office、PDF、图片、音频、HTML、EPUB 等）转成 LLM 友好的 Markdown。仓库只提供库 + CLI + MCP server，**不做上层应用**——这一点写在 README 的 Contributing 里，是硬边界。

## 2. 阶段结论

- **理清 monorepo 四个包的职责**：`markitdown`（核心库与 CLI）、`markitdown-mcp`（MCP server）、`markitdown-ocr`（OCR 扩展）、`markitdown-sample-plugin`（第三方插件模板）
- **摸清转换器注册链路**：`ConverterRegistration` 携带 priority，主类内部维护 `_converters` 列表，按优先级排序后逐个试 `accepts()`
- **发现一个容易搞反的细节**：priority 有两条并存的规则（见第 6 节第一条），加转换器时两处都要看
- **确认扩展方式有两条路**：改本仓库加内建转换器，或用插件机制外挂（官方更倾向后者）
- **确认测试组织**：核心包 19 个测试文件（全仓库 31 个，四个包各有独立的 tests 目录），配套 `tests/test_files` 下 42 个测试向量
- **未做**：没安装依赖、没跑测试（本环境缺 hatch 与项目依赖），只做了静态阅读

## 3. 当前状态

**整体**：可读可分析，未在本机运行

**运行态**
- 没有长期服务。`markitdown` 是 CLI + 库；`markitdown-mcp` 是可选 MCP server
- 本机未安装任何包依赖，`import markitdown` 会失败

**代码态**
- 本地是上游 `main` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无
- 无临时文件、无调试残留
- 已知瑕疵：无（代码本身是上游状态，未改动）

## 4. 技术栈与既定契约

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Python >= 3.10, < 3.15（`packages/markitdown/pyproject.toml` 锁定） | 不可动 |
| 框架 | 无 web 框架。核心依赖：beautifulsoup4、requests、markdownify、magika、charset-normalizer、defusedxml、certifi | 谨慎 |
| 非默认选择 | **重能力走可选依赖或独立包**（OCR、音频转写、Azure 服务），核心包刻意保持轻 | 硬红线 |
| 禁区 | 不接受 web 服务 / REST API / 前端 / 桌面应用（README 明确 out of scope）；新格式优先做插件而不是塞进核心 | 硬红线 |
| 对外契约 | `DocumentConverter` 子类必须实现 `accepts()` 与 `convert()`；`ConverterRegistration(converter, priority)` 的排序语义固定 | 改动需同步测试 |
| 分层职责 | 每个 `packages/*` 是独立可发布包，各有自己的 `pyproject.toml`；**仓库根没有 pyproject**，装依赖必须进子包目录 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`、`CODEBUDDY.md`，一层子目录也没有。项目规则全部写在 `README.md` 的 Contributing 段落里（含 CLA、in/out of scope、测试方式、安全建议），**没有常驻约定文件**，新会话不会自动读到——本文件第 6 节已把关键约束摘出来。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 拆成四个独立包而非单包 | 核心保持轻量；OCR、MCP 各自独立演进与发版 | 单包发布（简单，但可选依赖会污染核心） | 推断：仓库根无 `pyproject.toml`，各包独立配置 |
| 转换器用「注册表 + priority」而非 if-else 链 | 新格式只需注册，不动主流程；优先级可覆盖默认行为 | 硬编码分派（直观，但每加格式都改主干） | 代码注释：`_markitdown.py` 第 101 行与第 229 行 |
| 新格式优先走插件机制 | 官方担心核心依赖膨胀，插件可独立发布安装 | 内建所有格式（用户省事，但依赖失控） | README：Extending MarkItDown Without Changing This Repository |
| `accepts()` 先于 `convert()` | 先用类型识别过滤，再决定谁来处理，避免每个转换器都尝试解析 | 直接 try-convert（代码少，但错误信息混乱） | 代码注释：`_base_converter.py` 的类文档字符串 |
| 核心不做应用层 | 官方明确把 web 服务、前端、桌面应用列为 out of scope | 自带 UI（用户门槛低，但职责发散） | README：What to Contribute 的 Out of scope |

## 6. 坑与约束

**踩过的坑**
- **priority 有两条并存规则，极易搞反**：注释写明「数字越小越先试」，同时另一处写明「后注册的优先于先注册的」。加转换器时既要挑对 priority 常量，也要注意注册顺序的影响，不能只改一个
- `accepts()` 返回 True 就**意味着** `convert()` 必须能处理它，且要保证读完之后把 stream 位置复原；这条契约写在基类文档字符串里，不遵守会在多转换器串联时出诡异问题
- monorepo 根目录**没有** `pyproject.toml`，在根目录执行 `pip install -e .` 会直接失败，必须进 `packages/markitdown` 再装
- 测试不是裸 `pytest`：官方要求 `hatch shell` 后用 `hatch test`，直接跑 pytest 可能因环境未激活而缺依赖
- 提交 PR 前有 pre-commit 检查，跳过它等于白跑
- 官方明确 out of scope 的东西（加 web 服务、加前端）不要在新会话里重新提议

**约束与红线**
- 不引入 web 服务、REST API、前端、桌面应用——这是项目定位，不是技术偏好
- 新增格式优先用插件机制，内建新格式要先论证必要性
- 核心包不加重依赖，重能力走可选依赖或独立包
- 涉及 I/O 的调用要按官方安全建议选最窄接口：只需要本地文件就用 `convert_local()`，不要用全功能的 `convert()`

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `packages/markitdown/src/markitdown/_markitdown.py` | 主类：转换器注册、priority 排序、分派 | 只读调研 |
| `packages/markitdown/src/markitdown/_base_converter.py` | `DocumentConverter` 基类与 `DocumentConverterResult`，定义 accepts/convert 契约 | 只读调研 |
| `packages/markitdown/src/markitdown/converters/` | 各格式转换器，一格式一文件 | 只读调研 |
| `packages/markitdown/tests/` | 19 个测试文件 + `tests/test_files` 下 42 个测试向量 | 未运行 |
| `packages/markitdown-sample-plugin/` | 第三方插件模板，新格式的参照实现 | 只读调研 |
| `packages/markitdown/pyproject.toml` | 核心包依赖与 Python 版本约束 | 只读 |
| `README.md` | 用法、插件、Azure 集成、Contributing 与 in/out of scope | 只读，**必读 Contributing 全节**（含 CLA 签署要求）与 Plugins 小节 |
| `SECURITY.md` | 漏洞报告方式与输入可信边界 | 只读 |

## 8. 验证方法

**启动**
- `cd packages/markitdown`
- `pip install hatch` 后 `hatch shell`，再 `hatch test`
- 若用 Devcontainer，依赖已预装，直接 `hatch test`

**确认成功**
- 测试全绿（核心包 19 个测试文件覆盖各格式）
- `pre-commit run --all-files` 无报错

**上次验证结果**
- **未验证**。本环境只装了裸 Python，没有 hatch 也没有项目依赖，本轮只做了静态代码阅读。接手后请先自己跑一遍 `hatch test` 再相信本文件的任何运行结论。

## 9. 下一步

**优先级**
1. 决定新格式走插件还是内建——官方倾向插件，先按插件做能省掉核心依赖评审
2. 照 `markitdown-sample-plugin` 实现 `accepts()` 与 `convert()`
3. 补测试向量并跑通 `hatch test`

**第一步动作**
> 先读 `packages/markitdown-sample-plugin/src/markitdown_sample_plugin/_plugin.py`，照它实现 `accepts()` / `convert()` 两个方法；再打开 `packages/markitdown/src/markitdown/_markitdown.py`，看 `register_converter()` 的调用区（约 230 行起）确认该给什么 priority——注意那里同时有「数字小优先」和「后注册优先」两条规则。

**待确认**
- 新格式是否值得进核心？如果它会引入新依赖，按官方口径应做成插件
- 插件要不要发布到 PyPI 并打 `#markitdown-plugin` 标签（官方推荐做法）

## 10. 接手方式

新窗口开场直接粘贴：

```
读 D:/Temp/skill-eval/markitdown/.handoff/handoff-2026-11-21-095341-converter-research.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
沿用项目现有技术栈，不要更换语言/框架，不要新增依赖；新增格式优先按插件做，不要加进核心包。
```

建议下一个会话调用的技能：无

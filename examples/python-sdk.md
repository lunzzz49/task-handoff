# 交接：摸清文档-测试联动机制，准备提第一个 PR

- 生成时间：2026-11-21 10:17
- 项目：python-sdk（D:/Temp/skill-eval/python-sdk）
- 分支：main
- 覆盖范围：从通读 AGENTS.md 与 CONTRIBUTING → 到搞清 docs_src 与 docs 的联动、确认提 PR 的前置门槛
- 上一份交接：无
- 状态：调研完成，未动代码

## 1. 一句话目标

Model Context Protocol 的官方 Python SDK，提供 server 与 client 两侧实现。`main` 是已发布的 v2 线，`v1.x` 是上一大版本的维护分支——两条线并行，改动落在哪条线取决于它是新功能还是关键修复。

## 2. 阶段结论

- **读完 AGENTS.md**（166 行）与 CONTRIBUTING（192 行），确认这个项目有 12 类硬约束：包管理、分支模型、代码质量、测试、覆盖率、文档、格式、异常处理
- **搞清 docs_src 的机制**：`docs/*.md` 里的示例不是手写的，而是用 `--8<--` 从 `docs_src/<chapter>/tutorialNNN.py` 引入；`tests/docs_src/` 导入同一批模块并跑通。**文档里读到的代码，就是 CI 跑的那份**
- **确认 mcp 与 mcp-types 的 lockstep 发布**：`mcp` 的依赖里 `mcp-types=={{ version }}` 由构建时注入，两个包永远同版本
- **确认提 PR 的门槛**：未关联到指派给自己的 issue 的 PR 会被自动关闭（AGENTS.md 开头就写了）
- **规模认知**：238 个测试文件对 136 个源文件，覆盖率要求 `fail_under = 100`
- **未做**：没装依赖、没跑测试（本环境缺 uv 与 3.11–3.15 矩阵）

## 3. 当前状态

**整体**：可读可分析，本机未运行

**运行态**
- 无长期服务，纯库
- 本机未安装任何依赖，`import mcp` 会失败
- 项目用 uv 管理，`uv.lock` 在仓库里

**代码态**
- 本地是上游 `main` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 因此**看不到真实分支**：`v1.x` 维护分支是否存在、backport PR 怎么打，只能从远端确认
- 未提交改动：无

## 4. 技术栈与既定契约

**根级有 `AGENTS.md`（`CLAUDE.md` 只是 `@AGENTS.md` 的引用），它会被客户端自动加载，所以本节只写它没覆盖或容易被忽略的部分，不重复它的内容。**

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Python >= 3.11，CI 矩阵覆盖 3.11–3.15（`pyproject.toml` 锁定） | 不可动 |
| 包管理 | **只用 uv，禁止 pip**。root 项目依赖是 dynamic 的，加依赖要手改 `pyproject.toml` 再 `uv lock` | 硬红线，详见 AGENTS.md |
| 非默认选择 | `mcp` 与 `mcp-types` 严格同版本发布，不是独立依赖 | 硬红线 |
| 禁区 | 不许改已发布 v2 公共 API 的签名或可观察行为；不许用 `except Exception:`（顶层处理器除外） | 硬红线 |
| 对外契约 | `src/mcp/__init__.py` 的 `__all__`（约 70 个符号）就是公共 API 门面，往里加符号是一次 API 决策 | 改动需评估兼容性 |
| 分层职责 | `src/mcp/` 是主包，`src/mcp-types/` 是 wire-types 包，两个独立可发布包 | 保持现状 |

**红线出处**：`AGENTS.md`（项目根，常驻，新会话自动加载）。它引用的 `.claude/skills/test-quality/SKILL.md` 也真实存在，是测试写法的细则。**本文件不重复这些规则**，只在第 6 节补充 AGENTS.md 没有展开的机制。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| v2 公共 API 是兼容契约，删除或改签名要维护者显式决定 | 已发布给大量下游使用者，破坏性改动代价高 | 自由演进 API（迭代快，但下游会炸） | `AGENTS.md`：Branching Model |
| `mcp` 与 `mcp-types` 严格同版本发布 | wire types 是 SDK 的另一半，版本错配会导致协议层不一致 | 独立版本（灵活，但要做兼容矩阵） | `DEPENDENCY_POLICY.md` |
| 依赖只设 `>=` 下限，不为 CVE 单独抬下限 | 下限越高装得进的环境越少；漏洞该在上游和 lockfile 里修 | 为安全公告抬下限（看起来负责，实际缩小兼容面） | `DEPENDENCY_POLICY.md` |
| 文档示例必须放在 `docs_src/` 且能被测试导入 | 让文档示例不可能过期——读到的就是 CI 跑的那份 | 在 md 里内联代码块（好写，但会烂掉） | `docs_src/__init__.py` 模块文档 |
| 测试不用 `Test` 前缀类，只用顶层 `test_*` 函数 | 减少嵌套与隐式共享状态，anyio 场景下更清晰 | unittest 风格类（老文件里还有，但不再新增） | `AGENTS.md`：Testing |

## 6. 坑与约束

**踩过的坑**
- **改文档示例不能直接改 `docs/*.md`**：代码块是 `--8<--` 引入的，必须改 `docs_src/<chapter>/tutorialNNN.py`，并保证 `tests/docs_src/` 对应测试能跑通。改 md 里的代码会被下次构建覆盖掉，白改
- **覆盖率 100% 是硬门禁**：`fail_under = 100` 且 `branch = true`。局部跑测试时无法达到 100%（coverage 把 `tests/` 也算进去），要按 AGENTS.md 给的 `--include` + `--fail-under=0` 流程做，别以为是自己改坏了
- **`uv run` 必须带 `--frozen`**：否则 uv 会顺手改写 `uv.lock`，产生无关 diff
- **`mcp-types` 的依赖是模板变量** `mcp-types=={{ version }}`，不是写死的数字；手改会破坏发布流程
- **分支选错等于白做**：新功能进 `main`（v2），只在 `v1.x` 上的关键修复要加 `[v1.x]` 前缀。本地快照看不到分支，动手前先 `git branch -a` 确认
- **PR 不关联 issue 会被自动关闭**：先找 assigned 给自己的 issue，再开 PR

**约束与红线**
- 不许用 pip（包括 `uv pip install`），不许写 `@latest`
- 公共 API 变更必须在同一个 PR 里更新 `docs/` 对应页，且 docs 的组织按 `mkdocs.yml` 的 `nav:` 分节找，不是按目录名
- 新增 `# pragma: no cover` / `# type: ignore` / `# noqa` 要能被合理解释，否则就是缺测试

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `AGENTS.md` | 项目全部硬约束，**必读，全程** | 只读 |
| `CONTRIBUTING.md` | 提 issue/PR 的流程与自动关闭规则，**必读，动手前** | 只读 |
| `DEPENDENCY_POLICY.md` | 依赖下限与 CVE 处理口径 | 只读 |
| `src/mcp/__init__.py` | 公共 API 门面（`__all__`） | 只读 |
| `src/mcp/` | server / client / shared / types 主实现 | 只读调研 |
| `src/mcp-types/` | wire-types 包，与 mcp 同版本发布 | 只读 |
| `docs_src/` | 文档示例的**源码**，`--8<--` 引入到 md，同时被测试跑 | 只读调研 |
| `tests/docs_src/` | 跑 `docs_src` 里示例的测试，保证文档不过期 | 只读 |
| `mkdocs.yml` | 文档导航结构，找页面按它的 `nav:` | 只读 |
| `scripts/test` | 一键跑覆盖率 + strict-no-cover（约 23 秒） | 未运行 |

## 8. 验证方法

**启动**
- 安装依赖用 `uv sync`（不是 pip）
- 全量检查：`./scripts/test`（约 23 秒，跑覆盖率与 strict-no-cover）
- 单测：`uv run --frozen pytest tests/path/test_foo.py`
- 跨版本：`uv run --frozen --python 3.11 pytest ...`（CI 覆盖 3.11–3.15）

**确认成功**
- 覆盖率报告显示 100%，`strict-no-cover` 无告警
- `uv run --frozen ruff format .` / `ruff check .` / `pyright` 全部干净
- pre-commit 全过（含 markdownlint、uv.lock 一致性、README 检查）

**上次验证结果**
- **未验证**。本环境没有 uv 和项目依赖，本轮只做静态阅读。上述命令抄自 `AGENTS.md`，未经实际执行——接手后请先跑一遍 `./scripts/test` 再信本文件。

## 9. 下一步

**优先级**
1. 先去仓库找 assigned 给自己的 issue，没有就先在 issue 里确认方案——PR 不关联 issue 会被自动关闭，这一步不能跳
2. 确认改动该落 `main` 还是 `v1.x`
3. 动手前跑一次 `./scripts/test` 建立基线，否则改完分不清是新引入的问题还是环境问题

**第一步动作**
> 在 `D:/Temp/skill-eval/python-sdk` 下执行 `uv sync` 安装依赖，然后跑 `./scripts/test` 记录基线覆盖率与耗时；同时 `git branch -a` 确认本地能看到哪些分支（当前快照只有一次提交，`v1.x` 是否存在要到远端 @modelcontextprotocol/python-sdk 确认）。

**待确认**
- 目标改动属于新功能还是 v1.x 修复？决定落在哪条分支
- 如果改的是文档示例，是否已经对应改了 `docs_src/` 而不是 `docs/` 里的 md？

## 10. 接手方式

新窗口开场直接粘贴：

```
读 D:/Temp/skill-eval/python-sdk/.handoff/handoff-2026-11-21-101739-docs-test-linkage.md，按第 9 节「第一步动作」继续。
先跑 git status 和文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
沿用项目现有技术栈，不要更换语言/框架，不要新增依赖；只用 uv，不要用 pip。
```

建议下一个会话调用的技能：无

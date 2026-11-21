# 交接：v8 架构调研，理解 Core 与 Legacy 的边界

- 生成时间：2026-11-21 10:39
- 项目：polly（<项目根>）
- 分支：main
- 覆盖范围：从读 AGENTS.md 与解决方案结构 → 到分清 v8 重写与 legacy 包的关系
- 上一份交接：无
- 状态：调研完成，未构建未测试

## 1. 一句话目标

.NET 的弹性（resilience）库：重试、熔断、超时、限流、舱壁等策略的组合执行。v8 是一次彻底重写，但旧 API 仍以独立包形式保留给存量项目。

## 2. 阶段结论

- **v8 是重写，不是增量**：`Polly.Core` 是新的设计核心，根包 `Polly` 是 v8 之前的 legacy API，仅为向后兼容存在
- **8 个源项目**：`Polly.Core`、`Polly`（legacy）、`Polly.Extensions`、`Polly.RateLimiting`、`Polly.Testing`、`LegacySupport`、`Shared`、`Snippets`
- **根级有 `AGENTS.md`**：包含完整构建命令、架构说明、mutation testing 入口，是给 AI agent 的项目说明
- **集中式版本管理**：`Directory.Packages.props`（包版本）、`Directory.Build.props` / `.targets`（共享 MSBuild 配置），不是每个项目各管各的
- **解决方案文件是新格式**：`Polly.slnx`，不是传统 `.sln`
- **有 mutation testing**：`build.ps1` 里有针对各子项目的 mutation 目标，CI 里跑
- **未做**：没构建、没跑测试

## 3. 当前状态

**整体**：可读可分析，未构建

**运行态**
- 纯库，无服务
- 本机有 JDK 但**没有 .NET SDK**，`dotnet` 命令不可用；构建需要先装 .NET SDK

**代码态**
- 本地是上游 `main` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无

## 4. 技术栈与既定契约

**必须自己写**（`AGENTS.md` 之外还要自己判断的部分）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **两套 API 并存**：新代码一律用 `Polly.Core` 的 `ResiliencePipeline`；根包 `Polly` 只做兼容，不要往里加新功能 | 硬红线 |
| 非默认选择 | **集中式依赖管理**：包版本统一写在 `Directory.Packages.props`，不要在单个 `.csproj` 里写版本号 | 保持现状 |
| 禁区 | 不改 legacy 包的行为语义；不在 Core 里引入 legacy 的静态扩展现式 API | 硬红线 |
| 对外契约 | `ResiliencePipeline` / `ResiliencePipelineBuilder` / `ResilienceStrategy` / `ResilienceContext` 四个核心抽象是公开 API 骨架 | 改动需评估兼容性 |

**可省略**（`AGENTS.md` 已覆盖，这里只留索引）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | .NET（`AGENTS.md` 的示例里有 `--framework net10.0`，完整目标框架矩阵见 `Directory.Build.props`） | 不可动 |
| 框架 | 无 web 框架；测试用 xUnit 系（按 `test/` 下项目结构） | 谨慎 |
| 分层职责 | `src/` 放实现（8 个项目），`test/` 放对应测试项目，`Directory.*.props` 管共享配置 | 保持现状 |

**红线出处**：`AGENTS.md`（项目根，常驻，新会话自动加载）。它写清了构建命令、架构分层、mutation testing 入口与 CI 检查项。**本文件不重复它的内容**，只补它没展开的边界判断。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| v8 彻底重写而非增量修补 | 旧 API 的静态扩展方法体系难以扩展新策略 | 在旧 API 上迭代（改动小，但架构债还不掉） | `AGENTS.md`：Architecture 一节 |
| 保留 legacy 包 `Polly` | 存量项目不能强制迁移 | 直接删旧包（干净，但破坏下游） | `AGENTS.md` 同上 |
| 包版本集中管理 | 多项目共享依赖，逐项目写版本会漂移 | 各 `.csproj` 自管（灵活，但版本易不一致） | `Directory.Packages.props` 的存在 |
| 引入 mutation testing | 覆盖率不等于测试有效性，变异测试能发现「测了但没断言到」 | 只看行覆盖率（快，但可能假绿） | `AGENTS.md` 的 MutationTests 目标 |
| 解决方案用 `.slnx` 新格式 | 新格式更简洁、可读 | 传统 `.sln`（工具兼容性更广） | `Polly.slnx` |

## 6. 坑与约束

**踩过的坑**
- **`Polly` 与 `Polly.Core` 是两个世界**：往根包 `Polly` 里加功能是错的，新能力必须落在 `Polly.Core` 或其扩展包
- **本机没有 .NET SDK**：`dotnet build` 直接失败，需先装 SDK 并确认版本能覆盖目标框架
- **不要逐项目写包版本**：版本号统一在 `Directory.Packages.props`，写在 `.csproj` 里会被集中管理覆盖或引发冲突
- **单测要指定项目**：解决方案有多套测试项目，`dotnet test` 全跑很慢，用 `--filter "FullyQualifiedName~XxxTests"` 缩小范围
- **mutation testing 不是常规测试**：它跑得慢，只在需要验证测试有效性时用

**约束与红线**
- 新功能只进 `Polly.Core` 体系，不进 legacy `Polly`
- 依赖版本只改 `Directory.Packages.props`
- 提交前跑 `./build.ps1`（完整流程：clean + restore + build + test）

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `AGENTS.md` | 构建命令、架构分层、mutation 入口、CI 检查，**必读** | 只读 |
| `CONTRIBUTING.md` | 贡献流程与规范 | 只读 |
| `src/Polly.Core/` | v8 核心：`ResiliencePipeline` 与策略抽象 | 只读调研 |
| `src/Polly/` | legacy 包（v8 之前 API），只做兼容 | 只读调研 |
| `src/Polly.Extensions/` | 与依赖注入等宿主集成的扩展 | 只读 |
| `src/Polly.RateLimiting/` | 限流策略实现 | 只读 |
| `src/Polly.Testing/` | 测试辅助（断言策略行为） | 只读 |
| `Directory.Packages.props` | 集中式包版本管理 | 只读 |
| `Directory.Build.props` | 共享 MSBuild 配置（含目标框架） | 只读 |
| `Polly.slnx` | 新格式解决方案文件 | 只读 |

## 8. 验证方法

**启动**
- 先装 .NET SDK（本机当前没有 `dotnet`）
- 完整流程：`./build.ps1`（clean + restore + build + test + package）
- 只构建：`dotnet build`
- 全量测试：`dotnet test`
- 单项目测试：`dotnet test ./test/Polly.Core.Tests/Polly.Core.Tests.csproj`
- 按名字过滤：`dotnet test ./test/Polly.Core.Tests --filter "FullyQualifiedName~CircuitBreakerTests"`

**确认成功**
- `./build.ps1` 全流程以成功结束
- 目标测试项目通过，且确实跑到了测试（注意 `--filter` 写错时可能零匹配而假绿）

**上次验证结果**
- **未验证**。本机无 .NET SDK，本轮只做静态阅读。以上命令来自 `AGENTS.md`，未实际执行。

## 9. 下一步

**优先级**
1. 装 .NET SDK，跑 `dotnet build` 确认能编译（`AGENTS.md` 示例用 net10.0，版本不够会失败）
2. 明确改动属于 Core 还是 legacy —— 这条判断决定后面所有工作
3. 改完跑 `./build.ps1` 走完整流程，别只跑单测

**第一步动作**
> 在 `<项目根>` 下先确认 `dotnet --version` 可用并满足 `Directory.Build.props` 里的目标框架，然后 `dotnet build` 全量编译一次；若目标是加策略，先读 `src/Polly.Core/` 里现有策略的实现与注册方式。

**待确认**
- 这次改动是给 v8（`Polly.Core`）还是维护 legacy？两者不能混
- 是否需要同步更新 `src/Polly.Testing` 的断言辅助？

## 10. 接手方式

新窗口开场直接粘贴：

```
读 .handoff/handoff-2026-11-21-103932-resilience-v8.md，按第 9 节「第一步动作」继续。
先读 AGENTS.md（根级，含构建命令与架构说明）。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
新功能只进 Polly.Core 体系，不要动 legacy 包 Polly；依赖版本只改 Directory.Packages.props。
沿用项目现有技术栈，不要新增依赖。
```

建议下一个会话调用的技能：无

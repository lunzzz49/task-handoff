# 交接：v2 架构与测试机制调研，准备修并发相关问题

- 生成时间：2026-11-21 10:21
- 项目：bubbletea（D:/Temp/skill-eval/bubbletea）
- 分支：main
- 覆盖范围：从通读 README 教程与升级指南 → 到搞清包结构、平台分层、测试机制
- 上一份交接：无
- 状态：调研完成，本机无 Go 工具链，未编译未测试

## 1. 一句话目标

用 Go 写的终端 UI 框架，走 MVU（Model-View-Update）模式：`Init` 起命令、`Update` 处理消息、`View` 渲染。当前主线是 **v2**，v1 的用法与消息类型都变了，迁移清单在 `UPGRADE_GUIDE_V2.md`。

## 2. 阶段结论

- **包结构是扁平的**：123 个 `.go` 文件全在仓库根，**只有一个 package**，按职责分文件（`key.go` / `mouse.go` / `renderer.go` / `tea.go` / `screen.go`…），不是 pkg/xxx 分层
- **module 路径不是 GitHub 地址**：`charm.land/bubbletea/v2`，是 vanity import path。按仓库地址写 import 会编译不过
- **Go 版本要求很高**：`go 1.26.0`，且 `go.mod` 里 `retract v2.0.0-beta1`（撤回过一个 beta）
- **平台差异靠 build tags 双写**：`signals_unix.go` / `signals_windows.go` 这类文件，新式 `//go:build` 与旧式 `// +build` 两行都写
- **测试必须带 race 与重复**：`go test -race -count 4 -cpu 1,4 ./...`（Taskfile 的 `test` 任务），并发问题只能这样暴露
- **渲染输出用 golden 快照比对**：`screen_test.go` 用 `golden.RequireEqual`，快照存在 `testdata/` 下
- **文档形态**：README 是**教程**（面向使用者），加 `UPGRADE_GUIDE_V2.md` 迁移清单与 67 个 `examples/`。**没有 CONTRIBUTING、没有 docs 目录、没有 AGENTS.md**——贡献规则和设计理由都不在文档里
- **未做**：本机没有 Go 工具链，没编译、没跑测试

## 3. 当前状态

**整体**：可读可分析，本机无法构建

**运行态**
- 无服务，是库
- **本机没有 Go**（`go: command not found`），装 Go 1.26+ 之前什么都跑不了

**代码态**
- 本地是上游 `main` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无
- 已知瑕疵：无（代码本身是上游状态）

## 4. 技术栈与既定契约

**必须自己写**（文档里查不到）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **单包扁平结构**，不拆 pkg/；平台差异用文件名后缀 + build tags，不用运行时判断 | 保持现状 |
| 禁区 | v2 的公开 API 已发布，改签名属破坏性变更；不许只改 `_unix.go` 不改 `_windows.go`；不许去掉 `-race` 跑测试 | 硬红线 |
| 对外契约 | import path 为 `charm.land/bubbletea/v2`（不是 GitHub 地址）；`tea.Model` 接口为 `Init() Cmd` / `Update(Msg) (Model, Cmd)` / `View() tea.View`（v2 里 `View` 返回 `tea.View` 而不是 `string`） | 改动需评估 v1→v2 迁移影响 |

**可省略**（能读到，但这里仍写实，因为项目没有别的地方可查）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Go 1.26.0（见 `go.mod`；CI 用 `go-version-file` 跟随它，不另设矩阵） | 不可动 |
| 框架 | 无框架；直接依赖 8 个，均为 charmbracelet 系列加 `golang.org/x/sys` | 谨慎 |
| 分层职责 | 平铺单包：核心在根目录 `.go`，`examples/` 与 `tutorials/` 是各自独立的 Go module（各有 `go.mod`），`testdata/` 存 golden 快照 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md`，也没有 `docs/`。**没有任何常驻约定文件**，以上红线只存在于本文件，新会话不会自动获得——开场 prompt 已内置技术栈约束兜底。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 单包扁平结构，不拆子包 | 库的使用者只 import 一个包，内部拆分对调用方无价值，反而增加跨包循环依赖风险 | pkg/ 分层（结构清晰，但对单库是过度设计） | 推断：123 个文件同属一个 package，未找到说明理由的文档 |
| 平台差异用 build tags 而非运行时分支 | 编译期裁剪，不引入不可能执行到的代码路径 | 运行时 `runtime.GOOS` 判断（简单，但会带进无效分支与额外依赖） | 代码注释：`signals_unix.go` 首行 build tag |
| v2 一次性做完破坏性变更，并给出完整迁移清单 | 集中一次阵痛，比逐版本小步破坏对下游更友好 | 增量演进（平滑，但会长期同时维护两套 API） | `UPGRADE_GUIDE_V2.md` 开头 |
| 测试带 `-race -count 4` | 并发框架的问题只在重复与竞争检测下暴露 | 单次 `go test`（快，但漏掉数据竞争） | `Taskfile.yaml` 的 test 任务 |
| 渲染输出用 golden 快照 | 终端渲染结果无法用断言描述，只能整体比对 | 逐字段断言（脆弱，改一个空格就全红） | 代码：`screen_test.go` 的 `golden.RequireEqual` |

## 6. 坑与约束

**踩过的坑**
- **import 路径踩坑**：module 是 `charm.land/bubbletea/v2`，照 GitHub 地址写 `github.com/charmbracelet/bubbletea` 会编译失败
- **`View()` 已经改签名**：v2 返回 `tea.View` 不是 `string`。照 v1 教程或旧记忆写会直接报类型错误
- **按键消息类型换名**：v1 的 `tea.KeyMsg` 在 v2 是 `tea.KeyPressMsg`，字段也变了（`Type`/`Runes`/`Alt`）；空格键判断从 `case " "` 改成 `case "space"`
- **改平台相关代码必须成对改**：只动 `signals_unix.go` 不动 `signals_windows.go`，CI 的 Windows job 才炸，本地 Linux 完全看不出来
- **改渲染逻辑会让 golden 测试红**：输出有变化就要更新 `testdata/` 里的快照，否则测试失败但代码可能是对的——先确认差异是不是预期的
- **测试不加 `-race` 等于没测并发**：这个库的本质是并发事件循环，数据竞争不靠 race 检测器抓不到

**约束与红线**
- 不改已发布的 v2 公共 API 签名；要改先走 issue 讨论并更新 `UPGRADE_GUIDE_V2.md`
- 平台文件必须成对维护，build tag 两行（新式 + 旧式）都写
- 提交前跑 `golangci-lint run`（Taskfile 的 `lint` 任务）

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `tea.go` | `Program` 主循环：事件读取、消息分发、渲染调度 | 只读调研 |
| `mod.go` | `Model` / `Msg` / `Cmd` 等核心接口定义 | 只读调研 |
| `key.go`、`mouse.go`、`paste.go` | 输入消息类型与解析 | 只读调研 |
| `renderer.go`、`screen.go`、`cursed_renderer.go` | 渲染与屏幕缓冲 | 只读调研 |
| `signals_unix.go` / `signals_windows.go` | 平台相关信号处理，build tags 分离 | 只读调研 |
| `*_test.go`（根目录） | 单元测试，含并发与生命周期测试 | 未运行 |
| `testdata/` | golden 快照，渲染输出比对基准 | 只读 |
| `UPGRADE_GUIDE_V2.md` | v1→v2 迁移清单，**改 API 前必读** | 只读 |
| `Taskfile.yaml` | lint / test / release 命令入口（不是 Makefile） | 只读 |
| `examples/`、`tutorials/` | 各为独立 Go module，演示与教程 | 只读 |

## 8. 验证方法

**启动**
- 先装 Go 1.26+（本机当前没有 Go）
- 编译：`go build ./...`
- 测试：`go test -race -count 4 -cpu 1,4 ./...`（等价于 `task test`）
- 静态检查：`golangci-lint run`（等价于 `task lint`）
- 示例单独验证：进 `examples/` 目录再 `go build ./...`（它是独立 module）

**确认成功**
- `go test` 全绿，且带 `-race` 时无 `DATA RACE` 输出
- golden 测试通过说明渲染输出与快照一致
- `golangci-lint` 无告警

**上次验证结果**
- **未验证**。本机没有 Go 工具链，本轮只做静态阅读。以上命令抄自 `Taskfile.yaml` 与 `go.mod`，未实际执行——接手后先装 Go 再跑一遍。

## 9. 下一步

**优先级**
1. 装 Go 1.26+，跑通 `go test -race ./...` 建立基线——没有这一步，后面改什么都无法验证
2. 确认要修的并发问题复现路径（最好有 issue 或能稳定复现的测试）
3. 按 v2 的消息类型与 `View` 签名写代码，不要照 v1 的记忆

**第一步动作**
> 在 `D:/Temp/skill-eval/bubbletea` 下先装 Go 1.26+（`go version` 要有输出），然后执行 `go test -race -count 1 ./...` 跑一遍基线；若 `tea.go` 的事件循环是问题所在，先读它的 `eventLoop` 与 `renderer` 协作部分再动手。

**待确认**
- 要修的问题是上游已知 issue，还是本地发现的？如果是已知问题，先看有没有维护者给的方案
- 改动是否涉及平台相关代码？涉及就要准备两套实现

## 10. 接手方式

新窗口开场直接粘贴：

```
读 D:/Temp/skill-eval/bubbletea/.handoff/handoff-2026-11-21-102145-concurrency-research.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
注意 import path 是 charm.land/bubbletea/v2，不是 GitHub 地址；v2 的 View() 返回 tea.View 不是 string。
沿用项目现有技术栈，不要新增依赖。
```

建议下一个会话调用的技能：无

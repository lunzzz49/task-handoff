# 交接：构建与测试体系调研，准备加功能

- 生成时间：2026-11-21 10:27
- 项目：bat（<项目根>）
- 分支：master
- 覆盖范围：从读 Cargo.toml 与 CONTRIBUTING → 到搞清 feature 分层、三类测试、CHANGELOG 流程
- 上一份交接：无
- 状态：调研完成，本机无 Rust 工具链，未构建

## 1. 一句话目标

`cat` 的增强版：语法高亮、git 改动标记、自动分页。既是 CLI 工具，也作为库被别的程序嵌入——这两种用法共用一份代码，靠 Cargo feature 分隔。

## 2. 阶段结论

- **Cargo 单 crate，双入口**：`src/lib.rs` 是库，`src/bin/` 是 CLI，两者共用 `src/` 下的模块
- **build script 不在默认位置**：`Cargo.toml` 里写的是 `build = "build/main.rs"`，不是根目录的 `build.rs`。找构建逻辑别去根目录翻
- **feature 分两层**：`default = ["application", "git"]`。`application` 把 CLI 所需的一切（clap、paging、regex 等）拉进来，**把它当库依赖时必须关掉它**，否则下游会被塞一堆 CLI 依赖
- **三类测试**：`tests/integration_tests.rs`（起二进制、断言 stdout/stderr）、`tests/snapshot_tests.rs`（快照比对，基准在 `tests/snapshots/`）、`tests/syntax-tests/`（语法高亮回归，需要先 `cargo build --bins`）
- **CHANGELOG 是硬流程**：行为、语法映射、语法定义、主题、构建/CI 改动都要求加条目
- **MSRV 1.88**，且 `Cargo.toml` 里明写「有理由就可以抬」
- **未做**：本机没有 cargo，没构建、没跑测试

## 3. 当前状态

**整体**：可读可分析，本机无法构建

**运行态**
- 是 CLI + 库，无服务
- **本机没有 Rust 工具链**（`cargo: command not found`），装 Rust 1.88+ 之前什么都跑不了

**代码态**
- 本地是上游 `master` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无
- 已知：`assets/syntaxes/*` 与 `assets/themes/*` 在 `Cargo.toml` 的 `exclude` 里，不进 crate 包

## 4. 技术栈与既定契约

**必须自己写**（文档里查不到，或者只在 Cargo.toml 的注释里）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **一个 crate 同时当库和 CLI**，用 `application` feature 分隔两种用法；build script 放在 `build/main.rs` | 保持现状 |
| 禁区 | 当库被依赖时不得开启 `application` feature；不许为了「方便」把 CLI 依赖塞进默认路径；行为改动不补 CHANGELOG 不合规 | 硬红线 |
| 对外契约 | crate 名 `bat`，库入口 `src/lib.rs`；`assets/syntaxes`、`assets/themes` 是运行时资源，被 `exclude` 排除在 crate 包之外，靠 `build-assets` feature 处理 | 改动需评估打包影响 |

**可省略**（但这里仍写实，因为项目没有一份「给开发者看」的总览）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Rust，MSRV 1.88（`Cargo.toml` 的 `rust-version`），edition 2021 | 不可动 |
| 框架 | 无框架；关键依赖：`clap`（CLI）、`syntect`（高亮）、`gix`（git）、`minus`（分页） | 谨慎 |
| 分层职责 | `src/` 按职责分模块（`printer` / `controller` / `config` / `syntax_mapping` / `theme`…）；`src/bin/` 只做入口；`build/` 是构建脚本；`assets/` 是语法与主题资源 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`。有 `CONTRIBUTING.md` 与 `doc/`，但讲的是「怎么贡献」而非「架构为什么这样」。**没有常驻约定文件**，以上红线只存在于本文件，新会话不会自动获得。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 单 crate 同时提供库与 CLI，用 feature 分隔 | 库和 CLI 共享高亮、分页、渲染逻辑，拆成两个 crate 会有大量重复 | 拆成 `bat-lib` + `bat-cli` 两个 crate（边界清晰，但共享代码要下沉成第三个 crate） | `Cargo.toml` 的 features 注释：「Should be disabled when depending on bat as a library」 |
| build script 放在 `build/main.rs` | 根目录留给用户直接看的东西，构建逻辑收纳到子目录 | 默认的根目录 `build.rs`（更符合惯例，但根目录多一个文件） | `Cargo.toml` 的 `build = "build/main.rs"` |
| 断言 stdout/stderr 的集成测试 | bat 的行为就是「输出什么」，只能对输出做断言 | 只测内部函数（快，但覆盖不到参数解析与管道行为） | `CONTRIBUTING.md`：Regression tests |
| 语法与主题用快照/资源测试 | 高亮结果是整段文本，逐字段断言不现实 | 逐 token 断言（精确，但极脆弱） | `tests/snapshot_tests.rs` 与 `tests/syntax-tests/` |
| 每个行为改动都进 CHANGELOG | 发布流程靠 CHANGELOG 汇总，漏了就得维护者自己补 | 发布时凭 commit 整理（省事，但容易漏） | `CONTRIBUTING.md`：Add an entry to the changelog |

## 6. 坑与约束

**踩过的坑**
- **build script 不在根目录**：`build = "build/main.rs"`，改构建逻辑要去 `build/` 而不是找 `build.rs`
- **`application` feature 是给 CLI 用的**：作为库依赖时若不小心带上它，会把 clap、分页器等一堆东西拉进下游构建，体积和编译时间都会爆
- **语法测试需要先有二进制**：`tests/syntax-tests/` 要求先 `cargo build --bins`，否则那批测试跑不起来
- **改输出会让快照测试红**：`tests/snapshots/` 是基准，输出变化要更新快照，但先确认变化是预期的
- **MSRV 1.88 很新**：本机 Rust 版本不够会直接编译失败，且项目允许在有理由时抬 MSRV，别指望降回去
- **CHANGELOG 漏写要返工**：行为、语法、主题、CI 改动都算，提交前对照 `CONTRIBUTING.md` 的清单

**约束与红线**
- 当库被依赖时不要开 `application` feature
- 加新功能先开 feature request issue 讨论（`CONTRIBUTING.md`：Adding a new feature）
- 行为相关改动必须在同一 PR 里更新 `CHANGELOG.md`

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `Cargo.toml` | crate 元数据、**feature 分层**、build script 路径、MSRV，**必读** | 只读 |
| `CONTRIBUTING.md` | CHANGELOG 要求、加功能流程、回归测试怎么写，**动手前必读** | 只读 |
| `src/lib.rs` | 库入口与模块声明 | 只读调研 |
| `src/bin/` | CLI 入口（参数解析、调用库） | 只读调研 |
| `src/printer.rs`、`controller.rs`、`config.rs` | 核心：输出、调度、配置 | 只读调研 |
| `src/syntax_mapping/`、`theme.rs` | 语法与主题映射 | 只读调研 |
| `build/main.rs` | 构建脚本（生成资源相关代码） | 只读调研 |
| `tests/integration_tests.rs` | 起二进制断言输出，功能改动要加测试 | 未运行 |
| `tests/snapshot_tests.rs` + `tests/snapshots/` | 快照测试与基准 | 未运行 |
| `tests/syntax-tests/` | 语法高亮回归，需先 `cargo build --bins` | 未运行 |

## 8. 验证方法

**启动**
- 先装 Rust 1.88+（本机当前没有 cargo）
- 构建：`cargo build`（只 build CLI 可加 `--bins`）
- 测试：`cargo test`（集成 + 快照 + 单元）
- 语法测试：先 `cargo build --bins`，再跑 `tests/syntax-tests/` 对应脚本
- 只开最小 feature 快速迭代：参考 `Cargo.toml` 的 `minimal-application`

**确认成功**
- `cargo test` 全绿
- 快照测试通过说明输出与 `tests/snapshots/` 基准一致
- `cargo build --no-default-features` 能过，说明「当库用」的 feature 边界没被破坏

**上次验证结果**
- **未验证**。本机没有 Rust 工具链，本轮只做静态阅读。以上命令来自 `Cargo.toml` 与 `CONTRIBUTING.md`，未实际执行——接手后先装 Rust 再跑一遍。

## 9. 下一步

**优先级**
1. 装 Rust 1.88+，跑通 `cargo test` 建立基线
2. 若是新功能，先开 feature request issue 讨论（`CONTRIBUTING.md` 明确要求）
3. 改动完成后补 `CHANGELOG.md` 条目并确认 feature 边界没破

**第一步动作**
> 在 `<项目根>` 下装 Rust 1.88+（`cargo --version` 要有输出），执行 `cargo test` 记录基线；若要改的是输出行为，先读 `tests/snapshot_tests.rs` 与 `tests/snapshots/` 现有组织方式，再决定是否新增快照。

**待确认**
- 目标改动是否会碰 `assets/syntaxes` 或 `assets/themes`？碰了就要看 `doc/assets.md` 的语法测试说明
- 是否需要保持「当库使用」的场景可用？需要的话动手全程用 `--no-default-features` 验一遍 feature 边界

## 10. 接手方式

新窗口开场直接粘贴：

```
读 .handoff/handoff-2026-11-21-102737-build-test-research.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
注意 build script 在 build/main.rs，不在根目录；当库依赖时不要开 application feature。
沿用项目现有技术栈，不要新增依赖。
```

建议下一个会话调用的技能：无

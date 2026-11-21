# 交接：模块布局与 API 政策调研，准备提交改动

- 生成时间：2026-11-21 10:33
- 项目：guava（<项目根>）
- 分支：master
- 覆盖范围：从读根 pom 与 CONTRIBUTING → 到搞清模块划分、非标准目录布局、提 PR 的前置门槛
- 上一份交接：无
- 状态：调研完成，未构建未测试

## 1. 一句话目标

Google 的 Java 核心工具库：集合、并发、IO、哈希、字符串处理。它被塞进无数项目的依赖里，所以**API 稳定性高于一切**——加一个新 API 要经过完整设计评审，不是写完提 PR 就能进。

## 2. 阶段结论

- **Maven 多模块聚合**：根 pom 管 5 个模块（`guava` / `guava-bom` / `guava-gwt` / `guava-testlib` / `guava-tests`），`android` / `futures` / `integration-tests` 是额外目录
- **源码目录不是标准 Maven 布局**：主源码在 `guava/src/com/google/common/...`，**没有 `main/java` 两层**。按 Maven 惯例去 `src/main/java` 找会扑空
- **源码级别是 Java 8**：根 pom 里 `<source>1.8</source>`。本机 JDK 是 21，编译目标与运行 JDK 不一致，需要留意
- **测试在独立模块**：单元测试住在 `guava-tests/test/`，不在 `guava` 模块内，找测试别去 `guava/src` 下翻
- **用 wrapper 构建**：仓库自带 `mvnw`，不需要预装 Maven
- **两道前置门槛**：Google 项目的 CLA 必须签；API 变更有专门流程（先开 issue 讲用例 → API 设计评审 → 才写代码）
- **规模**：`guava` 模块 611 个 Java 文件，全仓库 3353 个文件
- **未做**：没有构建、没有跑测试

## 3. 当前状态

**整体**：可读可分析，未构建

**运行态**
- 是库，无服务
- 本机有 **JDK 21**（`java version "21.0.10"`），但没有验证过 Maven 构建
- 依赖需要联网下载，首次构建会拉一批 Maven 插件

**代码态**
- 本地是上游 `master` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无

## 4. 技术栈与既定契约

**必须自己写**（文档里查不到，或者只在 pom 的配置里）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **非标准源码布局**：`guava/src/` 直接就是包根，由 pom 的 sourceDirectory 配置支撑，不要「修正」成 Standard Maven Layout | 硬红线 |
| 非默认选择 | **源码级别锁 Java 8**，虽然本机 JDK 可能更高；不要随手把 `<source>` 抬上去 | 硬红线 |
| 禁区 | 不许删改已发布的公共 API；不许跳过 API 设计评审直接提功能 PR；不许在没有 CLA 的情况下提交 | 硬红线 |
| 对外契约 | 包名 `com.google.common.*`；`@Beta` / `@GwtCompatible` / `@GwtIncompatible` 等注解是 API 契约的一部分，改动影响下游判定 | 改动需评估兼容性 |

**可省略**（能读到，但这里写实，因为布局特殊）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Java，源码级别 1.8（根 pom），模块化描述在 `guava/src/module-info.java` | 不可动 |
| 框架 | 无框架；构建用 Maven（自带 `mvnw` wrapper） | 谨慎 |
| 分层职责 | 每个 `guava-*` 目录是一个 Maven 模块；`guava` 放实现，`guava-tests` 放测试，`guava-testlib` 放测试工具，`guava-gwt` 放 GWT 兼容层 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`。有 `CONTRIBUTING.md`，但只讲贡献流程（API 变更、PR、CLA、构建命令），不讲架构。**没有常驻约定文件**，以上红线只存在于本文件。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 源码目录省掉 `main/java` | 少两层嵌套，路径短；由 pom 显式配置 sourceDirectory 支撑 | 标准 Maven 布局（工具链默认能识别，但路径冗长） | 推断：pom 有 sourceDirectory 配置的痕迹，未找到说明理由的文档 |
| 测试独立成模块 | 测试代码体量大，独立模块可单独发布 `guava-testlib` 给下游复用 | 测试与实现同模块（结构简单，但无法单独分发测试工具） | 目录结构 + `guava-testlib` 的存在 |
| 新 API 必须先设计与评审 | 下游用户太多，草率加 API 之后无法删除 | 先实现再评审（速度快，但容易留下包袱） | `CONTRIBUTING.md`：API changes |
| 源码级别锁 Java 8 | 保证大量只支持旧 JDK 的下游项目能继续用 | 用新语言特性（写法简洁，但会切断旧用户） | 根 `pom.xml` 的 `<source>1.8</source>` |
| 用 Maven wrapper 而非要求装 Maven | 统一构建工具版本，贡献者不用自己配环境 | 直接 `mvn`（快，但版本不一致会导致行为差异） | `CONTRIBUTING.md`：Building and Testing |

## 6. 坑与约束

**踩过的坑**
- **按 Maven 惯例找源码会扑空**：主源码在 `guava/src/com/google/common/`，不是 `src/main/java/com/google/common/`。找类直接按 `com/google/common/` 往下走
- **测试不在 `guava` 模块**：单元测试在 `guava-tests/test/`，改完实现要去那个模块找对应测试
- **本机 JDK 21 编 Java 8 目标**：可能出现与旧 API 相关的警告或检查失败，遇到先确认是不是环境问题而不是代码问题
- **首次构建要下载依赖**：`mvnw` 会拉 Maven 发行版和插件，离线环境跑不起来
- **API 变更不是「写完提 PR」**：CONTRIBUTING 明确要求先开 issue 说清用例，走完 API 设计评审才写代码，顺序错了会白做
- **CLA 是硬门槛**：Google 项目要求签贡献者协议，没签的话 PR 不会被合

**约束与红线**
- 不改已发布的公共 API；不把源码布局「修正」成标准 Maven 结构
- 不擅自抬高 `<source>` / `<target>` 的 Java 版本
- 提功能前先走 issue 与 API 评审流程

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `CONTRIBUTING.md` | API 变更流程、PR 要求、CLA、构建命令，**动手前必读** | 只读 |
| `pom.xml` | 根聚合 pom：模块列表、插件版本、编译级别 | 只读 |
| `guava/pom.xml` | 核心模块的构建配置（含非标准 sourceDirectory） | 只读调研 |
| `guava/src/com/google/common/` | **主源码所在**，包根直接在这里 | 只读调研 |
| `guava/src/module-info.java` | Java 模块化描述 | 只读 |
| `guava-tests/test/` | 单元测试所在（独立模块） | 未运行 |
| `guava-tests/benchmark/` | 基准测试 | 未运行 |
| `guava-testlib/` | 测试工具库，单独发布给下游 | 只读 |
| `guava-gwt/` | GWT 兼容层，加 API 时要注意这里是否需要同步 | 只读 |
| `mvnw` | Maven wrapper 启动脚本，构建入口 | 未使用 |

## 8. 验证方法

**启动**
- 本机有 JDK 21，无需装 Java
- 全量构建：`./mvnw clean package`（首次会下载依赖）
- 单个测试：`./mvnw clean package -Dtest=某个测试类 -DfailIfNoTests=false -Dmaven.javadoc.skip`
- 只构建核心模块：`./mvnw -pl guava -am package`

**确认成功**
- `./mvnw clean package` 以 BUILD SUCCESS 结束
- 目标测试类通过，且不是被 `-DfailIfNoTests=false` 掩盖的「没跑到」

**上次验证结果**
- **未验证**。本轮只做静态阅读，没执行 `mvnw`（首次构建需联网拉依赖）。上面的命令抄自 `CONTRIBUTING.md`，未实际跑过——接手后请先构建一次再相信本文件的任何运行结论。

## 9. 下一步

**优先级**
1. 先跑一次 `./mvnw clean package` 建立基线——不构建就无法判断后面改动有没有引入问题
2. 确认目标改动是「加 API」还是「修 bug」。加 API 必须先开 issue 走评审，修 bug 可以直接提
3. 去 `guava-tests/test/` 找对应测试，别在 `guava/src` 下找

**第一步动作**
> 在 `<项目根>` 下执行 `./mvnw clean package -DskipTests` 确认能编译通过（首次会下载依赖，耗时较长）；然后打开 `guava-tests/test/com/google/common/` 找到与被改动类对应的测试文件，确认它的位置与命名习惯。

**待确认**
- 这次是加 API 还是修 bug？前者要先走 issue 与 API 评审
- 改动是否需要同步 `guava-gwt`？GWT 兼容层对某些 API 有额外要求

## 10. 接手方式

新窗口开场直接粘贴：

```
读 .handoff/handoff-2026-11-21-103336-api-policy-research.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
注意主源码在 guava/src/com/google/common/，不是 src/main/java；测试在 guava-tests 独立模块。
沿用项目现有技术栈，不要抬高 Java 源码级别，不要新增依赖。
```

建议下一个会话调用的技能：无

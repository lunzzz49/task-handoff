# 交接：模块结构与构建逻辑调研

- 生成时间：2026-11-21 10:40
- 项目：okhttp（<项目根>）
- 分支：main
- 覆盖范围：从读 settings.gradle.kts 与目录结构 → 到搞清多模块划分、build-logic 的作用
- 上一份交接：无
- 状态：调研完成，未构建

## 1. 一句话目标

JVM 上的 HTTP 客户端：连接池、HTTP/2、拦截器链、WebSocket。既服务于 Android 也服务于服务端 JVM，所以模块划分要同时照顾两端。

## 2. 阶段结论

- **模块数量多且按能力切分**：核心 `okhttp`，配套 `mockwebserver` 系列（含 junit4/junit5 集成与 deprecated 版）、扩展（`okhttp-brotli`、`okhttp-coroutines`、`okhttp-dnsoverhttps`）、工具（`okcurl`）、BOM（`okhttp-bom`）、测试辅助（`okhttp-hpacktests`、`okhttp-idna-mapping-table`）
- **构建逻辑独立成项目**：`build-logic` 通过 `includeBuild("build-logic")` 引入，是 Gradle 的复合构建，不是普通子模块
- **根项目名是 `okhttp-parent`**，不是 `okhttp`
- **`mockwebserver` 有两代**：现行版与被标记 deprecated 的旧版并存，junit4 / junit5 各有一个适配模块
- **有独立测试目录**：`android-test`、`android-test-app`、`native-image-tests`、`maven-tests`、`module-tests`、`regression-test` 等
- **未做**：没构建、没跑测试

## 3. 当前状态

**整体**：可读可分析，未构建

**运行态**
- 是库，无服务
- 本机有 JDK 21，但用 Gradle 构建需要先下载 wrapper 与依赖

**代码态**
- 本地是上游 `main` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无

## 4. 技术栈与既定契约

**必须自己写**（文档里查不到，或者要看 Gradle 配置才知道）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **构建逻辑用复合构建**（`includeBuild("build-logic")`），构建约定集中在那里，不在各模块的 `build.gradle.kts` 里重复 | 保持现状 |
| 非默认选择 | **同一能力有多模块**：`mockwebserver` 分现行/deprecated、junit4/junit5 四个模块，改动要判断影响哪几个 | 保持现状 |
| 禁区 | 不改已发布公共 API 的签名；不在核心模块里引入 Android 专属依赖（会破坏服务端 JVM 使用） | 硬红线 |
| 对外契约 | 包名 `okhttp3.*`；`OkHttpClient` / `Interceptor` / `Call` / `Response` 是公开 API 主干 | 改动需评估兼容性 |

**可省略**（能读到，但这里写实）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | Kotlin（源码）为主，部分模块可能含 Java；JVM + Android 双目标 | 不可动 |
| 框架 | Gradle 多模块 + 复合构建（`build-logic`），版本目录在 `gradle/` 下 | 谨慎 |
| 分层职责 | 根 `build.gradle.kts` 只放插件声明；各能力一个模块；`build-logic` 放构建约定；测试辅助与集成测试分散在 `android-test`、`maven-tests` 等目录 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`。有 `CONTRIBUTING.md` / `CHANGELOG.md` / `docs/`，但贡献指南讲流程、`docs/` 面向使用者。**没有常驻约定文件**。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 构建逻辑抽成 `build-logic` 复合构建 | 二十多个模块共享同一套编译/发布/测试约定，写在根 build 文件里会失控 | 全部写在根 `build.gradle.kts`（文件少，但难维护） | `settings.gradle.kts` 的 `includeBuild("build-logic")` |
| 按能力拆模块而非一个大模块 | 用户只依赖需要的部分，`okhttp-brotli` 之类不强制引入 | 单模块（依赖简单，但把可选能力变成必选） | `settings.gradle.kts` 的 include 列表 |
| mockwebserver 保留 deprecated 版 | 存量测试代码不能强制迁移 | 直接删旧版（干净，但破坏下游测试） | 模块名 `mockwebserver-deprecated` 的存在 |
| junit4 / junit5 各一个适配模块 | 两种测试框架的用户都要照顾 | 只支持 junit5（现代，但挡掉旧项目） | 模块名 `mockwebserver-junit4` / `-junit5` |
| 提供 `okhttp-bom` | 多模块项目需要统一版本对齐 | 各模块各自管版本（用户要分别指定） | 模块名 `okhttp-bom` |

## 6. 坑与约束

**踩过的坑**
- **`build-logic` 不是普通子模块**：它是 `includeBuild` 引入的复合构建，改构建约定要去那里，不在 `build.gradle.kts` 里找
- **根项目名是 `okhttp-parent`**：脚本或文档里写 `:okhttp` 指的不是根
- **mockwebserver 有四个模块**：改 mock 行为要确认影响现行版还是 deprecated 版，junit4/junit5 各自是否需要同步
- **核心模块不能带 Android 依赖**：否则服务端 JVM 用户无法使用
- **测试分散在多个目录**：`android-test` 需要 Android 环境，`native-image-tests` 需要 GraalVM，不是所有测试本地都能跑
- **构建要联网**：Gradle wrapper 与依赖首次下载耗时较长

**约束与红线**
- 不改已发布公共 API 签名
- 核心模块不引入 Android 专属依赖
- 改 mockwebserver 时注意 deprecated 版是否需同步

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `settings.gradle.kts` | 模块清单与 `includeBuild("build-logic")`，**模块结构看这里** | 只读调研 |
| `build.gradle.kts` | 根构建：插件声明（多为 `apply false`） | 只读 |
| `build-logic/` | 复合构建，集中放编译/测试/发布约定 | 只读调研 |
| `okhttp/` | 核心模块：客户端、连接池、拦截器、HTTP/2 | 只读调研 |
| `mockwebserver/` | 测试用假服务器（现行版） | 只读 |
| `okhttp-coroutines/` | Kotlin 协程适配 | 只读 |
| `okhttp-brotli/`、`okhttp-dnsoverhttps/` | 可选能力扩展 | 只读 |
| `docs/` | 面向使用者的文档 | 只读 |
| `CONTRIBUTING.md` | 贡献流程 | 只读 |
| `android-test/`、`native-image-tests/` | 需要特定环境的测试 | 未运行 |

## 8. 验证方法

**启动**
- 本机 JDK 21 可用
- 全量构建：`./gradlew build`（首次会下载 wrapper 与依赖）
- 只构建核心模块：`./gradlew :okhttp:build`
- 核心模块测试：`./gradlew :okhttp:test`

**确认成功**
- Gradle 以 BUILD SUCCESSFUL 结束
- 目标模块的测试任务通过

**上次验证结果**
- **未验证**。本轮没执行 Gradle，只做静态阅读。上面的任务路径依据 `settings.gradle.kts` 的模块名推断，未实际跑过。

## 9. 下一步

**优先级**
1. 先跑 `./gradlew :okhttp:build` 建立基线（比全量快，先确认核心能编）
2. 确认改动落在哪个模块，以及是否牵连 mockwebserver 的多个版本
3. 若涉及公共 API，同步检查 `okhttp-bom` 与 `docs/`

**第一步动作**
> 在 `<项目根>` 下执行 `./gradlew :okhttp:build -x test` 先确认能编译（首次下载依赖较慢），然后打开 `okhttp/src/main/java/okhttp3/` 找到要改的类，并检查 `mockwebserver/` 里是否有依赖它行为的测试。

**待确认**
- 改动是否影响 mockwebserver 的 deprecated 版？影响就要四个模块一起看
- 是否需要 Android 侧验证（`android-test` 需要 Android SDK）

## 10. 接手方式

新窗口开场直接粘贴：

```
读 .handoff/handoff-2026-11-21-104025-gradle-modules.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
模块结构看 settings.gradle.kts；构建约定在 build-logic（复合构建），不在各模块 build.gradle.kts 里。
沿用项目现有技术栈，不要新增依赖。
```

建议下一个会话调用的技能：无

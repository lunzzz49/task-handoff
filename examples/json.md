# 交接：构建与分发形态调研

- 生成时间：2026-11-21 10:38
- 项目：json（<项目根>）
- 分支：develop
- 覆盖范围：从读 CMakeLists 与 FILES.md → 到搞清两套源码形态、五套构建系统、C++ 标准覆盖
- 上一份交接：无
- 状态：调研完成，未构建

## 1. 一句话目标

现代 C++ 的 JSON 库：header-only、零依赖、`nlohmann::json` 一个类型搞定序列化与反序列化。设计上优先「用起来省事」而不是「极致性能」。

## 2. 阶段结论

- **两套源码形态并存**：`include/nlohmann/` 是模块化源码，`single_include/nlohmann/json.hpp` 是给用户直接拷走的单头文件版
- **五套构建系统**：CMake、Bazel、Meson、Makefile、SwiftPM。改构建相关的东西要同步多套
- **C++ 标准覆盖 11 → 26**：库自身要求 C++11（`cxx_std_11`），CI 在 11/14/17/20/23/26 六个标准上分别跑
- **CMake 版本有分段逻辑**：最低 3.5，但 C++20 module 支持要求 3.28+，低于该版本会跳过 module 部分并给警告
- **有 `FILES.md` 专门说明支撑文件**：CI、GitHub 配置、REUSE 合规、包管理器、调试辅助都在这里登记
- **未做**：没构建、没跑测试

## 3. 当前状态

**整体**：可读可分析，未构建

**运行态**
- 纯 header-only 库，无运行时
- 本机未验证任何一套构建系统（CMake / Bazel / Meson / Makefile / SwiftPM 都没跑）

**代码态**
- 本地是上游 `develop` 的 tarball 快照，**只有一次提交**（`baseline snapshot for skill evaluation`），不是上游真实历史
- 未提交改动：无

## 4. 技术栈与既定契约

**必须自己写**（文档里查不到，或者要在多套构建配置间对照才知道）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 非默认选择 | **两套源码形态并存**：`include/` 是开发用的模块化源，`single_include/` 是对外分发形态。改代码要考虑两者一致性 | 硬红线 |
| 非默认选择 | **五套构建系统并行维护**，不是主从关系。改构建/编译选项要逐套核对 | 保持现状 |
| 禁区 | 不许引入运行时依赖（header-only 是核心卖点）；不许抬高最低 C++ 标准（C++11 是兼容底线） | 硬红线 |
| 对外契约 | 命名空间 `nlohmann`，主类型 `nlohmann::json`；单头文件路径 `nlohmann/json.hpp` 是大量项目的硬引用 | 改动需评估兼容性 |

**可省略**（能读到，但这里写实）：

| 项 | 内容 | 是否可动 |
|---|---|---|
| 语言/运行时 | C++11 起（`target_compile_features ... cxx_std_11`），CI 覆盖 11~26 | 不可动 |
| 框架 | 无框架；构建系统五套（CMake / Bazel / Meson / Makefile / SwiftPM） | 谨慎 |
| 分层职责 | `include/nlohmann/` 模块化源（含 `detail/`）、`single_include/` 分发形态、`tests/` 测试、`tools/` 辅助脚本、`cmake/` CMake 模块与 CI 定义 | 保持现状 |

**红线出处**：项目根不含 `AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md`。唯一的项目自述是 `FILES.md`（讲支撑文件怎么组织）与 `README.md`（面向使用者）。**没有常驻约定文件**。

## 5. 关键决策

| 决策 | 理由 | 放弃了什么 | 来源 |
|---|---|---|---|
| 提供单头文件分发形态 | C++ 生态里大量项目不愿引入构建依赖，拷一个 hpp 就能用 | 只发模块化源码（干净，但集成门槛高） | `single_include/` 的存在 + `FILES.md` |
| 多套构建系统并行 | 不同生态各有惯例（Bazel 用户、Meson 用户、SwiftPM 用户都要能用） | 只维护 CMake（省事，但挡掉一部分用户） | 根目录同时存在 `CMakeLists.txt` / `BUILD.bazel` / `meson.build` / `Makefile` / `Package.swift` |
| 最低 C++11 | 覆盖面优先，老项目也能用 | 直接用 C++17/20 特性（写法简洁，但切断旧编译器） | `CMakeLists.txt` 的 `cxx_std_11` |
| CI 逐标准验证 | 只测一个标准无法发现跨标准的行为差异 | 只测最新标准（快，但漏问题） | `cmake/ci.cmake` 的 `foreach(CXX_STANDARD 11 14 17 20 23 26)` |

## 6. 坑与约束

**踩过的坑**
- **改源码要考虑两套形态**：`include/` 改了，`single_include/` 未必自动同步，而用户引用的是后者
- **构建系统不止 CMake**：只改 `CMakeLists.txt` 会让 Bazel / Meson 用户构建失败
- **C++20 module 有 CMake 版本门槛**：低于 3.28 会跳过该部分并打警告，不代表配置错了
- **CI 按六个 C++ 标准分别跑**：本地用 C++20 编过不代表 C++11 也能过，别用新语法
- **`FILES.md` 是索引不是文档**：找 CI 配置、包管理器注册、REUSE 合规信息先看它

**约束与红线**
- 不引入运行时依赖
- 不抬高最低 C++ 标准
- 改构建相关配置时逐套核对

## 7. 文件地图

| 路径 | 作用 | 本阶段 |
|---|---|---|
| `CMakeLists.txt` | 主构建定义：项目版本、C++ 标准、安装规则 | 只读调研 |
| `cmake/ci.cmake` | CI 各标准的构建与测试目标定义 | 只读 |
| `include/nlohmann/` | 模块化源码（`detail/` 子目录放实现细节） | 只读调研 |
| `single_include/nlohmann/json.hpp` | 对外分发的单头文件版 | 只读，需与上者保持一致 |
| `tests/` | 测试与测试数据 | 未运行 |
| `tools/` | 辅助脚本（生成、检查类） | 只读 |
| `FILES.md` | 支撑文件索引：CI、GitHub、REUSE、包管理器、调试 | 只读 |
| `README.md` | 面向使用者的用法说明 | 只读 |
| `Makefile`、`meson.build`、`BUILD.bazel`、`Package.swift` | 另外四套构建入口 | 只读 |

## 8. 验证方法

**启动**
- CMake：`cmake -S . -B build && cmake --build build && ctest --test-dir build`
- 其它构建系统各自入口：`bazel test //...`、`meson setup build && meson test -C build`、`make check`、`swift build`

**确认成功**
- CMake 配置阶段无错误，测试全过
- 若要验证跨标准，参考 `cmake/ci.cmake` 里的写法分别指定标准再跑

**上次验证结果**
- **未验证**。本机未执行任何构建。以上命令依据 `CMakeLists.txt` 与 `cmake/ci.cmake` 推断，未实际跑过。

## 9. 下一步

**优先级**
1. 先用 CMake 跑一次完整构建 + 测试建立基线
2. 确认改动落在哪套源码：只改 `include/` 还是也要动 `single_include/`
3. 若涉及构建配置，逐套检查 CMake / Bazel / Meson / Makefile / SwiftPM

**第一步动作**
> 在 `<项目根>` 下执行 `cmake -S . -B build -DJSON_BuildTests=ON && cmake --build build -j`，再 `ctest --test-dir build`；同时打开 `include/nlohmann/json.hpp` 与 `single_include/nlohmann/json.hpp` 对比，确认两者是同一份内容的不同组织方式，还是需要额外生成步骤。

**待确认**
- `single_include/nlohmann/json.hpp` 是手工维护还是由脚本从 `include/` 生成的？`tools/` 下可能有相关脚本，本轮未确认
- 目标改动是否需要同步到另外四套构建系统

## 10. 接手方式

新窗口开场直接粘贴：

```
读 .handoff/handoff-2026-11-21-103847-cmake-build.md，按第 9 节「第一步动作」继续。
先跑文中的验证命令核对现实，与文档不一致时以代码为准并告诉我。
注意源码有两套形态：include/ 与 single_include/；构建系统有五套，改一套要核对其他几套。
沿用项目现有技术栈，不要引入运行时依赖，不要抬高最低 C++ 标准。
```

建议下一个会话调用的技能：无

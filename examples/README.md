# 真实产出示例

这 8 份交接文档都是在真实开源项目上、按 `SKILL.md` 的流程生成的，未经润色。

| 文件 | 项目 | star | 语言 | 一份文档主要抓到了什么 |
|---|---|---|---|---|
| `markitdown.md` | [microsoft/markitdown](https://github.com/microsoft/markitdown) | 197k | Python | `priority` 双规则并存、`accepts()` 的 stream 契约、monorepo 根无 pyproject |
| `python-sdk.md` | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | 25k | Python | `docs_src` 与测试的联动（文档示例即 CI 跑的代码） |
| `bubbletea.md` | [charmbracelet/bubbletea](https://github.com/charmbracelet/bubbletea) | 46k | Go | module path 不是 GitHub 地址、build tags 双写、`-race -count 4` |
| `bat.md` | [sharkdp/bat](https://github.com/sharkdp/bat) | 61k | Rust | build script 不在根目录、`application` feature 当库用要关 |
| `guava.md` | [google/guava](https://github.com/google/guava) | 52k | Java | 非标准 Maven 布局（无 `main/java`）、API 变更需先评审、CLA |
| `json.md` | [nlohmann/json](https://github.com/nlohmann/json) | 51k | C++ | 两套源码形态、五套构建系统、C++11~26 六标准验证 |
| `polly.md` | [App-vNext/Polly](https://github.com/App-vNext/Polly) | 14k | C# | v8 重写与 legacy 包的边界、集中式包版本管理 |
| `okhttp.md` | [square/okhttp](https://github.com/square/okhttp) | 47k | Kotlin | `build-logic` 是复合构建、mockwebserver 四模块 |

## 怎么读

建议对照原项目的官方文档看，比较容易看出差异：

- 官方 README 讲「怎么用」，交接文档讲「改的时候哪里会咬人」
- 例如 `markitdown.md` 第 6 节那三条，在它 475 行的 README 里一次都没出现过
- `guava.md` 第 4 节记录的「非标准源码布局」，只有打开 `pom.xml` 才看得出来

## 关于文件名里的路径

文档头部记录的项目路径（如 `<项目根>`）是当时生成用的临时副本位置，不是项目真实位置。原项目分别在上表链接的仓库里。

## 复现

```bash
cd <目标项目根>
python <skill路径>/scripts/handoff.py new --slug <主题>
# 按 SKILL.md 的流程读代码、填十节
python <skill路径>/scripts/handoff.py check --stale
```

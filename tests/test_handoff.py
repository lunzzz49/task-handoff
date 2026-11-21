"""handoff.py 的自动化测试。运行：python tests/test_handoff.py -v"""

import importlib.util
import io
import re
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("handoff_tool", SKILL / "scripts" / "handoff.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "requirements.txt").write_text("fastapi", encoding="utf-8")
        (self.root / "app.py").write_text("print(1)", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def new(self, slug="demo", inherit=False):
        ns = Namespace(slug=slug, root=str(self.root), inherit=inherit)
        rc, out = quiet(mod.cmd_new, ns)
        self.assertEqual(rc, 0)
        return sorted((self.root / ".handoff").glob("handoff-*.md"))[-1]

    def log(self, event, files=None, verify=None):
        ns = Namespace(event=event, files=files, verify=verify, slug="auto", doc=None, root=str(self.root))
        rc, out = quiet(mod.cmd_log, ns)
        self.assertEqual(rc, 0)
        return out


class TestCreate(Base):
    def test_never_overwrites(self):
        self.new("demo")
        self.new("demo")
        files = list((self.root / ".handoff").glob("handoff-*.md"))
        self.assertEqual(len(files), 2, "同分钟内重复创建必须生成两份文件")

    def test_branch_field_present(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        self.assertIn("- 分支：", text)

    def test_inherit_pulls_stable_sections(self):
        first = self.new("first")
        text = first.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 1, "把行程导出成 Excel，方便离线发给客户。")
        text = mod.set_section_body(text, 4, "| 语言 | Python 3.11 | 不可动 |")
        text = mod.set_constraint_block(text, "- 不要改 `models/` 下任何文件")
        first.write_text(text, encoding="utf-8")

        second = self.new("second", inherit=True)
        itext = second.read_text(encoding="utf-8")
        self.assertIn("把行程导出成 Excel", itext)
        self.assertIn("Python 3.11", itext)
        self.assertIn("不要改 `models/`", itext)
        self.assertIn("继承自", itext)

    def test_inherit_skips_empty_previous(self):
        self.new("first")  # 空骨架
        second = self.new("second", inherit=True)
        self.assertNotIn("继承自", second.read_text(encoding="utf-8"))


class TestSections(unittest.TestCase):
    def test_section_body_isolates_section(self):
        text = "## 1. 目标\n\n内容A\n\n## 2. 结论\n\n内容B\n"
        self.assertIn("内容A", mod.section_body(text, 1))
        self.assertNotIn("内容B", mod.section_body(text, 1))

    def test_section_body_matches_10_not_1(self):
        text = "## 1. 目标\nA\n\n## 10. 接手\nB\n"
        self.assertIn("A", mod.section_body(text, 1))
        self.assertNotIn("B", mod.section_body(text, 1))

    def test_is_filled(self):
        self.assertFalse(mod.is_filled(""))
        self.assertFalse(mod.is_filled("<占位符内容>"))
        self.assertTrue(mod.is_filled("这是一段足够长的真实内容，用来判断是否填写过。"))

    def test_set_section_body_roundtrip(self):
        text = "## 1. 目标\n\n旧\n\n## 2. 结论\n\nB\n"
        out = mod.set_section_body(text, 1, "新内容")
        self.assertIn("新内容", out)
        self.assertNotIn("旧", out)
        self.assertIn("## 2. 结论", out)


class TestPaths(unittest.TestCase):
    def test_ignores_placeholder(self):
        text = "路径：<`api/` 与 `AGENTS.md`> 以及 `backend/app.py`"
        self.assertEqual(mod.extract_paths(text), ["backend/app.py"])

    def test_ignores_quote_block(self):
        text = "> 能从 `package.json` 读出来的\n\n真路径 `app.py`"
        self.assertEqual(mod.extract_paths(text), ["app.py"])

    def test_dedupes(self):
        text = "`app.py` 和 `app.py`"
        self.assertEqual(mod.extract_paths(text), ["app.py"])

    def test_rejects_non_path(self):
        text = "`utf-8-sig` `curl -X GET` `https://x.com`"
        self.assertEqual(mod.extract_paths(text), [])

    def test_rejects_http_route(self):
        """坑⑤：`/api/orders` 是 HTTP 路由，不该当成项目内文件去核对。"""
        text = "接口 `/api/orders`，另一个 `/health`"
        self.assertEqual(mod.extract_paths(text), [])

    def test_rejects_module_path(self):
        """坑⑬：Go module path / 包名不是文件路径。"""
        text = "import 路径是 `charm.land/bubbletea/v2`，不是 `github.com/charmbracelet/bubbletea`"
        self.assertEqual(mod.extract_paths(text), [])

    def test_rejects_uri_schemes(self):
        """坑⑭：chrome:// / file:// / vscode:// 是 URI，不是项目内文件。"""
        text = "打开 `chrome://extensions` 或 `vscode://settings`，本地看 `file:///tmp/a`"
        self.assertEqual(mod.extract_paths(text), [])

    def test_rejects_git_refs(self):
        """坑⑲：refs/heads/main 是 git 引用名，不是工作区文件。"""
        text = "被重写的是 `refs/heads/main` 和 `refs/remotes/origin/main`"
        self.assertEqual(mod.extract_paths(text), [])

    def test_skips_paths_in_negated_sentences(self):
        """坑⑥：文档说「没有 / 是蓝图 / 已排除」的路径，不能被 --stale 报成缺失。"""
        text = (
            "项目根无 `AGENTS.md`，`CLAUDE.md` 也没有。\n"
            "README 里的 `llm/` `tools/` 是蓝图，当前不存在。\n"
            "不改 `.gitignore` 里已排除的 `.env`。\n"
            "源码目录省掉 `main/java` 这一层。\n"
            "真实文件 `app.py` 存在。"
        )
        self.assertEqual(mod.extract_paths(text), ["app.py"])

    def test_ignores_closing_xml_tags(self):
        """坑⑯：`</source>` 这类闭合标签不是未填占位符。"""
        self.assertFalse(mod.is_scaffold_placeholder("</source>"))
        self.assertFalse(mod.is_scaffold_placeholder("</module>"))
        self.assertTrue(mod.is_scaffold_placeholder("<阶段主题>"))


class TestTimeline(Base):
    def test_log_creates_timeline(self):
        self.new()
        self.log("跑通导出")
        text = sorted((self.root / ".handoff").glob("handoff-*.md"))[-1].read_text(encoding="utf-8")
        self.assertIn(mod.TIMELINE_HEADING, text)
        self.assertIn("跑通导出", text)

    def test_log_appends_multiple(self):
        self.new()
        self.log("第一条")
        self.log("第二条")
        text = sorted((self.root / ".handoff").glob("handoff-*.md"))[-1].read_text(encoding="utf-8")
        self.assertLess(text.index("第一条"), text.index("第二条"))

    def test_log_without_doc_creates_one(self):
        self.log("无文档时记录")
        self.assertEqual(len(list((self.root / ".handoff").glob("handoff-*.md"))), 1)

    def test_undo_by_id(self):
        doc = self.new()
        self.log("甲")
        self.log("乙")
        text = doc.read_text(encoding="utf-8")
        first_id = mod.ENTRY_RE.findall(text)[0]
        ns = Namespace(id=first_id, file=str(doc), root=str(self.root))
        rc, _ = quiet(mod.cmd_undo, ns)
        self.assertEqual(rc, 0)
        after = doc.read_text(encoding="utf-8")
        self.assertNotIn(first_id, after)
        self.assertEqual(len(mod.ENTRY_RE.findall(after)), 1)

    def test_undo_last_when_no_id(self):
        doc = self.new()
        self.log("甲")
        self.log("乙")
        ns = Namespace(id=None, file=str(doc), root=str(self.root))
        rc, _ = quiet(mod.cmd_undo, ns)
        self.assertEqual(rc, 0)
        self.assertEqual(len(mod.ENTRY_RE.findall(doc.read_text(encoding="utf-8"))), 1)

    def test_undo_unknown_id_fails(self):
        doc = self.new()
        self.log("甲")
        ns = Namespace(id="zzzzzz", file=str(doc), root=str(self.root))
        rc, _ = quiet(mod.cmd_undo, ns)
        self.assertEqual(rc, 1)

    def test_restore_brings_entry_back(self):
        doc = self.new()
        self.log("甲")
        ns = Namespace(id=None, file=str(doc), root=str(self.root))
        quiet(mod.cmd_undo, ns)
        self.assertEqual(len(mod.ENTRY_RE.findall(doc.read_text(encoding="utf-8"))), 0)
        rc, _ = quiet(mod.cmd_restore, Namespace(file=str(doc), root=str(self.root)))
        self.assertEqual(rc, 0)
        self.assertEqual(len(mod.ENTRY_RE.findall(doc.read_text(encoding="utf-8"))), 1)

    def test_summarize_apply_archives(self):
        doc = self.new()
        self.log("甲")
        self.log("乙")
        ns = Namespace(apply=True, doc=str(doc), root=str(self.root))
        rc, out = quiet(mod.cmd_summarize, ns)
        self.assertEqual(rc, 0)
        text = doc.read_text(encoding="utf-8")
        self.assertIn(mod.ARCHIVE_HEADING, text)
        self.assertIn("甲", text)
        self.assertIn("归档", out)

    def test_summarize_dry_run_keeps_entries(self):
        doc = self.new()
        self.log("甲")
        ns = Namespace(apply=False, doc=str(doc), root=str(self.root))
        rc, _ = quiet(mod.cmd_summarize, ns)
        self.assertEqual(rc, 0)
        self.assertEqual(len(mod.ENTRY_RE.findall(doc.read_text(encoding="utf-8"))), 1)


class TestCheck(Base):
    def run_check(self, doc, stale=False):
        ns = Namespace(file=str(doc), stale=stale, root=str(self.root))
        return quiet(mod.cmd_check, ns)

    def test_missing_section_fails(self):
        doc = self.root / ".handoff" / "x.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("## 1. 一句话目标\n\n内容\n", encoding="utf-8")
        rc, out = self.run_check(doc)
        self.assertEqual(rc, 1)
        self.assertIn("缺少第 10 节", out)

    def test_secret_detected(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8").replace("<阶段主题>", "sk-abcdef1234567890abcd")
        doc.write_text(text, encoding="utf-8")
        rc, out = self.run_check(doc)
        self.assertEqual(rc, 1)
        self.assertIn("疑似敏感信息", out)

    def test_vague_first_action_warns(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = text.replace(
            "> <具体到一个文件/函数/命令。新会话读完这句就能立刻动手。>",
            "> 继续优化这部分功能，完善细节。",
        )
        text = mod.set_section_body(text, 1, "目标内容足够长以避免占位符判定为未填。")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc)
        self.assertIn("空泛", out)

    def test_stale_flags_missing_path(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 1, "见 `nope.py` 这个文件。")
        doc.write_text(text, encoding="utf-8")
        rc, out = self.run_check(doc, stale=True)
        self.assertIn("路径已不存在", out)

    def test_stale_passes_existing_path(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 1, "见 `app.py` 这个文件。")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=True)
        self.assertIn("文中路径均存在", out)


class TestRegressions(Base):
    """这组用例对应四个真实踩过的坑，改脚本时必须保持绿。"""

    def run_check(self, doc, stale=False):
        ns = Namespace(file=str(doc), stale=stale, root=str(self.root))
        return quiet(mod.cmd_check, ns)

    # 坑①：正文里长得像条目的一行，被 summarize 当成进展搬走
    def test_summarize_keeps_body_lines_that_look_like_entries(self):
        doc = self.new()
        self.log("完成导出", verify="页面点导出能下载")
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(
            text, 5, "补充说明（正文，不是进展条目）：\n\n- `c9f1a2` 是租户编号前缀，改它要同步三方系统"
        )
        doc.write_text(text, encoding="utf-8")

        quiet(mod.cmd_summarize, Namespace(apply=True, doc=str(doc), root=str(self.root)))
        after = doc.read_text(encoding="utf-8")

        self.assertIn("c9f1a2", mod.section_body(after, 5), "正文里的编号行必须留在原位")
        bounds = mod.section_bounds(after, mod.ARCHIVE_HEADING)
        if bounds:
            self.assertNotIn("c9f1a2", after[bounds[0]:bounds[1]], "不能把正文内容搬进归档区")

    def test_summarize_twice_does_not_duplicate(self):
        doc = self.new()
        self.log("只此一条", verify="跑通 pytest")
        ns = Namespace(apply=True, doc=str(doc), root=str(self.root))
        quiet(mod.cmd_summarize, ns)
        quiet(mod.cmd_summarize, ns)
        self.assertEqual(doc.read_text(encoding="utf-8").count("只此一条"), 1)

    # 坑②：泛型/类型参数被当成未填占位符
    def test_check_accepts_generic_type_args(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 4, "| 对外契约 | 返回 `List<String>` 与 `Map<K,V>` | 不可动 |")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc)
        self.assertNotIn("<String>", out)
        self.assertNotIn("<K,V>", out)

    def test_is_filled_accepts_generic_type_args(self):
        self.assertTrue(mod.is_filled("统一返回 `Response[List<String>>` 封装，长度足够判定已填写。"))
        self.assertFalse(mod.is_filled("<阶段主题：这里该填什么>"))
        self.assertFalse(mod.is_filled("<项目名>"))

    # 坑③：「验证方式必填」只在文字里，工具放水
    def test_log_warns_when_verify_missing(self):
        self.new()
        out = self.log("完成导出")
        self.assertIn("未提供 --verify", out)

    def test_log_quiet_when_verify_provided(self):
        self.new()
        out = self.log("完成导出", verify="页面点导出能下载")
        self.assertNotIn("未提供 --verify", out)

    def test_check_warns_entry_without_verify(self):
        doc = self.new()
        self.log("完成导出")
        _, out = self.run_check(doc)
        self.assertIn("缺「验证：」", out)

    def test_check_quiet_when_entry_has_verify(self):
        doc = self.new()
        self.log("完成导出", verify="页面点导出能下载")
        _, out = self.run_check(doc)
        self.assertNotIn("缺「验证：」", out)

    # 坑④：空 git 仓库被误判成「非 git 仓库」，分支隔离失效
    def test_branch_detected_before_first_commit(self):
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=str(self.root), check=True,
            capture_output=True,
        )
        self.assertEqual(mod.git_branch(self.root), "main")

    def test_branch_none_outside_git(self):
        self.assertIsNone(mod.git_branch(self.root))

    # 坑⑦：文中写 `api/` 但实际在 `backend/api/`，不该报「路径已不存在」
    def test_dir_shorthand_resolves_by_search(self):
        (self.root / "backend" / "api").mkdir(parents=True)
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 7, "| `api/` | 路由 | 新增 |")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=True)
        self.assertIn("路径简写", out)
        self.assertIn("backend/api", out)
        self.assertNotIn("路径已不存在（删除或改名）：api/", out)

    def test_file_shorthand_resolves_by_search(self):
        """文件简写：文中写 `Start.bat`，实际在 `sub/Start.bat`，不该报缺失。"""
        (self.root / "sub").mkdir()
        (self.root / "sub" / "Start.bat").write_text("@echo off", encoding="utf-8")
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 7, "| `Start.bat` | 本地启动脚本 | 只读 |")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=True)
        self.assertIn("路径简写", out)
        self.assertIn("sub/Start.bat", out)
        self.assertNotIn("路径已不存在（删除或改名）：Start.bat", out)

    def test_missing_dir_still_reported(self):
        doc = self.new()
        text = doc.read_text(encoding="utf-8")
        text = mod.set_section_body(text, 7, "| `nothere/` | 说明 | 新增 |")
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=True)
        self.assertIn("路径已不存在（删除或改名）：nothere/", out)

    def test_dir_search_skips_dependency_dirs(self):
        (self.root / "node_modules" / "api").mkdir(parents=True)
        (self.root / "src" / "api").mkdir(parents=True)
        self.assertEqual(mod.find_dir_by_name(self.root, "api"), ["src/api"])


    def test_log_multiple_files_are_quoted_separately(self):
        """坑⑧：--files 多文件若整串包一个反引号，含空格会被判成非路径，静默漏检。"""
        self.new()
        self.log("改了两个文件", files="a.py, b.py", verify="跑通")
        text = sorted((self.root / ".handoff").glob("handoff-*.md"))[-1].read_text(encoding="utf-8")
        self.assertIn("`a.py`", text)
        self.assertIn("`b.py`", text)
        self.assertNotIn("`a.py, b.py`", text)

    def test_log_multiple_files_are_extractable_for_stale(self):
        doc = self.new()
        self.log("改了两个文件", files="a.py, b.py", verify="跑通")
        paths = mod.extract_paths(doc.read_text(encoding="utf-8"))
        self.assertIn("a.py", paths)
        self.assertIn("b.py", paths)

    # 坑⑨：latest 指向刚 new 出来、还没填的骨架，接手的人会把空文档当真
    def test_latest_warns_on_unfilled_scaffold(self):
        self.new()
        rc, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertEqual(rc, 0)
        self.assertIn("未填占位符", out)

    def test_latest_points_to_previous_when_latest_is_blank(self):
        self.new("first")
        self.new("second")
        _, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertIn("上一份", out)
        self.assertIn("first", out)

    def test_latest_quiet_when_document_is_filled(self):
        doc = self.new()
        text = re.sub(r"<[^<>\n]{1,120}>", "已填写", doc.read_text(encoding="utf-8"))
        doc.write_text(text, encoding="utf-8")
        _, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertNotIn("未填占位符", out)

    # 坑⑩：归档条目被撤空后，留下一个空的「已归档进展」章节
    def test_undo_removes_empty_archive_section(self):
        doc = self.new()
        self.log("唯一一条", verify="跑通")
        quiet(mod.cmd_summarize, Namespace(apply=True, doc=str(doc), root=str(self.root)))
        text = doc.read_text(encoding="utf-8")
        self.assertIn(mod.ARCHIVE_HEADING, text)
        entry_id = mod.ENTRY_RE.findall(text)[0]
        quiet(mod.cmd_undo, Namespace(id=entry_id, file=str(doc), root=str(self.root)))
        self.assertNotIn(mod.ARCHIVE_HEADING, doc.read_text(encoding="utf-8"))

    def test_undo_keeps_archive_when_entries_remain(self):
        doc = self.new()
        self.log("第一条", verify="跑通")
        self.log("第二条", verify="跑通")
        quiet(mod.cmd_summarize, Namespace(apply=True, doc=str(doc), root=str(self.root)))
        text = doc.read_text(encoding="utf-8")
        entry_id = mod.ENTRY_RE.findall(text)[0]
        quiet(mod.cmd_undo, Namespace(id=entry_id, file=str(doc), root=str(self.root)))
        self.assertIn(mod.ARCHIVE_HEADING, doc.read_text(encoding="utf-8"))

    # 坑⑪：关键决策表少了「来源」列，事实与推断混在一起（standards 2.6）
    def test_decision_table_without_source_warns(self):
        doc = self.new()
        text = mod.set_section_body(
            doc.read_text(encoding="utf-8"), 5,
            "| 决策 | 理由 | 放弃了什么 |\n|---|---|---|\n| 用 A | 因为 B | 放弃 C |",
        )
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc)
        self.assertIn("缺少「来源」列", out)

    def test_decision_table_with_source_is_quiet(self):
        doc = self.new()
        text = mod.set_section_body(
            doc.read_text(encoding="utf-8"), 5,
            "| 决策 | 理由 | 放弃了什么 | 来源 |\n|---|---|---|---|\n| 用 A | 因为 B | 放弃 C | 代码注释 |",
        )
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc)
        self.assertNotIn("缺少「来源」列", out)

    # 坑⑫：数量断言（N 个测试/模块）check 验不了，--stale 时应提示人去数
    def test_count_assertions_hinted_on_stale(self):
        doc = self.new()
        text = mod.set_section_body(
            doc.read_text(encoding="utf-8"), 2,
            "本项目有 19 个测试文件、4 个模块、8 个接口，已全部跑通。",
        )
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=True)
        self.assertIn("数量断言", out)

    def test_count_assertions_quiet_on_plain_check(self):
        doc = self.new()
        text = mod.set_section_body(
            doc.read_text(encoding="utf-8"), 2,
            "本项目有 19 个测试文件、4 个模块、8 个接口，已全部跑通。",
        )
        doc.write_text(text, encoding="utf-8")
        _, out = self.run_check(doc, stale=False)
        self.assertNotIn("数量断言", out)


class TestRootDetection(unittest.TestCase):
    """坑⑮：项目根标记只认 Python/Node/Go/Rust，从 Maven/CMake 子模块进去会认错根。"""

    def _root_from_subdir(self, marker, sub_parts):
        root = Path(tempfile.mkdtemp())
        (root / marker).write_text("x", encoding="utf-8")
        sub = root.joinpath(*sub_parts)
        sub.mkdir(parents=True)
        try:
            # find_root 内部会 resolve()，macOS 的 /var 是指向 /private/var 的软链，
            # 直接比 Path 会因符号链接不相等而误报
            self.assertEqual(mod.find_root(sub), root.resolve())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_maven(self):
        self._root_from_subdir("pom.xml", ("module", "src"))

    def test_gradle(self):
        self._root_from_subdir("settings.gradle.kts", ("app", "src"))

    def test_cmake(self):
        self._root_from_subdir("CMakeLists.txt", ("src", "core"))

    def test_composer(self):
        self._root_from_subdir("composer.json", ("src", "Http"))

    def test_git_wins_over_nested_build_file(self):
        """多模块：子模块有 pom.xml，但 .git 在更上层，应认 .git 那层。"""
        root = Path(tempfile.mkdtemp())
        (root / ".git").mkdir()
        (root / "pom.xml").write_text("x", encoding="utf-8")
        sub = root / "moduleA"
        sub.mkdir()
        (sub / "pom.xml").write_text("x", encoding="utf-8")
        try:
            # find_root 内部会 resolve()，macOS 的 /var 是指向 /private/var 的软链，
            # 直接比 Path 会因符号链接不相等而误报
            self.assertEqual(mod.find_root(sub), root.resolve())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestLatestBranch(unittest.TestCase):
    """缺陷⑱：latest 不区分分支，切分支后会读到另一条线的状态。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "requirements.txt").write_text("x", encoding="utf-8")
        self._git("init", "-q", "-b", "main")
        self._git("-c", "user.email=t@t", "-c", "user.name=t",
                  "commit", "-qm", "init", "--allow-empty")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True, text=True)

    def _new(self, slug):
        rc, _ = quiet(mod.cmd_new, Namespace(slug=slug, root=str(self.root), inherit=False))
        self.assertEqual(rc, 0)

    def test_warns_when_doc_belongs_to_other_branch(self):
        self._new("on-main")
        self._git("checkout", "-q", "-b", "dev")
        _, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertIn("当前在 dev 分支", out)

    def test_prefers_current_branch_document(self):
        self._new("on-main")
        self._git("checkout", "-q", "-b", "dev")
        self._new("on-dev")
        _, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertNotIn("当前在 dev 分支", out)
        self.assertIn("on-dev", out)

    def test_no_warning_when_single_branch(self):
        self._new("only-main")
        _, out = quiet(mod.cmd_latest, Namespace(root=str(self.root)))
        self.assertNotIn("当前在", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

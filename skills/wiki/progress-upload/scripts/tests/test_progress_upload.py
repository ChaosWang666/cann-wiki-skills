"""derive_op / derive_run_id / short_display_path 的最小验证（纯 stdlib unittest）。

运行：
    cd skills/wiki/progress-upload/scripts && python -m unittest discover -s tests -p 'test_*.py'
"""
import sys
import unittest
from pathlib import Path

# 让 `import progress_upload` 能在 tests/ 子目录下找到上一级的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from progress_upload import derive_op, derive_run_id, short_display_path  # noqa: E402


class DeriveOpTest(unittest.TestCase):
    def test_strips_progress_md_suffix(self):
        self.assertEqual(
            derive_op("/x/claude/run0/gemm_add_relu.progress.md"), "gemm_add_relu")

    def test_strips_plain_md_suffix(self):
        self.assertEqual(derive_op("/x/add.md"), "add")

    def test_explicit_op_wins(self):
        self.assertEqual(
            derive_op("/x/gemm_add_relu.progress.md", "custom_op"), "custom_op")

    def test_no_known_suffix_returns_basename(self):
        self.assertEqual(derive_op("/x/notes"), "notes")


class DeriveRunIdTest(unittest.TestCase):
    def test_parent_run_dir(self):
        self.assertEqual(
            derive_run_id("/x/claude/run0/gemm_add_relu.progress.md"), "run0")

    def test_parent_run_dir_multi_digit(self):
        self.assertEqual(derive_run_id("/x/claude/run12/op.progress.md"), "run12")

    def test_non_run_parent_returns_none(self):
        self.assertIsNone(derive_run_id("/x/output/op.progress.md"))

    def test_explicit_run_wins(self):
        self.assertEqual(
            derive_run_id("/x/claude/run0/op.progress.md", "retry"), "retry")


class ShortDisplayPathTest(unittest.TestCase):
    def test_absolute_path_reduced_to_two_segments(self):
        self.assertEqual(
            short_display_path("/data2/w/raw/sessions/progress/gemm_add_relu/run0.progress.md"),
            "gemm_add_relu/run0.progress.md",
        )

    def test_bare_filename_unchanged(self):
        self.assertEqual(short_display_path("run0.progress.md"), "run0.progress.md")

    def test_empty_path(self):
        self.assertEqual(short_display_path(""), "")


if __name__ == "__main__":
    unittest.main()

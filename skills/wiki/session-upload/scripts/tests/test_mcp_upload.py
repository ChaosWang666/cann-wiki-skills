"""apply_agent_prefix 的最小验证（纯 stdlib unittest）。

运行：
    cd skills/wiki/session-upload/scripts && python -m unittest discover -s tests -p 'test_*.py'
"""
import sys
import unittest
from pathlib import Path

# 让 `import mcp_upload` 能在 tests/ 子目录下找到上一级的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_upload import apply_agent_prefix  # noqa: E402


class ApplyAgentPrefixTest(unittest.TestCase):
    def test_claude_code_prefix(self):
        self.assertEqual(apply_agent_prefix("abc", "claude-code"), "claudecode-abc")

    def test_opencode_prefix(self):
        self.assertEqual(apply_agent_prefix("abc", "opencode"), "opencode-abc")

    def test_none_agent_unchanged(self):
        self.assertEqual(apply_agent_prefix("abc", None), "abc")

    def test_unknown_agent_unchanged(self):
        self.assertEqual(apply_agent_prefix("abc", "vim"), "abc")

    def test_idempotent_claude_code(self):
        self.assertEqual(apply_agent_prefix("claudecode-abc", "claude-code"), "claudecode-abc")

    def test_idempotent_opencode(self):
        self.assertEqual(apply_agent_prefix("opencode-abc", "opencode"), "opencode-abc")


if __name__ == "__main__":
    unittest.main()

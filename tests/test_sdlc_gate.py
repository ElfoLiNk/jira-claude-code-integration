"""tests/test_sdlc_gate.py — sdlc-gate.py 단위 테스트 (git은 임시 저장소, gh는 mock)

실행: python -m unittest tests.test_sdlc_gate
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sdlc_gate", REPO_ROOT / "scripts" / "sdlc-gate.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)  # type: ignore[union-attr]

AGENTS = """# AGENTS

## 승인자

| 역할 | 담당 |
|---|---|
| 제품 책임자 | @po-kim |
| 기술 책임자 | @tech-lee, @arch-park |
| 릴리스 담당 | @ |

## 검사
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def pr(comments, author="dev-choi", draft=True, state="OPEN"):
    return {"number": 7, "url": "https://gh/pr/7", "state": state, "isDraft": draft,
            "author": {"login": author}, "headRefName": "feature/K-1", "baseRefName": "main",
            "mergeCommit": None,
            "comments": [{"author": {"login": a}, "body": b, "createdAt": f"2026-10-16T0{i}:00:00Z"}
                         for i, (a, b) in enumerate(comments)],
            "reviews": []}


class TokenTest(unittest.TestCase):
    def test_detects_token_lines(self):
        self.assertTrue(m.contains_approval_token("좋습니다\nAPPROVE plan 3f1b7d5"))
        self.assertTrue(m.contains_approval_token("> `approve spec abcdef0`"))

    def test_ignores_prose_and_placeholder(self):
        self.assertFalse(m.contains_approval_token("plan을 APPROVE plan 형식으로 승인해 주세요"))
        self.assertFalse(m.contains_approval_token("APPROVED"))
        self.assertFalse(m.contains_approval_token("다음 한 줄을 남겨 주세요:\nAPPROVE plan <SHA>\n(SHA = 3f1b7d5)"))

    def test_parse_requires_sha(self):
        self.assertEqual(m.parse_approvals("APPROVE plan\nAPPROVE Spec ABCDEF0"), [("spec", "abcdef0")])


class TableTest(unittest.TestCase):
    def test_parse_table(self):
        t = m.parse_approver_table(AGENTS)
        self.assertEqual(t, {"제품 책임자": ["po-kim"], "기술 책임자": ["tech-lee", "arch-park"]})

    def test_missing_table(self):
        self.assertEqual(m.parse_approver_table("# x\n## 검사\n"), {})

    def test_codeowners_skips_teams(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".github").mkdir()
            (Path(d) / ".github" / "CODEOWNERS").write_text("* @owner-a @org/team  # @not-me\n", encoding="utf-8")
            self.assertEqual(m.parse_codeowners(Path(d)), ["owner-a"])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.cwd = os.getcwd()
        git(self.d, "init", "-q", "-b", "main")
        git(self.d, "config", "user.email", "t@t")
        git(self.d, "config", "user.name", "t")
        Path(self.d, "AGENTS.md").write_text(AGENTS, encoding="utf-8")
        Path(self.d, ".jira-context.json").write_text(json.dumps({"branch": "feature/K-1", "level": "L2"}), encoding="utf-8")
        w = Path(self.d, "work", "K-1")
        w.mkdir(parents=True)
        (w / "spec.md").write_text("spec v1", encoding="utf-8")
        (w / "plan.md").write_text("plan v1", encoding="utf-8")
        git(self.d, "add", "AGENTS.md", "work")
        git(self.d, "commit", "-qm", "docs(K-1): spec·plan")
        self.sha = git(self.d, "rev-parse", "--short=7", "HEAD")
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_check(self, comments, artifact="plan", level=None, risk=None, author="dev-choi"):
        with mock.patch.object(m, "fetch_pr", return_value=pr(comments, author=author)):
            return m.check("K-1", artifact, level, risk)

    def test_l2_plan_by_pr_author(self):
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 0, out)
        self.assertEqual(out["approver"], "dev-choi")
        self.assertEqual(out["files"], ["work/K-1/spec.md", "work/K-1/plan.md"])

    def test_risk_requires_tech_lead(self):
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")], risk=True)
        self.assertEqual(code, 1)
        self.assertEqual(out["rejected"][0]["reason"], "승인자 목록에 없는 계정")
        code, out = self.run_check([("arch-park", f"APPROVE plan {self.sha}")], risk=True)
        self.assertEqual(code, 0, out)

    def test_change_after_approval_invalidates(self):
        Path(self.d, "work", "K-1", "spec.md").write_text("spec v2", encoding="utf-8")
        git(self.d, "commit", "-qam", "docs(K-1): AC 변경")
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 1)
        self.assertIn("work/K-1/spec.md", out["rejected"][0]["reason"])

    def test_unrelated_commit_after_approval_ok(self):
        Path(self.d, "src.txt").write_text("x", encoding="utf-8")
        git(self.d, "add", "src.txt")
        git(self.d, "commit", "-qm", "test(K-1): 실패 테스트")
        code, _ = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 0)

    def test_rebased_branch_keeps_approval_when_artifacts_identical(self):
        # 승인 뒤 다른 base 위로 rebase: 승인 SHA는 이력에서 빠지지만 spec·plan 내용은 같다
        git(self.d, "checkout", "-q", "-b", "other", "HEAD~0")
        git(self.d, "checkout", "-q", "--orphan", "newbase")
        git(self.d, "rm", "-rqf", ".")
        Path(self.d, "base.txt").write_text("b", encoding="utf-8")
        git(self.d, "add", "base.txt")
        git(self.d, "commit", "-qm", "base")
        git(self.d, "checkout", "-q", "other", "--", "AGENTS.md", "work")
        git(self.d, "commit", "-qm", "docs(K-1): spec·plan (rebased)")
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 0, out)
        Path(self.d, "work", "K-1", "plan.md").write_text("plan v2", encoding="utf-8")
        git(self.d, "commit", "-qam", "docs(K-1): plan 수정")
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 1)
        self.assertIn("work/K-1/plan.md", out["rejected"][0]["reason"])

    def test_unknown_sha(self):
        code, out = self.run_check([("dev-choi", "APPROVE plan deadbee")])
        self.assertEqual(code, 1)
        self.assertIn("찾을 수 없다", out["rejected"][0]["reason"])

    def test_wrong_artifact_ignored(self):
        code, out = self.run_check([("dev-choi", f"APPROVE intent {self.sha}")])
        self.assertEqual(code, 1)
        self.assertEqual(out["rejected"], [])

    def test_l3_spec_needs_product_owner(self):
        code, _ = self.run_check([("dev-choi", f"APPROVE spec {self.sha}")], artifact="spec", level="L3")
        self.assertEqual(code, 1)
        code, out = self.run_check([("po-kim", f"APPROVE spec {self.sha}")], artifact="spec", level="L3")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["files"], ["work/K-1/spec.md"])

    def test_l2_spec_rejected_as_usage_error(self):
        with self.assertRaises(m.GateError):
            self.run_check([], artifact="spec")

    def test_l1_has_no_gate(self):
        with self.assertRaises(m.GateError):
            self.run_check([], level="L1")

    def test_no_table_falls_back_with_warning(self):
        Path(self.d, "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        code, out = self.run_check([("dev-choi", f"APPROVE plan {self.sha}")])
        self.assertEqual(code, 0, out)
        self.assertTrue(out["warnings"])

    def test_pr_state(self):
        conflicting = pr([], draft=False)
        conflicting["mergeable"] = "CONFLICTING"
        with mock.patch.object(m, "fetch_pr", return_value=conflicting):
            st = m.pr_state("K-1")
            self.assertEqual((st["state"], st["mergeable"]), ("ready", "CONFLICTING"))
        merged = pr([], state="MERGED")
        merged["mergeCommit"] = {"oid": "abc"}
        with mock.patch.object(m, "fetch_pr", return_value=merged):
            self.assertEqual(m.pr_state("K-1")["mergeCommit"], "abc")
        with mock.patch.object(m, "fetch_pr", return_value=None):
            self.assertEqual(m.pr_state("K-1"), {"state": "none"})


if __name__ == "__main__":
    unittest.main()

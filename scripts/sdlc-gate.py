#!/usr/bin/env python3
"""sdlc-gate.py — 산출물 승인과 PR 상태를 GitHub·git의 사실로 판정한다 (v0.70.0+).

"승인됐는지"를 LLM이 판단하지 않게 하려는 스크립트다 (SD-COM-AUT-004, GAT-005).

Usage (작업 worktree에서 실행):
    python3 sdlc-gate.py check <KEY> <intent|spec|plan> [--level L1|L2|L3] [--risk|--no-risk]
    python3 sdlc-gate.py pr-state <KEY>         {state, number, url, base, head, mergeable, mergeCommit}
    python3 sdlc-gate.py scan-token < text      승인 토큰이 있으면 exit 1 (코멘트 작성 경로 차단용)

승인 코멘트 형식 (PR 코멘트나 리뷰 본문의 한 줄):
    APPROVE <intent|spec|plan> <커밋 SHA 7자 이상>

check 판정 — 아래를 모두 만족하는 코멘트가 하나라도 있으면 통과:
    1. 작성자가 그 산출물의 승인자다
         intent             제품 책임자
         spec (L3)          제품 책임자
         plan               작업 담당자(PR 작성자) 또는 기술 책임자. 위험 신호가 있으면 기술 책임자만
       L2는 spec과 plan을 함께 승인하므로 `APPROVE plan`이 spec.md·plan.md 둘 다를 덮는다.
       승인자 목록은 프로젝트 AGENTS.md "## 승인자" 표의 @계정. 표가 없거나 비었으면
       PR 작성자 또는 CODEOWNERS 계정을 인정하고 warnings에 남긴다.
    2. SHA 커밋이 저장소에 있다.
    3. 그 SHA 시점의 대상 파일(work/<KEY>/<artifact>.md)과 HEAD의 대상 파일이 같다.
       승인은 산출물 내용에 대한 것이라, stacked 재정렬이나 base 충돌 해결 rebase로 SHA가 이력에서 빠져도
       내용이 같으면 승인은 유효하다. 내용이 바뀌었으면 재승인이 필요하다.

--level / --risk를 생략하면 worktree-local .jira-context.json의 level / riskSignals를 쓴다.

Output: JSON 한 줄.
Exit:   check — 0 통과 / 1 미통과 / 2 오류(gh·git 실패, 인자, PR 없음)
        pr-state — 0 / 2
        scan-token — 0 토큰 없음 / 1 토큰 있음
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ARTIFACTS = ("intent", "spec", "plan")

# 코멘트 작성 경로(jira-cli.py comment, hooks/scripts/guard-approval.js)도 같은 패턴으로 막는다.
# SHA가 붙어야 유효한 승인이라, 승인 요청 코멘트의 "APPROVE plan <SHA>" 안내는 걸리지 않는다.
APPROVAL_RE = re.compile(r"^[ \t>*_`]*APPROVE[ \t]+(intent|spec|plan)[ \t]+([0-9a-fA-F]{7,40})\b", re.I | re.M)

ROLE_PRODUCT = "제품 책임자"
ROLE_TECH = "기술 책임자"


class GateError(Exception):
    pass


def contains_approval_token(text: str) -> bool:
    return bool(APPROVAL_RE.search(text or ""))


def parse_approvals(text: str) -> list[tuple[str, str]]:
    """본문에서 (artifact, sha) 목록을 뽑는다."""
    return [(a.lower(), s.lower()) for a, s in APPROVAL_RE.findall(text or "")]


# ---------------------------------------------------------------- 외부 호출

def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def _gh_json(args: list[str]) -> dict:
    try:
        p = _run(["gh", *args])
    except FileNotFoundError:
        raise GateError("gh CLI가 없다")
    if p.returncode != 0:
        raise GateError(f"gh {' '.join(args[:3])} 실패: {p.stderr.strip()}")
    return json.loads(p.stdout or "{}")


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return _run(["git", *args])


def _repo_root() -> Path:
    p = _git(["rev-parse", "--show-toplevel"])
    if p.returncode != 0:
        raise GateError("git 저장소 안에서 실행해야 한다")
    return Path(p.stdout.strip())


# ---------------------------------------------------------------- 입력 읽기

def load_context(root: Path) -> dict:
    f = root / ".jira-context.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_approver_table(agents_md: str) -> dict[str, list[str]]:
    """AGENTS.md "## 승인자" 표 → {역할: [login...]}. 표가 없으면 {}."""
    m = re.search(r"^##[ \t]+승인자[ \t]*$(.*?)(?=^#{1,2}[ \t]|\Z)", agents_md, re.M | re.S)
    if not m:
        return {}
    table: dict[str, list[str]] = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not line.lstrip().startswith("|") or set(cells[0]) <= set("-: "):
            continue
        logins = re.findall(r"@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)(?![/\w-])", cells[1])
        if logins:
            table[cells[0]] = [x.lower() for x in logins]
    return table


def parse_codeowners(root: Path) -> list[str]:
    for rel in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        f = root / rel
        if f.is_file():
            text = re.sub(r"#.*", "", f.read_text(encoding="utf-8"))
            # @org/team은 개인 계정이 아니라 건너뛴다
            return sorted({x.lower() for x in re.findall(r"@([A-Za-z0-9-]+)(?![/\w-])", text)})
    return []


def fetch_pr(branch: str) -> dict | None:
    try:
        return _gh_json(["pr", "view", branch, "--json",
                         "number,url,state,isDraft,mergeable,author,headRefName,baseRefName,mergeCommit,comments,reviews"])
    except GateError as e:
        if "no pull requests found" in str(e).lower():
            return None
        raise


# ---------------------------------------------------------------- 판정

def approvers_for(artifact: str, risk: bool, table: dict[str, list[str]],
                  pr_author: str, codeowners: list[str]) -> tuple[set[str], list[str]]:
    warnings: list[str] = []
    product = set(table.get(ROLE_PRODUCT, []))
    tech = set(table.get(ROLE_TECH, []))
    if not table:
        warnings.append("AGENTS.md 승인자 표가 없어 PR 작성자·CODEOWNERS 계정의 승인을 인정했다")
        return {pr_author, *codeowners} - {""}, warnings
    if artifact == "plan":
        allowed = tech if risk else {pr_author} | tech
        if risk and not tech:
            warnings.append("위험 신호가 있지만 AGENTS.md에 기술 책임자 계정이 없다")
    else:  # intent, L3 spec
        allowed = product
        if not product:
            warnings.append("AGENTS.md에 제품 책임자 계정이 없다")
    return allowed - {""}, warnings


def target_files(key: str, artifact: str, level: str) -> list[str]:
    if artifact == "plan" and level == "L2":
        return [f"work/{key}/spec.md", f"work/{key}/plan.md"]
    return [f"work/{key}/{artifact}.md"]


def check_sha(sha: str, files: list[str]) -> str | None:
    """통과면 None, 아니면 사유."""
    p = _git(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"])
    if p.returncode != 0:
        return f"SHA {sha}를 찾을 수 없다"
    full = p.stdout.strip()
    for f in files:
        if _git(["cat-file", "-e", f"{full}:{f}"]).returncode != 0:
            return f"SHA {sha} 시점에 {f}가 없다"
    changed = _git(["diff", "--name-only", full, "HEAD", "--", *files]).stdout.split()
    if changed:
        return f"승인 이후 바뀐 파일: {', '.join(changed)} — 다시 승인받아야 한다"
    return None


def _entries(pr: dict) -> list[dict]:
    out = []
    for c in (pr.get("comments") or []) + (pr.get("reviews") or []):
        out.append({
            "author": ((c.get("author") or {}).get("login") or "").lower(),
            "body": c.get("body") or "",
            "at": c.get("createdAt") or c.get("submittedAt") or "",
            "url": c.get("url") or "",
        })
    return sorted(out, key=lambda e: e["at"], reverse=True)


def check(key: str, artifact: str, level: str | None, risk: bool | None) -> tuple[int, dict]:
    if artifact not in ARTIFACTS:
        raise GateError(f"artifact는 {'|'.join(ARTIFACTS)} 중 하나")
    root = _repo_root()
    ctx = load_context(root)
    level = (level or ctx.get("level") or "").upper()
    if level not in ("L2", "L3"):
        raise GateError(f"승인 게이트는 L2·L3만 있다 (level={level or '없음'})")
    if artifact != "plan" and level == "L2":
        raise GateError("L2는 spec·plan을 함께 승인한다 — check <KEY> plan을 쓴다")
    if risk is None:
        risk = bool(ctx.get("riskSignals"))

    pr = fetch_pr(ctx.get("branch") or f"feature/{key}")
    if pr is None:
        raise GateError(f"feature/{key} 브랜치의 PR이 없다")
    pr_author = ((pr.get("author") or {}).get("login") or "").lower()

    agents = root / "AGENTS.md"
    table = parse_approver_table(agents.read_text(encoding="utf-8")) if agents.is_file() else {}
    allowed, warnings = approvers_for(artifact, risk, table, pr_author, parse_codeowners(root))
    files = target_files(key, artifact, level)

    rejected = []
    for e in _entries(pr):
        for a, sha in parse_approvals(e["body"]):
            if a != artifact:
                continue
            if e["author"] not in allowed:
                rejected.append({"by": e["author"], "sha": sha, "reason": "승인자 목록에 없는 계정"})
                continue
            reason = check_sha(sha, files)
            if reason:
                rejected.append({"by": e["author"], "sha": sha, "reason": reason})
                continue
            return 0, {"ok": True, "artifact": artifact, "level": level, "approver": e["author"],
                       "sha": sha, "at": e["at"], "url": e["url"] or pr.get("url"),
                       "files": files, "warnings": warnings}
    return 1, {"ok": False, "artifact": artifact, "level": level, "pr": pr.get("url"),
               "allowed": sorted(allowed), "files": files, "rejected": rejected,
               "warnings": warnings, "howto": f"PR에 'APPROVE {artifact} <커밋 SHA>' 코멘트"}


def pr_state(key: str) -> dict:
    ctx = load_context(_repo_root())
    pr = fetch_pr(ctx.get("branch") or f"feature/{key}")
    if pr is None:
        return {"state": "none"}
    st = (pr.get("state") or "").upper()
    state = {"MERGED": "merged", "CLOSED": "closed"}.get(st) or ("draft" if pr.get("isDraft") else "ready")
    return {"state": state, "number": pr.get("number"), "url": pr.get("url"),
            "base": pr.get("baseRefName"), "head": pr.get("headRefName"),
            # MERGEABLE | CONFLICTING | UNKNOWN — 열린 PR이 base와 충돌하는지 (loop sync가 격리 판단에 쓴다)
            "mergeable": pr.get("mergeable"),
            "mergeCommit": (pr.get("mergeCommit") or {}).get("oid")}


# ---------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "scan-token":
            return 1 if contains_approval_token(sys.stdin.read()) else 0
        if cmd == "pr-state" and len(rest) == 1:
            print(json.dumps(pr_state(rest[0]), ensure_ascii=False))
            return 0
        if cmd == "check" and len(rest) >= 2:
            level = rest[rest.index("--level") + 1] if "--level" in rest else None
            risk = True if "--risk" in rest else False if "--no-risk" in rest else None
            code, out = check(rest[0], rest[1].lower(), level, risk)
            print(json.dumps(out, ensure_ascii=False))
            return code
    except GateError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))

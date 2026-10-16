#!/usr/bin/env python3
"""Update jira-context.json files (worktree-local and/or aggregate) for a workflow step.

Usage:
    python3 scripts/jira-context-update.py <TASK-ID> <step> <status> <ctx-file> [<ctx-file>...] [--patch '<json>']
    python3 scripts/jira-context-update.py --migrate-approach <ctx-file> [<ctx-file>...]
    python3 scripts/jira-context-update.py --prune-done <aggregate-ctx-file>

done 단계는 aggregate에서 해당 태스크 항목을 **제거**한다 (생명주기 종료 — 이력은 docs/run-log·review-log가 보유).
--prune-done은 이미 완료된 항목(completedSteps에 done 또는 status가 Done/완료류)을 일괄 제거하는 일회성 정리.

--patch '<json>' (v0.58.0): worktree-local 파일에 top-level 키를 병합한다. implSelfCheck / fixSelfCheck 객체에
    ranAt이 없으면 현재 UTC로 채운다. 값이 null이면 키를 지운다 (v0.70.0).
    aggregate에는 level / riskSignals / stackedOn만 해당 tasks[i]에 반영한다 (v0.70.0; 나머지는 pollution 규칙).
    v0.70.0 필드: level("L1"|"L2"|"L3"), riskSignals(위험 신호 번호 목록), activeRole("test-writer"|"implementer"|"verifier"),
    stackedOn({key, branch, sha} — 앞 태스크 브랜치 위에 쌓은 경우).

--cache-issue <file|-> (v0.70.0): `jira-cli.py get` 출력(JSON)을 worktree-local `cachedIssue`로 기록하고 fetchedAt을
    현재 UTC로 채운다. step "-"와 함께 쓰면 캐시만 갱신한다. aggregate에는 기록하지 않는다.

ctx-file이 없으면 stderr에 error를 내고 exit 1 (v0.70.0 — 잘못된 경로로 aggregate 갱신이 조용히 빠지는 것을 막는다).
    용도: impl/fix 단계가 self-check 기록과 completedSteps 갱신을 Bash 1회로 끝내기.
    step에 "-"를 주면 completedSteps 추가·타임스탬프 기록 없이 patch만 적용한다 (fix loop의 test/review 제거용).
    갱신 후 worktree 파일의 completedSteps를 `completedSteps=[...]`로 출력하므로 재-Read가 필요 없다.

The --migrate-approach mode is a one-shot migration (MAE-357): for each task
that has both 'plan' and 'design' in completedSteps but is missing 'approach',
inserts 'approach' after the later of the two. No-op if already migrated.

Args:
    TASK-ID    Jira issue key (e.g. MAE-279).
    step       Workflow step name to append to completedSteps (e.g. "verify", "done").
               Must be one of: discover, create, init, start, approach, test-write,
               impl, verify, pr, done. Also drives the timestamp field name:
               "<step>At" (e.g. mergedAt, doneAt).
    status     Value to set as top-level `status` and (if present) `cachedIssue.status`.
               **Must be a Jira-verified value** — caller is responsible for fetching
               the post-transition status from Jira (`jira_get_issue` after
               `jira_transition_issue`) and passing the actual `fields.status.name`.
               Do NOT pass the transition target name (e.g. "Done") as-is, since the
               resulting status may differ ("완료", "검토중", etc. depending on workflow).
               Pass "-" to keep the existing status fields untouched (used by
               record-only steps like approach/impl/review that don't transition Jira).
    ctx-file   One or more .jira-context.json paths. Format auto-detected:
               - Aggregate: {"tasks": [...], ...}  → updates the matching tasks[i] entry.
               - Worktree:  {"taskId": ..., ...}   → updates top-level fields.

Behavior:
    - completedSteps: appends `step` (no-op if already present).
    - status: replaced.
    - <step>At: set to current UTC ISO 8601 (Z suffix). TZ-naive timestamps are
      treated as stale by the dashboard reader.
    - cachedIssue.status / cachedIssue.fetchedAt: updated only when status != "-" and cachedIssue exists
      (never created from scratch — leave None as-is).

Exit codes:
    0  All requested files processed.
    1  One or more ctx-files were missing (the others are still processed).
    2  Wrong arg count.
"""

from __future__ import annotations

import datetime
import json
import os
import sys


# Valid workflow step whitelist. Keep in sync with skill SKILL.md Progress lines
# and dashboard SDLC_STEPS. `plan`/`design`은 통합되어 `approach`로 대체됨.
# v0.70.0: test → test-write + verify, review → verify, merge(local) 폐지.
VALID_STEPS = frozenset({
    "discover", "create", "init", "start", "approach",
    "test-write", "impl", "verify", "pr", "done",
})

# --patch에서 aggregate의 해당 tasks[i]에도 반영하는 키 (loop가 큐 전체를 보고 판단하는 값).
# activeRole 등 나머지는 worktree-local에만 둔다.
_AGGREGATE_PATCH_KEYS = frozenset({"level", "riskSignals", "stackedOn"})


def _now_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _apply_step(target: dict, step: str, status: str, ts: str) -> None:
    steps = target.get("completedSteps", [])
    if step not in steps:
        steps.append(step)
    target["completedSteps"] = steps
    target[f"{step}At"] = ts
    keep_status = status == "-"
    if not keep_status:
        target["status"] = status
    ci = target.get("cachedIssue")
    if isinstance(ci, dict) and not keep_status:
        # status는 transition 출력(Jira 확인값)이므로 그때만 신선도를 갱신한다 — record-only 단계가 fetchedAt을 덮으면 캐시가 실제보다 새것처럼 보인다
        ci["status"] = status
        ci["fetchedAt"] = ts


# Worktree-local fields that must never appear at the aggregate top level.
# A skill running with main-repo cwd can leak these into the aggregate
# (schema pollution); stripped on every aggregate update (self-healing).
# Step timestamps ("<step>At") are covered by the endswith check — the
# aggregate's own timestamp is "initialized" (no "At" suffix).
_AGGREGATE_POLLUTION_KEYS = frozenset({
    "taskId", "branch", "worktreePath", "summary", "priority",
    "status", "completedSteps", "cachedIssue", "parentEpic", "parentStory",
    "implSelfCheck", "fixSelfCheck",
    "level", "riskSignals", "stackedOn", "activeRole",
})


def _strip_aggregate_pollution(ctx: dict) -> list[str]:
    removed = sorted(
        k for k in ctx
        if k in _AGGREGATE_POLLUTION_KEYS or k.endswith("At")
    )
    for k in removed:
        del ctx[k]
    return removed


def _apply_patch(target: dict, patch: dict, ts: str) -> None:
    """top-level 키 병합. 값이 null이면 키를 지운다 (activeRole·stackedOn 해제용)."""
    for k, v in patch.items():
        if v is None:
            target.pop(k, None)
            continue
        if k in ("implSelfCheck", "fixSelfCheck") and isinstance(v, dict) and not v.get("ranAt"):
            v = {**v, "ranAt": ts}
        target[k] = v


def update_context(ctx_file: str, task_id: str, step: str, status: str, ts: str,
                   patch: dict | None = None) -> str:
    if not os.path.isfile(ctx_file):
        return f"missing: {ctx_file}"
    with open(ctx_file, "r", encoding="utf-8") as f:
        ctx = json.load(f)
    if isinstance(ctx.get("tasks"), list):
        removed = _strip_aggregate_pollution(ctx)
        if removed:
            print(
                f"warn: stripped worktree-local fields from aggregate top level: {removed}",
                file=sys.stderr,
            )
        updated = False
        if step == "done":
            # done = 생명주기 종료 → aggregate에서 항목 제거 (이력은 run-log/review-log가 보유).
            # worktree-local 파일은 clean이 worktree와 함께 정리한다.
            before = len(ctx["tasks"])
            ctx["tasks"] = [t for t in ctx["tasks"] if t.get("taskId") != task_id]
            updated = len(ctx["tasks"]) < before
        else:
            agg_patch = {k: v for k, v in (patch or {}).items() if k in _AGGREGATE_PATCH_KEYS}
            if step == "-" and not agg_patch and not removed:
                return f"aggregate unchanged (worktree-only patch): {ctx_file}"
            for t in ctx["tasks"]:
                if t.get("taskId") == task_id and (step != "-" or agg_patch):
                    if step != "-":
                        _apply_step(t, step, status, ts)
                    _apply_patch(t, agg_patch, ts)
                    updated = True
                    break
        if updated or removed:
            with open(ctx_file, "w", encoding="utf-8") as f:
                json.dump(ctx, f, indent=2, ensure_ascii=False)
        if updated and step == "done":
            return f"aggregate pruned ({task_id} done): {ctx_file}"
        if updated:
            return f"aggregate updated ({task_id}): {ctx_file}"
        return f"no {task_id} in aggregate, skipped: {ctx_file}"
    if step != "-":
        _apply_step(ctx, step, status, ts)
    _apply_patch(ctx, patch or {}, ts)
    with open(ctx_file, "w", encoding="utf-8") as f:
        json.dump(ctx, f, indent=2, ensure_ascii=False)
    steps = json.dumps(ctx.get("completedSteps", []), ensure_ascii=False)
    return f"worktree updated: {ctx_file}\ncompletedSteps={steps}"


def _migrate_target(t: dict) -> bool:
    """MAE-357 one-shot: insert 'approach' after plan+design when missing."""
    steps = t.get("completedSteps")
    if not isinstance(steps, list):
        return False
    if "plan" in steps and "design" in steps and "approach" not in steps:
        idx = max(steps.index("plan"), steps.index("design"))
        steps.insert(idx + 1, "approach")
        t["completedSteps"] = steps
        return True
    return False


def migrate_approach(ctx_file: str) -> str:
    if not os.path.isfile(ctx_file):
        return f"missing: {ctx_file}"
    with open(ctx_file, "r", encoding="utf-8") as f:
        ctx = json.load(f)
    migrated = 0
    if isinstance(ctx.get("tasks"), list):
        for t in ctx["tasks"]:
            if _migrate_target(t):
                migrated += 1
    elif _migrate_target(ctx):
        migrated = 1
    if migrated:
        with open(ctx_file, "w", encoding="utf-8") as f:
            json.dump(ctx, f, indent=2, ensure_ascii=False)
    return f"migrated {migrated} task(s): {ctx_file}"


_DONE_STATUSES = frozenset({"Done", "Closed", "완료", "종료"})


def prune_done(ctx_file: str) -> str:
    """aggregate에서 완료된 태스크 항목(completedSteps에 done 또는 status가 완료류)을 제거한다 (일회성 정리)."""
    if not os.path.isfile(ctx_file):
        return f"missing: {ctx_file}"
    with open(ctx_file, "r", encoding="utf-8") as f:
        ctx = json.load(f)
    if not isinstance(ctx.get("tasks"), list):
        return f"not an aggregate, skipped: {ctx_file}"
    keep, pruned = [], []
    for t in ctx["tasks"]:
        if "done" in (t.get("completedSteps") or []) or t.get("status") in _DONE_STATUSES:
            pruned.append(t.get("taskId"))
        else:
            keep.append(t)
    if pruned:
        ctx["tasks"] = keep
        with open(ctx_file, "w", encoding="utf-8") as f:
            json.dump(ctx, f, indent=2, ensure_ascii=False)
    return f"pruned {len(pruned)} done task(s) [{', '.join(str(p) for p in pruned)}]: {ctx_file}"


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--prune-done":
        for ctx_file in argv[2:]:
            print(prune_done(ctx_file))
        return 0
    if len(argv) >= 3 and argv[1] == "--migrate-approach":
        for ctx_file in argv[2:]:
            print(migrate_approach(ctx_file))
        return 0
    patch = None
    if "--patch" in argv:
        i = argv.index("--patch")
        if i + 1 >= len(argv):
            print("error: --patch requires a JSON argument", file=sys.stderr)
            return 2
        try:
            patch = json.loads(argv[i + 1])
        except ValueError as e:
            print(f"error: --patch JSON 파싱 실패: {e}", file=sys.stderr)
            return 2
        argv = argv[:i] + argv[i + 2:]
    if "--cache-issue" in argv:
        i = argv.index("--cache-issue")
        if i + 1 >= len(argv):
            print("error: --cache-issue requires a file path (or -)", file=sys.stderr)
            return 2
        src = argv[i + 1]
        try:
            text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
            issue = json.loads(text)
        except (OSError, ValueError) as e:
            print(f"error: --cache-issue 읽기 실패: {e}", file=sys.stderr)
            return 2
        patch = {**(patch or {}), "cachedIssue": {**issue, "fetchedAt": _now_utc_iso()}}
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    task_id, step, status = argv[1], argv[2], argv[3]
    if step == "-" and not patch:
        print("error: step '-' (record-only)는 --patch와 함께만 쓸 수 있다", file=sys.stderr)
        return 2
    if step != "-" and step not in VALID_STEPS:
        print(
            f"error: invalid step '{step}'. Valid steps: {sorted(VALID_STEPS)}",
            file=sys.stderr,
        )
        return 2
    ts = _now_utc_iso()
    rc = 0
    for ctx_file in argv[4:]:
        out = update_context(ctx_file, task_id, step, status, ts, patch)
        if out.startswith("missing: "):
            # 경로를 잘못 넘긴 것을 조용히 넘기지 않는다 — 없는 파일은 인자에서 빼고 호출한다
            print(f"error: {out}", file=sys.stderr)
            rc = 1
        else:
            print(out)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))

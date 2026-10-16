---
name: jira-task-done
description: "Complete a Jira task after its PR is merged — confirms the merge on GitHub, posts the merge commit, and transitions the issue to Done. Triggers: jira-task done, complete task; 작업 완료, 태스크 완료."
user-invocable: false
argument-hint: "<TASK-ID>"
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# jira-task-done: 머지 확인 후 완료

**Language Rule**: 프로젝트 CLAUDE.md의 Conventions 섹션 참고 (한국어 출력, Jira 코멘트 제목은 영어).

## Overview

PR이 기본 브랜치에 **머지된 것을 GitHub에서 확인한 뒤에만** Jira를 완료로 옮긴다. 머지는 코드 오너가 한다(SD-COM-ROL-003). `loop sync`도 같은 절차를 태스크마다 부른다.

## Workflow

Jira 호출은 `python3 "<scripts>/jira-cli.py" …` (`skills/_shared/jira-cli.md`). 경로가 prompt에 없으면 `skills/_shared/script-lookup.md`로 해석한다.

### Step 1: 머지 확인

```bash
python3 "<scripts>/sdlc-gate.py" pr-state <TASK-ID>
```

- `state != "merged"`면 **거부**하고 멈춘다: `PR이 아직 머지되지 않았습니다 (<state>). 코드 오너가 머지한 뒤 다시 실행하세요.` draft면 `/jira-task pr <TASK-ID>`로 상태를 안내한다.
- `merged`면 `mergeCommit`(SHA)과 `url`을 이후 단계에 쓴다.
- context가 없으면(worktree를 이미 지움) 메인 레포에서 실행해도 된다 — `pr-state`는 브랜치 이름으로 PR을 찾는다.

### Step 2: 완료 코멘트

요약 출처는 다시 계산하지 않고 인용한다: L2·L3는 `work/<TASK-ID>/spec.md`의 수용 조건 수와 `evidence/verification.md`의 판정, L1은 PR 본문 "변경 내용"·"검증". 파일이 기본 브랜치로 옮겨갔으면 `git show <mergeCommit>:work/<TASK-ID>/...`로 읽는다.

```markdown
## Task Completed
- PR: <URL> (머지됨)
- 머지 커밋: <mergeCommit>
- 등급: <L1|L2|L3> / 수용 조건 <n>/<n> 충족
- 산출물: `work/<TASK-ID>/` (L2·L3)
```

### Step 3: 전이

```bash
python3 "<scripts>/jira-cli.py" transitions <TASK-ID>
python3 "<scripts>/jira-cli.py" transition <TASK-ID> "<Done|완료 류 id>"
```
`Read skills/_shared/transition-verify.md` — `transition` 출력의 `status`가 `<final-jira-status>`다. 실패하면 가능한 전이 목록을 보여 주고 멈춘다.

### Step 4: 워크트리 MCP 설정 정리

context `worktreePath`가 있으면:
```bash
SCRIPT_NAME="cleanup-worktree-mcp.py" OUT_VAR="CLEANUP_MCP_PY"
# Read skills/_shared/script-lookup.md and execute its lookup block here
[ -n "$CLEANUP_MCP_PY" ] && python3 "$CLEANUP_MCP_PY" "<worktreePath>"
```

### Step 5: context와 요약

```bash
python3 "$JIRA_CTX_UPDATE_PY" <TASK-ID> done "<final-jira-status>" \
    "<worktreePath>/.jira-context.json" \
    "<repoRoot>/.jira-context.json"
```
aggregate에서는 해당 태스크 항목이 제거된다(이력은 `docs/run-log`·`docs/review-log`). worktree 파일이 없으면 그 인자만 뺀다.

```
---
✅ **Task Done** — <TASK-ID>

- PR 머지 확인: <mergeCommit 7자>
- Jira 상태: <final-jira-status>

**Progress**: init → start → approach → test-write → impl → verify → pr → **done ✓**

**Next**: `/jira-task clean <TASK-ID>` — worktree와 브랜치 정리
---
```

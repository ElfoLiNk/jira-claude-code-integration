---
name: jira-task-pr
description: "Regenerate the standard PR body for a Jira task and sync PR state to Jira (draft → review requested → In Review). Triggers: jira-task pr, PR 본문, PR 상태; PR 만들어, PR 갱신."
user-invocable: false
argument-hint: "<TASK-ID>"
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# jira-task-pr: PR 본문 재생성과 상태 반영

**Language Rule**: 프로젝트 CLAUDE.md의 Conventions 섹션 참고 (한국어 출력, Jira 코멘트 제목은 영어).

## Overview

v0.70.0부터 PR은 흐름 안에서 열린다(L2·L3는 approach, L1은 impl). 이 명령은 두 가지를 한다.

1. 표준 양식으로 PR 본문을 다시 만든다(없으면 draft로 연다).
2. PR 상태를 읽어 Jira에 반영한다. 사람이 draft를 풀었으면(리뷰 요청) Jira를 "검토 중"으로 옮기고 `pr`을 기록한다.

에이전트는 draft를 풀지 않는다(SD-COM-ROL-005). 로컬 병합은 없다(SD-COM-AUT-005).

## Workflow

Jira 호출은 `python3 "<scripts>/jira-cli.py" …` (`skills/_shared/jira-cli.md`). 경로가 prompt에 없으면 `skills/_shared/script-lookup.md`로 해석한다.

### Step 1: 본문 재생성

context(`level`, `riskSignals`, `planApproval`, `testExpectationChanges`, `knowledgeTransfer`, `verifyResult`, `stackedOn`)와 `work/<TASK-ID>/`를 읽고 `Read skills/_shared/pr-body.md`대로 PR을 만들거나 본문을 갱신한다.

### Step 2: 상태 확인

```bash
python3 "<scripts>/sdlc-gate.py" pr-state <TASK-ID>   # {"state": draft|ready|merged|closed|none, "number", "url", "mergeCommit"}
```

| state | 할 일 |
|---|---|
| draft | 검증 통과(context `verifyResult.result`)면 `gh pr ready <번호>`를 사람이 실행하도록 안내. 아니면 다음 단계(verify 등) 안내 |
| ready | Step 3 |
| merged | `/jira-task done <TASK-ID>` 안내 |
| closed | 머지 없이 닫힘 — 사용자에게 알리고 멈춘다 |

### Step 3: 리뷰 요청 반영 (state = ready)

`completedSteps`에 `pr`이 이미 있으면 건너뛴다.

```bash
python3 "<scripts>/jira-cli.py" transitions <TASK-ID>
python3 "<scripts>/jira-cli.py" transition <TASK-ID> "<In Review|검토 중 류 id>"   # 출력 status = 실제 상태
python3 "<scripts>/jira-cli.py" comment <TASK-ID> "## Review Requested
- PR: <URL>
- base: <base> ← feature/<TASK-ID>"
python3 "$JIRA_CTX_UPDATE_PY" <TASK-ID> pr "<전이 후 status>" \
    "<worktree>/.jira-context.json" "<repoRoot>/.jira-context.json"
```
전이 실패는 경고 후 계속한다(`skills/_shared/transition-verify.md`).

### Step 4: 요약

```
---
🔗 **PR** — <TASK-ID>

- PR: <URL> (<draft | 리뷰 요청됨 | 머지됨>)
- 본문 갱신됨
- Jira: <변화 없음 | 검토 중으로 전이>

**Progress**: init → start → approach → test-write → impl → verify → **pr** → done

**Next**: <draft: 확인 후 `gh pr ready <번호>` | 리뷰 요청됨: 코드 오너 머지 대기 | 머지됨: `/jira-task done <TASK-ID>`>
---
```

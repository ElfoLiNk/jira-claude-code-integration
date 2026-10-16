---
name: jira-task-loop
description: "Drain the initialized Jira task queue in passes around human gates — prep (confirm levels), plan (L2/L3 artifacts → approval wait), build (test-write → impl → verify), sync (PR state → Jira, restack). Triggers: jira-task loop; 루프 실행, 큐 소진."
user-invocable: false
argument-hint: "[prep|plan|build|sync]"
allowed-tools:
  - Read
  - Edit
  - Bash
  - Skill
  - AskUserQuestion
  - EnterWorktree
  - ExitWorktree
---

# jira-task-loop: 사람 게이트 기준 패스

**Language Rule**: 프로젝트 CLAUDE.md의 Conventions 섹션 참고 (한국어 출력, Jira 코멘트 제목은 영어).

## Overview

init된 태스크 큐를 **사람 게이트 단위의 패스**로 돈다. `auto`가 한 태스크 안에서 다음 게이트까지 가는 것이라면, `loop`는 큐 전체를 같은 게이트까지 밀어 두고 사람이 할 일을 한 번에 모아 보여 준다.

| 패스 | 대상 | 하는 일 |
|---|---|---|
| `prep` | 등급 없는 태스크 | 등급을 표로 제안하고 한 번에 확정 |
| `plan` | L2·L3 중 plan 승인 전 | 태스크마다 auto → 승인 대기 (L1은 건너뜀) |
| `build` | L1 + plan 승인된 L2·L3 | 태스크마다 auto → 리뷰 요청 준비됨 |
| `sync` | PR이 있는 태스크 | PR 상태 → Jira 반영(검토 중·완료), stacked 브랜치 재정렬 |

인자 없이 부르면 `prep → sync → plan → build` 순서로 모두 돈다. 패스 이름을 주면 그 패스만 돈다.

- 에이전트 코드는 PR로만 들어간다. 로컬 병합, draft 해제, 머지는 하지 않는다(SD-COM-AUT-005, ROL-005).
- **태스크-로컬 실패는 격리하고 계속, 시스템 실패만 전체 중단**(Step 6). 설계: `tasks/loop-quarantine-design.md`, `tasks/sdlc-alignment-design.md` §9.
- 재진입 가능: 큐와 각 태스크 위치는 매번 context·Jira·GitHub에서 다시 계산한다.
- **오케스트레이터는 가볍게.** context 읽기, Skill 호출, git·gh 명령, 판정만 한다. 산출물 본문을 컨텍스트로 가져오지 않는다.

## Step 1: 큐 로드

1. cwd의 `.jira-context.json`을 Read한다. `tasks[]`가 없으면(worktree-local) `repoRoot`로 `<repoRoot>/.jira-context.json`을 다시 Read한다. `REPO_ROOT`와 aggregate **절대 경로**를 여기서 확정한다 — 이후 모든 aggregate Read/Edit은 이 경로로 한다.
2. aggregate가 없거나 `tasks[]`가 비면 중단: `❌ Loop 실행 불가: init된 태스크 큐가 없습니다. 먼저 /jira-task init [count|ISSUE-KEY]로 작업 환경을 세팅하세요.`
3. `deferred`/`deferredKind`/`deferredReason`이 남아 있으면 셋 다 지운다(Edit) — 새 run은 보류 태스크를 재시도한다.
4. 큐 = `tasks[]` 중 Done이 아닌 태스크, 배열 순서(init이 priority 순으로 기록).
5. 스크립트 경로를 1회 해석한다: `Read skills/_shared/script-lookup.md`의 Batch Lookup으로 `jira-cli.py sdlc-gate.py jira-context-update.py append-run-log.py`.

```
🔁 Loop: <N>개 태스크 — 패스: <prep → sync → plan → build | 지정 패스>
```

## Step 2: prep — 등급 일괄 확정

`level`이 없는 태스크만 대상이다. 이슈 라벨에 `sdlc-L*`가 이미 있으면 context에만 기록한다.

1. 태스크마다 `jira-cli.py get <KEY>`로 요약·설명·AC를 읽고 `skills/_shared/sdlc-level.md`의 판정 질문으로 제안한다.
2. 한 표로 보여 준다: `KEY | 요약 | 제안 등급 | 위험 신호 | 근거 한 줄`.
3. `AskUserQuestion`(없으면 텍스트)으로 "제안대로 확정 / 일부 수정 / 건너뜀"을 받는다. 수정은 `KEY=L2` 형식으로 받는다.
4. 확정된 태스크마다 `sdlc-level.md` "기록"(라벨·코멘트·`--patch` — worktree-local과 aggregate 둘 다)을 한다. 확정 안 된 태스크는 이번 run의 plan·build에서 빠지고 리포트 "등급 확정 대기"에 남는다.

## Step 3: sync — PR 상태 반영과 재정렬

PR이 있을 수 있는 태스크(`completedSteps`에 `approach` 또는 `impl`)마다 worktree에서:

```bash
cd "<worktreePath>" && python3 "<sdlc-gate.py>" pr-state <KEY>
```

| state | 할 일 |
|---|---|
| merged | `Skill({ skill: "jira-integration:jira-task-done", args: "<KEY>" })` — 머지 커밋 코멘트, 완료 전이, aggregate에서 제거 |
| ready + `pr` 미기록 | `Skill({ skill: "jira-integration:jira-task-pr", args: "<KEY>" })` — Jira 검토 중 전이 |
| draft·ready(기록됨) | 변화 없음 |
| closed | 격리 `pr-closed` |

이어서 **stacked 재정렬**: context `stackedOn`이 있는 태스크마다 앞 태스크 PR(`stackedOn.key`)의 `pr-state`가 `merged`면 (rebase merge는 앞 커밋 SHA를 바꾸므로 분기 시점에 기록해 둔 `stackedOn.sha`가 기준이다):

```bash
git -C "<worktreePath>" fetch origin <base>
git -C "<worktreePath>" rebase --onto origin/<base> <stackedOn.sha> feature/<KEY>
git -C "<worktreePath>" push --force-with-lease origin feature/<KEY>
gh pr edit feature/<KEY> --base <base>
python3 "<jira-context-update.py>" <KEY> - - "<worktree ctx>" "<aggregate>" --patch '{"stackedOn":null}'
```

worktree가 dirty이거나 rebase가 충돌하면 `git -C "<worktreePath>" rebase --abort 2>/dev/null || true` 후 격리 `restack-conflict`. 앞 PR이 아직 열려 있으면 그대로 둔다.

## Step 4: plan — 산출물과 승인 요청

대상: `level`이 L2·L3이고 `completedSteps`에 `approach`가 없거나, L3로 intent·spec 단계에 있는 태스크(context로는 구분이 안 되므로 `approach` 미기록 L2·L3 전부).

태스크마다 Step 7의 **실행 절차**로 auto를 부른다. 기대 결과는 `awaiting_approval`이다(그 외 status는 Step 7 표로 처리). 이 패스는 독립·의존 구분 없이 산출물만 쓴다 — 산출물은 문서라 base와 충돌하지 않는다.

## Step 5: build — 구현과 검증

대상: L1(`verify` 미기록) + `approach`가 기록된 L2·L3 중 승인된 태스크. 승인은 auto 전에 main 세션에서 확인해 헛도는 sub-agent를 줄인다:

```bash
cd "<worktreePath>" && python3 "<sdlc-gate.py>" check <KEY> plan   # exit 0만 대상, 1은 리포트 "plan 승인 대기", 2는 격리 gate-error
```
context에 `planApproval`이 이미 있으면 확인을 건너뛴다.

### 5-a. 순서와 의존

큐 안에서 Jira `is blocked by`가 큐의 다른 태스크를 가리키면 의존 태스크다(`jira-cli.py get <KEY> --fields issuelinks`). 앞 태스크를 먼저 처리하도록 순서를 바꾼다. 앞 태스크가 이번 run에서 격리되면 의존 태스크도 격리 `predecessor-deferred`.

### 5-b. base 맞추기 (auto 전에, test-write 커밋이 생기기 전)

- **독립 태스크**: `origin/<base>` 최신 위로 옮긴다.
  ```bash
  git -C "<worktreePath>" fetch origin <base>
  git -C "<worktreePath>" rebase origin/<base>
  ```
- **의존 태스크, 앞 PR이 머지됨**: 독립 태스크와 같다.
- **의존 태스크, 앞 PR이 아직 열림**: 앞 브랜치 위에 쌓는다.
  ```bash
  PREV_SHA=$(git -C "<worktreePath>" rev-parse feature/<앞 KEY>)
  git -C "<worktreePath>" rebase feature/<앞 KEY>
  python3 "<jira-context-update.py>" <KEY> - - "<worktree ctx>" "<aggregate>" \
      --patch '{"stackedOn":{"key":"<앞 KEY>","branch":"feature/<앞 KEY>","sha":"'"$PREV_SHA"'"}}'
  ```
  PR이 이미 있으면(L2·L3) `git push --force-with-lease`와 `gh pr edit feature/<KEY> --base feature/<앞 KEY>`. PR 본문의 stacked 문구는 auto가 갱신한다(`skills/_shared/pr-body.md`).

충돌하면 `rebase --abort` 후 격리 `restack-conflict`.

### 5-c. auto

Step 7의 실행 절차로 auto를 부른다. 기대 결과는 `completed`(리뷰 요청 준비됨)다.

## Step 6: 격리와 시스템 실패

**격리**: EnterWorktree 상태면 먼저 `ExitWorktree({ action: "keep" })`. aggregate 해당 항목에 Edit:
```json
"deferred": true,
"deferredKind": "<scope-shortfall | gate-exhausted | stage-failed | test-dispute | gate-error | restack-conflict | predecessor-deferred | pr-closed>",
"deferredReason": "<한 줄 — auto/git/gh 출력 기반 실제 사유>"
```
worktree 작업 트리와 Jira는 건드리지 않는다. 같은 run 안에서 재시도하지 않는다. 출력: `⛔ <KEY> 격리 [<kind>]: <사유> — 다음 태스크로 계속합니다.`

**시스템 실패** — 아래면 전체 중단하고 보고한다(아니면 격리):
1. 서로 다른 태스크가 같은 `failedStage`로 연속 2건 실패.
2. 인프라 시그니처: HTTP 401/403·`Unauthorized`·`authentication`, `gh auth` 실패, base 브랜치 fetch·상태 복구 실패. 목록은 보수적으로 짧게 유지한다.

```
❌ Loop 중단 (시스템 실패 의심): <근거>
마지막 실패: <KEY> — <사유>
이번 run 결과: <패스별 처리 목록> / 격리: <목록> / 남은 큐: <목록>
원인을 해결한 뒤 /jira-task loop를 재실행하세요.
```

## Step 7: auto 실행 절차 (plan·build 공통)

1. **세션 cwd를 worktree로**: Bash `cd`가 아니라 `EnterWorktree({ path: "<worktreePath>" })`. auto launcher의 Read와 Workflow stage agent는 세션 cwd를 본다. EnterWorktree 안에서는 auto 호출과 단순 명령만 하고, git 재정렬·aggregate Edit은 `ExitWorktree({ action: "keep" })`로 main에 돌아와서 한다.
2. `Skill({ skill: "jira-integration:jira-task-auto", args: "<KEY>" })` — 등급이 있으므로 auto는 묻지 않는다.
3. worktree `docs/run-log/_index.jsonl` 마지막 줄(해당 taskId)의 `status`/`failedStage`/`reason`으로 결과를 판정한다(없으면 auto 출력의 status 키워드).

| auto status | 처리 |
|---|---|
| `awaiting_approval` | 리포트 "plan 승인 대기" (`awaitingKind=answers`면 같은 칸에 "질문 답변 필요"로) |
| `completed` | 리포트 "draft 해제 대기" |
| `level_unconfirmed` | 리포트 "등급 확정 대기" |
| `scope_shortfall` | 격리 `scope-shortfall` |
| `fix_exhausted` / `fix_unconverged` | 격리 `gate-exhausted` |
| `test_dispute` | 격리 `test-dispute` |
| `aborted` | 시스템 실패 판정 → 아니면 격리 `stage-failed` |

4. `ExitWorktree({ action: "keep" })`로 main에 돌아온다.

## Step 8: 사람 할 일 리포트

모든 패스가 같은 형식으로 끝낸다(EnterWorktree 상태면 먼저 복귀). 빈 칸은 생략한다.

```
─────────────────────────────────────────
🔁 Loop 완료 — <돈 패스>
─────────────────────────────────────────
1. 등급 확정 대기
   <KEY>  <요약> — /jira-task start <KEY> 또는 loop prep
2. plan 승인 대기
   <KEY>  <PR URL> — 승인자 @<login>: PR에 `APPROVE <plan|intent|spec> <SHA>`
3. draft 해제 대기 (리뷰 요청 준비됨)
   <KEY>  <PR URL> — AC <n>/<n> 충족. 확인 후 `gh pr ready <번호>`
   <KEY>  <PR URL> — stacked on <앞 KEY>
4. 격리
   <KEY>  [<kind>] <사유> — 권장: <아래 표>

sync 결과: 완료 <KEY...> / 검토 중 <KEY...> / 재정렬 <KEY...>
─────────────────────────────────────────
```

| kind | 권장 |
|---|---|
| scope-shortfall | 계획 수정 후 재승인, 직접 보완 후 `/jira-task verify`, 또는 미충족 범위를 새 이슈로 |
| gate-exhausted | `work/<KEY>/evidence/verification.md` 확인 → worktree에서 수정 → `/jira-task verify` |
| stage-failed | 실패 단계부터 직접: `/jira-task <단계> <KEY>` |
| test-dispute | 테스트를 고칠지 결정 → `/jira-task test-write <KEY>` 또는 `/jira-task impl <KEY>` |
| gate-error | `sdlc-gate.py check` 오류 확인(AGENTS.md 승인자 표, gh 로그인) |
| restack-conflict | worktree에서 rebase 충돌 해결(또는 미커밋 정리) 후 loop 재실행 |
| predecessor-deferred | 앞 태스크 격리 사유부터 해결 |
| pr-closed | PR이 머지 없이 닫힘 — 이슈를 정리하거나 새 PR |

### run-log 기록 (non-blocking)

REPO_ROOT에서 Bash 1회:
```bash
printf '%s' '{"status":"loop-run","passes":[<돈 패스>],"passed":[<completed KEY>],"awaiting":[<승인 대기 KEY>],"quarantined":[{"taskId":"<KEY>","deferredKind":"<kind>"}]}' \
  | python3 "<append-run-log.py>" - - - "docs/run-log" --kind=loop-run
```

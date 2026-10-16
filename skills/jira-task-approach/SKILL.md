---
name: jira-task-approach
description: "Write the standard L2/L3 artifacts (intent·spec·plan in work/<KEY>/), open a draft PR and stop for human approval. Triggers: jira-task approach, approach task; 명세, 계획, 승인 요청."
user-invocable: false
argument-hint: "<TASK-ID> [requirements 문서 경로]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# jira-task-approach: 산출물 작성과 승인 요청

**Language Rule**: 프로젝트 CLAUDE.md의 Conventions 섹션 참고 (한국어 출력, Jira 코멘트 제목은 영어).

## Overview

L2·L3 작업의 산출물을 `work/<TASK-ID>/`에 쓰고 커밋한 뒤 draft PR에서 승인을 요청하고 **멈춘다**. 승인 전에는 운영 코드를 고치지 않는다(SD-COM-GAT-004).

| 등급 | 이번 실행이 만드는 것 | 승인자 |
|---|---|---|
| L1 | 없음 — 계획은 PR 본문 "변경 내용"으로 대신한다. 안내만 하고 종료 | — |
| L2 | `spec.md` + `plan.md` 한 번에 | 작업 담당자(위험 신호가 있으면 기술 책임자) |
| L3 | 승인 상태에 따라 `intent.md` → `spec.md` → `plan.md` 중 다음 하나 | intent·spec: 제품 책임자 / plan: L2와 같음 |

**비목표**: 코드·테스트 작성(test-write·impl), 승인 판단(사람과 `sdlc-gate.py`), draft 해제.

## Workflow

### Step 0: 등급과 대상 산출물 결정

1. context `level`을 읽는다. 없으면 멈추고 `/jira-task start <TASK-ID>`(등급 확정)를 안내한다. issuetype으로 추정하지 않는다.
2. **Epic**이면 산출물을 만들지 않는다. `subtasks` + `issuelinks`(`is blocked by` 포함)로 자식 작업 목록과 순서·병렬 가능 여부를 응답에 표로 보여 주고 "자식 작업마다 start → approach"를 안내한 뒤 종료한다. 자식이 0건이면 `/jira-task create`로 먼저 분해하라고 안내한다.
3. **L1**이면 종료: `L1은 산출물이 없습니다. /jira-task test-write <TASK-ID> (동작 불변이면 impl)`.
4. **L3**이면 다음 대상을 고른다. 승인 확인은 스크립트 출력만 믿는다:
   ```bash
   python3 "<scripts>/sdlc-gate.py" check <TASK-ID> intent   # exit 0 승인 / 1 미승인 / 2 오류
   ```
   - `intent.md` 없음 → intent
   - intent 미승인 → 사용자가 수정을 요청했으면 intent를 고친다. 아니면 Step 7의 "승인 대기" 요약만 출력하고 종료
   - intent 승인, `spec.md` 없음 → spec (spec도 같은 방식으로 확인) → 그다음 plan
5. `docs/approach/<TASK-ID>.approach.md`(구버전 산출물)가 있으면 경고 1줄만 남긴다. 옮기거나 지우지 않는다.

사용자에게 1줄로 알린다 — 예: `📐 L3 — intent 승인 확인(@po-kim, 3f1b7d5) → spec 작성`.

### Step 1: Cache-First Fetch

context `cachedIssue.key === <TASK-ID>`이고 `fetchedAt`이 있으면 그대로 쓴다(CLAUDE.md "Cache-First Fetch"). 아니면:
```bash
python3 "<scripts>/jira-cli.py" get <TASK-ID> --fields subtasks,issuelinks > "<scratchpad>/<TASK-ID>.issue.json"
python3 "$JIRA_CTX_UPDATE_PY" <TASK-ID> - - "<worktree>/.jira-context.json" --cache-issue "<scratchpad>/<TASK-ID>.issue.json"
```

### Step 1.5: 첨부와 참조 읽기

화면 이미지·기획서·명세서 첨부는 description보다 구체적인 요구사항인 경우가 많다. **있으면 읽고 반영한다.**

1. `cachedIssue.attachments`에서 플러그인 산출물(`<TASK-ID>.`로 시작)을 뺀다. 이미지(≤5MB)·PDF(≤10MB)·텍스트류(md/txt/csv/json/yaml/xml/html/sql, ≤1MB)를 최대 10개, description에 `!파일명!`으로 삽입된 것부터 고른다. 그 밖의 형식은 파일명만 기록한다.
2. `python3 "<scripts>/jira-cli.py" download "${TMPDIR:-/tmp}/jira-attachments/<TASK-ID>" <id>...` — 실패해도 경고 1줄 후 진행.
3. Read로 열어 화면 구성·필드·흐름·수치·예외 조건처럼 구현에 영향을 주는 사실만 쓴다. description 속 외부 링크는 fetch하지 않고 URL만 기록한다.
4. 반영 위치: spec의 "외부 원본"(첨부·링크와 검토한 판), 요구사항·수용 조건. 첨부와 description이 충돌하면 spec "결정 사항"이 아니라 intent·spec의 미결 질문으로 남긴다.

### Step 2: 요구사항 문서와 공통 문서

1. 요구사항 문서를 `Read skills/_shared/requirements-link.md`의 순서(사용자 지정 → 출처 줄 → 키 역참조 → Glob, 모호하면 채택 안 함)로 확정한다. 노드를 알면 그 노드와 상위 Story 범위만 쓴다. 문서 내용은 복사하지 않고 링크한다(SD-COM-ART-004) — intent의 배경, spec의 참조 절.
2. 프로젝트 공통 문서가 있으면 읽는다: spec 전에는 `docs/policies/`·`docs/glossary.md`, plan 전에는 `docs/domain/`·`docs/architecture/`·`docs/decisions/`. 없는 폴더는 건너뛴다.
3. 남은 Open Questions(P1/P2/[CONFLICT])는 intent·spec의 미결 질문으로 옮긴다.

### Step 3: 산출물 쓰기

양식은 플러그인 `templates/sdlc/<intent|spec|plan>.md`를 Read해 쓴다. 맨 위 표준 사본 표시 주석과 안내 HTML 주석은 지우고, 절 제목과 순서는 유지한다. 산출물에 코드 스니펫을 넣지 않는다.

- **intent.md**: 문제·기대 결과·영향 범위·제약·미결 질문. 해결 방법은 쓰지 않는다.
- **spec.md**: 등급, 이슈 링크, 참조(정책·도메인·용어 링크), 요구사항(버그면 "버그" 절), 수용 조건 `AC-01`…(이슈의 AC를 검증 가능한 문장으로; 고객 요구사항 ID가 있으면 괄호로), 범위 밖. "결정 사항"에는 승인 기록이 있는 것만 적는다 — 대화에서 나온 합의는 미결 질문으로 둔다(SD-COM-ART-010).
- **plan.md**: 위험 신호(context `riskSignals`), 바뀌는 파일, 작업 순서(마지막은 지속 지식 옮기기 — 옮길 문서가 없으면 "없음"), 위험과 되돌리는 방법, 검증 방법(AC마다 테스트 이름이나 확인 방법 — test-write가 이 표로 테스트를 쓴다), 결정 기록(비워 둠).

산출물에 "승인됨" 같은 상태 문구를 쓰지 않는다. 승인은 PR 코멘트로만 기록된다.

### Step 4: 커밋

이번에 만든 파일만 명시적으로 add한다(`git add -A` 금지).

```bash
git add work/<TASK-ID>/spec.md work/<TASK-ID>/plan.md        # L3는 그 단계 파일 하나
git commit -m "docs(<TASK-ID>): spec·plan"                      # L3: "docs(<TASK-ID>): intent" 등
SHA=$(git rev-parse --short HEAD)
```

산출물을 고친 재실행이면 메시지 끝에 수정 사유를 붙인다(예: `docs(<TASK-ID>): spec AC-02 수정`). 승인 뒤 수정하면 앞선 승인은 무효가 된다는 것을 응답에 적는다(SD-COM-GAT-006).

### Step 5: draft PR과 승인 요청

1. `Read skills/_shared/pr-body.md` 후 push, draft PR 생성 또는 본문 갱신.
2. 승인자 계정: 프로젝트 `AGENTS.md` "## 승인자" 표의 `@계정`. intent·spec(L3)은 제품 책임자, plan은 작업 담당자(PR 작성자) — 위험 신호가 있으면 기술 책임자. 표가 없으면 PR 작성자·CODEOWNERS로 보고 경고를 코멘트에 넣는다. 승인자가 PR 작성자가 아니면 `gh pr edit feature/<TASK-ID> --add-reviewer <login>`.
3. PR 코멘트(`gh pr comment feature/<TASK-ID> --body-file <파일>`):
   ```markdown
   ## 승인 요청: <spec·plan | intent | spec | plan>

   - 대상 커밋: <SHA>
   - 파일: work/<TASK-ID>/spec.md, work/<TASK-ID>/plan.md
   - 승인자: @<login> (<역할>)

   검토 후 승인하시면 아래 형식의 한 줄을 코멘트로 남겨 주세요. `<SHA>` 자리에 위 대상 커밋을 넣습니다.

       APPROVE <plan|intent|spec> <SHA>

   수정이 필요하면 코멘트로 알려 주세요. 파일을 고치면 새 커밋으로 다시 승인을 요청합니다.
   ```
   L2는 `APPROVE plan`이 spec·plan을 함께 승인한다. **코멘트에 실제 SHA를 형식 줄과 붙여 쓰지 않는다** — 그 줄은 승인 기록으로 읽히고, hook과 jira-cli가 막는다.

### Step 6: Jira 반영

```bash
python3 "<scripts>/jira-cli.py" attach <TASK-ID> work/<TASK-ID>/spec.md work/<TASK-ID>/plan.md --artifact
python3 "<scripts>/jira-cli.py" comment <TASK-ID> @<scratchpad md>
```

코멘트:
```markdown
## Approval Requested
- 산출물: <spec·plan | intent | spec | plan> (커밋 <SHA>)
- PR: <PR URL> (draft)
- 승인자: <역할> @<login>
- 원본은 저장소 `work/<TASK-ID>/`, 첨부는 사본입니다.
```
첨부 실패는 경고 1줄 후 계속한다.

### Step 7: context와 완료 요약

plan까지 커밋했을 때만(L2, L3 plan) `approach`를 기록한다. L3 intent·spec 단계에서는 기록하지 않는다.

```bash
SCRIPT_NAME="jira-context-update.py" OUT_VAR="JIRA_CTX_UPDATE_PY"
# Read skills/_shared/script-lookup.md and execute its lookup block here
python3 "$JIRA_CTX_UPDATE_PY" <TASK-ID> approach "-" \
    "<worktree>/.jira-context.json" \
    "<repoRoot>/.jira-context.json"
```

```
---
⏸ **승인 대기** — <TASK-ID> (<L2|L3>)

- 산출물: work/<TASK-ID>/<파일> (커밋 <SHA>)
- PR: <URL> (draft)
- 승인자: @<login> — PR에 `APPROVE <artifact> <SHA>` 한 줄

**Progress**: init → start → **approach ⏸** → test-write → impl → verify → pr → done

**Next**: 승인 뒤 `/jira-task test-write <TASK-ID>` (L3 intent·spec 단계면 `/jira-task approach <TASK-ID>`로 다음 산출물)
---
```

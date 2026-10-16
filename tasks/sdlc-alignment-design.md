# AI-native SDLC 표준 정합 (P0) — 설계

> 기준: `mzd-software-development-standard/00-ai-native-sdlc-process/STANDARD.md` v0.9.0b (이하 `S`), 03 테스트 자동화 10장(`TA`), 04 코드 품질(`CQ`).
> 브랜치: `feature/sdlc-standard-alignment`. 선행: 0단계 버그 수정(v0.64.2, `2109c08`).
> 비범위: 멀티 harness 어댑터(3단계, 별도 설계), 표준 레포 수정(§11 피드백 목록만).
> 상태: P0 구현 완료(v0.70.0, 2026-10-16). 3단계(멀티 harness)는 별도 설계.

---

## 1. 문제

플러그인의 단계 이름은 표준과 비슷하지만 다섯 군데가 표준 MUST와 반대 방향이다.

| # | 현재 | 표준 | 근거 |
|---|---|---|---|
| 1 | 산출물은 `docs/approach·test·review/<KEY>.*.md`, 기본 gitignore, Jira 첨부 | `work/<KEY>/`에 spec·plan·evidence/verification(L3는 intent)만, 저장소가 원본 | ART-001/002 |
| 2 | 등급을 issuetype으로 추정하고 저장하지 않음 | 판정 질문 + 위험 신호로 에이전트가 제안, 작업 담당자가 확정, 이슈에 기록 | GAT-001/002 |
| 3 | auto가 approach→impl을 사람 확인 없이 연속 실행 | L2·L3는 plan 승인 전 운영 코드 수정 금지, 승인은 승인자 계정 + SHA | GAT-004/005 |
| 4 | 로컬 base에 먼저 병합, 그다음 PR. loop가 미리뷰 코드를 다음 태스크 base로 | 에이전트 코드는 PR로만 기본 브랜치에, 머지는 코드 오너 | AUT-005, ROL-003 |
| 5 | impl(테스트 금지) 뒤에 test가 테스트 작성 | 테스트 작성 세션이 실패 테스트를 먼저 별도 커밋, 구현 세션은 테스트 수정 불가(도구로 강제) | TA-AGT-001/002/005/008 |

## 2. 결정 사항 (사용자 확정, 2026-10-16)

- 산출물은 `work/<KEY>/`에 커밋하고 Jira에도 첨부한다(둘 다).
- Jira 등급 기록은 라벨 `sdlc-L1` / `sdlc-L2` / `sdlc-L3`.
- `jira-local-merge`는 폐지한다.
- loop는 유지하고 사람 게이트 기준 3패스(plan / build / sync)로 재설계한다.
- 팀 GitHub 머지 방식은 rebase merge.
- L2 plan 승인은 PR 코멘트로 받는다.
- 헤드리스 runner는 P0에서 빼고 3단계로 미룬다. P0의 세션 분리는 auto의 sub-agent + `activeRole` 표시로 한다.
- §12의 네 가지는 제안대로 확정.

## 3. 원칙

1. **게이트는 스크립트가 확인한다.** "승인됐는지"를 LLM이 판단하지 않는다. `sdlc-gate.py`가 GitHub·git에서 사실을 읽어 판정한다(AUT-004).
2. **에이전트는 승인하지 않고, 승인처럼 보이는 글도 쓰지 않는다.** 리뷰 결과 어휘는 "검증 통과/미통과". 승인 토큰을 담은 코멘트는 도구 계층에서 막는다(ROL-002).
3. **draft 해제는 사람이 한다.** 에이전트는 "리뷰 요청 준비됨"까지만 만든다(ROL-005, `S:220`).
4. **레포가 원본, Jira는 사본과 링크.** Jira 첨부는 편의용 사본이고, 코멘트에는 PR·커밋 링크를 함께 남긴다(ART-006).
5. **세션 분리는 역할 단위로.** 테스트 작성 / 구현 / 검증은 서로 다른 sub-agent(새 컨텍스트)에서 돌고, 현재 역할을 파일로 표시해 hook이 읽는다.

## 4. 새 흐름

```
L1: start(등급 확정) → test-write* → impl → verify → [사람] draft 해제 → [코드 오너] 머지 → done(sync)
L2: start → approach(spec+plan) → [사람] plan 승인 → test-write → impl → verify → [사람] draft 해제 → [코드 오너] 머지 → done
L3: start → approach(intent) → [제품 책임자] → approach(spec) → [제품 책임자] → approach(plan) → [작업 담당자] → (L2와 같음)
* L1 test-write는 동작이 바뀌는 경우에만. 오타·로그 한 줄 등 동작 불변이면 사유를 PR 본문에 남기고 생략.
```

### 4.1 단계별 변경

| 단계 | 변경 |
|---|---|
| discover | 유지. 산출물 `docs/requirements/`도 유지(티켓 생성 전 단계라 작업 ID가 없음). L3 작업의 intent.md는 이 문서를 링크하고 복사하지 않는다(ART-004) |
| create | 분해 레벨 이름 L1/L2/L3를 **분해 형태 `single` / `story` / `tree`**로 바꾼다(등급과 충돌 방지). 등급은 정하지 않는다 |
| epic, init, report, clean | 변경 없음. init은 base를 `origin/<base>` 최신으로 fetch 후 분기 |
| start | **등급 판정 추가.** 판정 질문 3개 + 위험 신호 5개로 제안 → 사용자 확정 → Jira 라벨 `sdlc-Lx` + 코멘트(등급, 확정자, 근거, 해당 위험 신호) + context `level`. 이후 모든 단계는 context `level`만 읽는다(issuetype 추정 제거) |
| approach | 표준 산출물을 쓴다. L2: spec.md + plan.md 한 번에. L3: intent → spec → plan을 게이트마다 끊어서(재실행 시 다음 산출물로 진행). 커밋 → push → draft PR → 승인 요청 코멘트 → **정지**. L1은 파일을 만들지 않고 PR 본문의 "변경 내용"에 3~5줄로 쓴다 |
| **test-write** (신규) | 역할 `test-writer`. spec의 AC마다 테스트 작성 → 실행해 **올바른 이유로 실패**하는지 확인 → `test(<KEY>): ...` 커밋. 기대값을 바꾼 경우 값마다 근거를 PR 본문 "테스트 기대값 변경"에 기록(TA-AGT-003) |
| impl | 역할 `implementer`. 테스트 파일 쓰기 차단(hook). 억제 주석·분석 제외 설정 추가 금지(CQ-AGT-001) — 필요하면 멈추고 보고. 계획과 달라지면 plan.md 결정 기록 수정(ART-007). 마지막 작업은 지속 지식 옮기기(ART-008). 커밋은 `feat|fix(<KEY>): ...`, 지식 옮기기는 `docs(<KEY>): ...` |
| test (기존) | **폐지**, test-write와 verify로 나뉜다. 환경 감지·Playwright 로직은 verify의 "실행한 검사"로 이동 |
| review → **verify** | 역할 `verifier`, 새 컨텍스트, 입력은 spec + diff만, 코드 수정 금지(VER-003). 산출물 `evidence/verification.md`: AC별 충족/미충족/미확인 + 근거, 실행한 검사(명령과 결과), 독립 검증(품질 findings 요약). jira-reviewer 에이전트를 이 역할로 재사용. review-log JSON은 유지 |
| pr | 별도 단계가 아니라 흐름에 녹는다. draft PR은 approach(L2·L3) 또는 impl 끝(L1)에서 생성. 본문은 표준 PR 양식이고 단계마다 `gh pr edit`로 갱신. `/jira-task pr`은 "PR 본문 재생성" 명령으로 남긴다 |
| merge | **폐지** (`skills/jira-local-merge/` 삭제, phase-gate·README·loop에서 참조 제거) |
| done | 사람이 부르지 않아도 sync가 처리. PR이 MERGED면 Jira 완료 전이 + 머지 커밋 SHA 코멘트. 수동 호출도 같은 확인을 거친다(머지 안 됐으면 거부) |

### 4.2 verify 판정과 fix 루프

- 미충족 0건이면 "리뷰 요청 준비됨": PR 본문 갱신, Jira 코멘트, 사람에게 `gh pr ready <번호>` 안내. Jira 상태는 draft 해제 시점에 "검토 중"으로(sync가 감지).
- 미충족이 있으면 draft 유지(VER-002), auto에서는 기존 fix 루프로 impl에 되돌린다. fix 루프의 구현 sub-agent도 역할은 `implementer`라 테스트를 못 고친다. 테스트 자체가 틀렸다는 판단이 나오면 test-write로 되돌리고 사유를 기록한다.
- 기존 matchRate(계획 항목 매칭률)와 README의 90% 임계값은 폐지한다. 판정 단위는 AC.

## 5. 산출물·커밋·Jira

### 5.1 산출물

| 기존 | 신규 | Jira 첨부 |
|---|---|---|
| `docs/approach/<KEY>.approach.md` (L1/L2) | L1: PR 본문 / L2: `work/<KEY>/spec.md` + `plan.md` | spec, plan |
| (없음) | L3: `work/<KEY>/intent.md` | intent |
| `docs/test/<KEY>.test-report.md` | `work/<KEY>/evidence/verification.md` "실행한 검사" + 스크린샷은 `evidence/` | verification |
| `docs/review/<KEY>.review.md` | 같은 파일 "독립 검증" 절 | (위와 같음) |
| `templates/pr-description.template.md` | 표준 `T/.github/pull_request_template.md` 기반. 프로젝트에 `.github/pull_request_template.md`가 있으면 그것을 따른다 | — |

- `templates/`에는 표준 템플릿 사본을 두고 머리에 출처(표준 버전·파일)를 적는다. 표준이 바뀌면 사본을 통째로 교체한다.
- 템플릿 사본은 플러그인 내부 자료라 CTX-005(AGENTS.md·skill에 표준 본문 복사 금지)와 충돌하지 않는다. 스킬 본문에는 섹션 목록을 다시 적지 않고 템플릿을 Read한다.

### 5.2 커밋 단위 (작업 ID는 모든 커밋에, ART-011)

| 순서 | 메시지 | 내용 |
|---|---|---|
| 1 | `docs(<KEY>): spec·plan` (L3는 intent/spec/plan 각각) | 산출물 |
| 2 | `test(<KEY>): AC-01…AC-0n 실패 테스트` | 테스트만 (TA-AGT-002) |
| 3 | `feat\|fix(<KEY>): <요약>` (여러 개 가능) | 운영 코드 |
| 4 | `docs(<KEY>): 지속 지식 옮기기` | `docs/policies·glossary·domain·architecture·decisions` |
| 5 | `docs(<KEY>): verification` | evidence |

`git add -A` 일괄 커밋은 없앤다. 각 단계는 자기가 만든 파일만 명시적으로 add한다.

### 5.3 Jira 반영

| 시점 | 라벨 | 상태 | 코멘트 |
|---|---|---|---|
| start | `sdlc-Lx` | 진행 중 | 등급·확정자·근거 |
| approach 정지 | — | — | 산출물 링크(PR·파일) + 첨부, 승인 대기 |
| 승인 확인(build 진입) | — | — | 승인자·SHA (스크립트가 읽은 사실 그대로) |
| verify 통과 | — | — | AC 판정 요약 + verification 첨부 |
| draft 해제 감지 | — | 검토 중 | PR 링크 |
| PR 머지 감지 | — | 완료 | 머지 커밋 SHA |

## 6. 승인 확인: `scripts/sdlc-gate.py` (신규)

- 서브커맨드: `check <KEY> <artifact>` (artifact = intent | spec | plan), `pr-state <KEY>`(draft/ready/merged).
- **승인 코멘트 형식**: PR 코멘트 한 줄 `APPROVE <artifact> <sha7 이상>`. 예: `APPROVE plan 3f1b7d5`.
- **판정** (모두 만족해야 통과):
  1. 코멘트 작성자가 해당 산출물의 승인자 목록에 있다.
  2. SHA 커밋이 저장소에 있다.
  3. 그 SHA 시점과 HEAD의 `work/<KEY>/<artifact>.md`가 같다(`git diff <sha> HEAD -- <file>` 비어 있음). 바뀌었으면 재승인 필요(GAT-006 확장: AC뿐 아니라 파일 전체 기준). 이력 포함 여부는 보지 않는다 — stacked 재정렬·base 충돌 rebase로 SHA가 바뀌어도 내용이 같으면 승인 유효(드라이런 DEMO-5).
  4. 위험 신호가 있는 L2·L3 plan은 승인자가 기술 책임자 목록에 있다(GAT-003).
- **승인자 목록 출처**: 프로젝트 `AGENTS.md`의 "## 승인자" 표(`| 역할 | 담당 |`)에서 "담당" 칸의 `@계정`을 GitHub 계정으로 읽는다. 표가 없거나 비었으면 §12-3대로 처리한다.
- **L2 작업 담당자 = PR 작성자**인 경우 GitHub Approve는 쓸 수 없으므로 코멘트 형식이 유일한 경로다.

### 6.1 승인 토큰 위조 차단

- 차단 대상은 SHA까지 붙은 유효한 토큰이다. 승인 요청 코멘트는 `APPROVE plan <SHA>`처럼 SHA 자리를 비운 안내와 SHA를 따로 적는다.
- `jira-cli.py comment`는 본문에 토큰 줄이 있으면 거부한다.
- PreToolUse hook `guard-approval.js`: `gh pr review --approve`를 거부하고, gh·curl·jira-cli 호출의 명령 텍스트나 body 파일에 토큰이 있으면 거부한다.
- L2는 spec·plan을 함께 승인하므로 `APPROVE plan <sha>`가 spec.md·plan.md 둘 다를 덮는다(둘 다 SHA 이후 불변이어야 통과).
- **남는 위험**: 에이전트가 curl로 GitHub API를 직접 부르면 막을 수 없다. 같은 계정을 쓰는 한 구조적 한계이고, 표준 쪽 규칙 보강이 필요하다(§11-2).

## 7. 역할 표시와 테스트 보호

- 각 단계는 시작할 때 worktree-local `.jira-context.json`에 `activeRole`(`test-writer` / `implementer` / `verifier` / 없음)을 쓰고, 끝날 때 지운다(`jira-context-update.py --patch`).
- PreToolUse hook `guard-test-files.js` (Edit|Write, Bash 리다이렉트):
  - `implementer`: 테스트 파일 쓰기 거부.
  - `verifier`: 모든 쓰기 거부, 단 `work/<KEY>/evidence/` 예외.
- 테스트 파일 판정 패턴은 고정값(`*.test.*`, `*.spec.*`, `test/`, `tests/`, `__tests__/`, `src/test/`, `test_*.py`, `*_test.py|go`). 프로젝트별 지정은 필요해지면 추가한다. `work/` 아래는 테스트 파일로 보지 않는다.
- Bash는 명시적인 쓰기 대상(`>`, `>>`, `tee`, `sed -i`, `Set-Content`/`Add-Content`/`Out-File`)만 판정하고, 저장소 밖 경로는 판정하지 않는다.
- 03 표준 참조 구현(`03-test-automation/configs/claude-code/`, 환경변수 `AGENT_ROLE`)과의 관계: 환경변수는 sub-agent별로 줄 수 없어서 파일 표시를 쓴다. `AGENT_ROLE`이 있으면 그것을 우선한다(표준 hook과 같이 깔려도 충돌하지 않게).
- 남는 위험: 역할 파일은 에이전트가 고칠 수 있다. 최종 강제는 CI(VER-004)와 리뷰 점검표다.

## 8. auto

`auto`는 "다음 사람 게이트까지 진행"으로 바뀐다.

| 시작 상태 | auto가 하는 일 | 멈추는 곳 |
|---|---|---|
| L1, 시작 전 | start → test-write → impl → verify → PR 본문 | 리뷰 요청 준비됨 |
| L2·L3, plan 승인 전 | start → approach | 승인 대기 (draft PR) |
| plan 승인됨 (`sdlc-gate check` 통과) | test-write → impl → verify(+fix 루프) | 리뷰 요청 준비됨 |

- `auto.workflow.js`의 단계 목록·게이트·triage는 위 표대로 재배치한다. 승인 확인은 첫 단계에서 `sdlc-gate.py`를 부르는 코드 판정이다.
- start의 등급 확정은 대화형이다. auto가 등급 미확정 태스크를 만나면 질문하고, 응답이 없으면 그 태스크를 멈춘다(추정으로 진행하지 않음).
- 모델 배정(haiku/sonnet/opus)은 단계 이름만 바꿔 유지한다: test-write = sonnet, verify = opus(L1은 sonnet).

## 9. loop: 3패스

### 9.1 패스

| 패스 | 대상 | 하는 일 | 끝 리포트 |
|---|---|---|---|
| 준비 | 큐 전체 | 등급 미확정 태스크의 등급을 표로 제안 → 한 번에 확정 | — |
| `loop plan` | L2·L3 중 승인 전 | 태스크마다 auto(→ 승인 대기). L1은 건너뜀 | 승인 대기 PR 목록 |
| `loop build` | L1 + 승인 확인된 L2·L3 | 태스크마다 auto(→ 리뷰 요청 준비됨) | draft 해제 대기 PR 목록 |
| `loop sync` | PR이 있는 전체 | PR 상태 읽기 → Jira 반영(검토 중/완료), stacked 브랜치 재정렬 | 머지됨·재정렬됨·충돌 목록 |

- 격리(quarantine)와 시스템 실패 중단 규칙은 세 패스 모두 기존 그대로.
- EnterWorktree 의존은 유지한다(3단계에서 runner로 대체).

### 9.2 base와 stacked PR

- **독립 태스크**: `origin/<base>`에서 분기, PR base = `<base>`.
- **의존 태스크**(Jira `is blocked by`로 큐 안의 태스크를 가리킴): 앞 태스크 브랜치에서 분기, PR base = `feature/<앞 KEY>`, draft 유지. 분기 시점의 앞 브랜치 head SHA를 context `stackedOn: {key, branch, sha}`에 기록한다.
- PR 본문 "작업" 절에 "이 PR은 #<번호>(<앞 KEY>) 위에 쌓여 있음. 그 PR이 머지되면 자동으로 재정렬됨" 문구.
- **sync의 재정렬** (rebase merge 기준): 앞 PR이 MERGED면 `git rebase --onto origin/<base> <stackedOn.sha> feature/<KEY>` → `push --force-with-lease` → `gh pr edit --base <base>` → `stackedOn` 삭제. rebase merge는 앞 태스크 커밋의 SHA를 바꾸므로, 기록해 둔 SHA가 없으면 재정렬할 수 없다(그래서 분기 시점에 기록).
- 충돌하면 그 태스크만 격리하고 리포트에 남긴다.

### 9.3 사람 할 일 리포트 (모든 패스 공통 형식)

1. 등급 확정 대기
2. plan 승인 대기 (PR 링크, 승인 코멘트 형식 안내)
3. draft 해제 대기 (리뷰 요청 준비된 PR)
4. 격리된 태스크 (사유)

## 10. 기타 변경

- **phase-gate config**: 의존 그래프를 새 단계로 교체(`test-write requires approach(L2·L3)`, `impl requires test-write`, `verify requires impl`, `merge` 제거). 여전히 기본 비활성.
- **session-start.js**: 단계 목록을 새 흐름으로.
- **README**: "사람의 자리"를 §9.3 네 칸 + 코드 오너 머지로 다시 쓴다. 리뷰 90% 임계값 서술 삭제.
- **CLAUDE.md**(플러그인 개발 문서): Progress 추적 유효 단계 목록 갱신, local merge 서술 삭제.
- **기존 진행 중 태스크**: 마이그레이션하지 않는다. `docs/approach/`가 있는 태스크는 구버전 흐름으로 끝내거나 start부터 다시 한다. approach는 구 경로 파일이 있으면 경고만 한다.
- **버전**: 흐름이 바뀌는 변경이라 0.70.0.

## 11. 표준 쪽 피드백 (표준 레포 반영은 별도 확인 후)

1. `T/CLAUDE.md:10`, GAT-004 🔧: plan mode는 쓰기·커밋을 막아 산출물 커밋 절차와 충돌. 문구 삭제 또는 "탐색 단계 한정"으로.
2. GAT-005: 같은 계정을 쓰는 로컬 에이전트가 승인 코멘트를 쓸 수 있다. "에이전트는 승인 형식의 글을 쓰지 않는다"와 승인 형식 고정(예: `APPROVE <artifact> <sha>`)을 규칙으로.
3. L1 절차 vs TA-AGT-002: "동작이 바뀌는 L1은 재현 테스트 선행" 또는 명시적 예외.
4. `T/AGENTS.md:29` "기존 테스트 수정 금지"를 역할 조건부로(테스트 작성 세션 제외).
5. 판정 질문 1번이 L2 예시(버그 수정, 기존 요구사항 안 변경)를 L3로 흡수. "새로운 제품 동작·요구사항 변경"으로 좁히기.
6. VER-002 "리뷰 요청 금지"와 산출물 승인용 리뷰 요청(`S:223`)의 용어 분리.
7. 코드 오너 1인 경로의 자기 승인 교착(ROL-006 예시).
8. `T/AGENTS.md` 승인자 표의 "담당" 칸 `@`가 GitHub 계정이라는 것을 명시(§6 자동 확인이 이 칸을 읽음).

## 12. 추가 결정 (2026-10-16 확정)

| # | 질문 | 결정 |
|---|---|---|
| 1 | approach 단계 이름을 유지할지, 표준 용어(`spec` / `plan`)로 바꿀지 | 유지. 개발자가 쓰는 명령은 그대로, 산출물 이름만 표준 |
| 2 | L3와 Epic의 관계. 지금 플러그인 L3 = Epic(자식 Story 순서만 씀) | 분리. 등급은 PR이 나오는 작업 단위(Story/Task/Subtask)에만 붙이고, Epic은 등급 없음. 기존 "L3 = Epic 조기 종료" 로직은 분해 형태 `tree`의 처리로 옮김 |
| 3 | 승인자 표를 못 읽는 프로젝트(표준 미도입) | PR 작성자 또는 CODEOWNERS에 있는 계정의 승인 코멘트를 인정하고, 승인자 표가 없다는 경고를 판정 결과와 Jira 코멘트에 남긴다 |
| 4 | Jira 첨부를 매 단계 새로 올릴지(버전 누적) | 같은 파일명은 기존 첨부 삭제 후 재업로드 |

## 13. 구현 순서 (커밋 단위)

1. `sdlc-gate.py` + 테스트 (승인 판정, PR 상태, 토큰 차단 함수)
2. `jira-cli.py comment` 토큰 거부 + `guard-approval.js`, `guard-test-files.js` + hooks.json 등록 + 테스트
3. 템플릿 교체(표준 사본) + `jira-context-update.py`에 `level`·`activeRole`·`stackedOn` 필드
4. start 등급 판정 + create 분해 형태 이름 변경
5. approach → 표준 산출물·draft PR·정지
6. test-write 신설, impl 역할·커밋·지식 옮기기, test 폐지
7. review → verify (jira-reviewer 재사용, verification.md)
8. pr 재정의, done을 머지 확인 기반으로, local merge 삭제
9. auto 재배치
10. loop 3패스 + stacked PR + sync
11. phase-gate config, session-start, README, CLAUDE.md, 버전 0.70.0

## 14. 드라이런 반영 (2026-10-16)

mock Jira·가짜 gh 샌드박스에서 DEMO-1(L1)을 끝까지, DEMO-2(L2, 위험 신호 ④)를 리뷰 요청 준비까지 돌렸다. 단계마다 새 sub-agent가 SKILL.md를 그대로 따랐다. 고친 것:

| 발견 | 조치 |
|---|---|
| 먼저 머지된 PR 때문에 열린 PR이 충돌(테스트 파일) — 경로 없음 | `pr-state`에 `mergeable`, sync가 `base-conflict`로 격리, `skills/_shared/base-conflict.md`(rebase → 테스트 충돌은 test-writer·코드는 implementer → 재검증) |
| start가 등급 확정 전에 Jira 전이·담당자 지정 | 등급 확정을 Step 1.2로 앞당김 |
| 승인 코멘트로 받은 미결 질문 답이 spec에 반영되지 않음, 표준 spec 양식에 미결 질문 절 없음 | 미결 질문이 있으면 승인 요청 대신 질문(5-a, `openQuestions`), 답은 spec "결정 사항"에 기록 후 승인 요청. auto `awaitingKind` |
| `jira-context-update.py`가 없는 ctx 파일을 rc=0으로 넘김 → aggregate 갱신 누락(3회) | exit 1, repoRoot는 Read한 값을 리터럴로 |
| review-log가 worktree에 미커밋 파일로 남음 | review-log·run-log를 메인 레포 로컬로, init이 gitignore 등록 |
| cachedIssue 기록 방법 부재, start·approach hit 기준 차이로 매번 miss, record-only 단계가 fetchedAt 덮음 | `--cache-issue`, hit = key + fetchedAt, fetchedAt은 status 갱신 때만 |
| 그 밖의 문서 정합 | test 커밋 메시지(실패·회귀 방지 수), L1 push 조건, Progress 줄 `approach(L2·L3)`, Jira 링크 출처, Mode B 서명, 템플릿 머리 문구, init 안내 문구 |

샌드박스에서 확인한 것: 승인 게이트(PR 작성자 거부·기술 책임자 통과), 미승인 test-write 정지, 역할 hook·토큰 차단, done 머지 확인, aggregate prune, `--artifact` 첨부. 확인하지 못한 것: Workflow 실행(auto·loop), L3, fix 루프, stacked 재정렬, Mode A verify.

충돌 경로 재확인: DEMO-2를 `base-conflict.md`대로 해결(테스트 충돌을 test-writer로, 코드는 자동 병합) → 재검증 통과 → 머지까지 갔다. 이 과정에서 `--remove-step`(aggregate의 verify 제거)과 rebase 뒤 test 커밋 SHA 재탐색을 추가했다.

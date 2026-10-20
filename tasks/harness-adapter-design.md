# harness 어댑터 설계 — 1부 Codex

> 상태: Codex 구현·실측 완료 (2026-10-17, v0.71.0). 지원 harness는 Claude Code·Codex 둘로 한다. Copilot은 계획으로만 둔다(사용자 결정 2026-10-17). 범위 결정은 `tasks/sdlc-alignment-design.md` §2: 3단계는 어댑터만, Codex → Copilot 순서. 다른 harness에서는 단계 명령을 사람이 단계마다 새 세션으로 실행하고, auto·loop는 Claude Code 전용으로 둔다.

## 1. 원칙: 원본 하나

2026-09에 v0.62를 손으로 옮긴 Codex 이식본(`~/plugins/jira-claude-code-integration`, `0.62.1+codex`)이 있었다. 변환 스크립트 없이 복사했기 때문에 원본이 바뀌자 바로 낡았다(test/review/merge 단계, MCP 시대 문구). 같은 일을 반복하지 않는다.

- 이 레포를 Codex에도 **그대로 설치**한다. Codex는 `.claude-plugin/marketplace.json`을 호환 형식으로 읽는다.
- 스킬 본문은 harness 중립 문구로 고친다. harness마다 다른 부분은 "Claude Code에서는 A, 도구가 없으면 B" 한 줄로 쓴다. 파일을 harness별로 나누지 않는다.
- 생성·변환 스크립트를 두지 않는다. 필요해지면(Copilot에서 형식이 갈리면) 그때 추가한다.
- (사용자 확정 2026-10-17) 원본 하나로 간다. 레포·플러그인 이름(`jira-claude-code-integration`)도 harness 중립으로 바꾼다 — 어댑터가 끝난 뒤 별도 작업. 실측은 사용자 Codex(Plus)로 한다. 기존 이식본은 새 방식 동작 확인 후 제거한다.

실측(codex-cli 0.162.1, 격리 `CODEX_HOME`): `codex plugin marketplace add <레포>` → `codex plugin add jira-integration@jira-claude-code-integration`로 설치된다. `codex debug prompt-input`에 단계 스킬 17개가 `jira-integration:<skill>`로 노출된다(`user-invocable: false`는 무시됨). `commands/`는 `dashboard`만 스킬로 변환되고 `jira-task`·`jira`는 변환되지 않았다. 로컬 경로 설치는 작업 트리를 통째로 복사하므로 gitignore된 `.jira-context.json`(토큰)까지 캐시에 들어간다 — 사용자 설치는 git 소스로 안내한다.

## 2. 대응표

| Claude Code 의존 | Codex | 처리 |
|---|---|---|
| `/jira-task <action>` 라우터(Skill 도구로 단계 스킬 호출, TASK-ID 자동 감지) | 커맨드 변환 안 됨. 스킬은 `$jira-task-start` 등으로 직접 호출 | §3.1 |
| PreToolUse hook(guard-approval, guard-test-files, guard-worktree-remove) | 같은 `hooks/hooks.json` 스키마, `CLAUDE_PLUGIN_ROOT`도 전달. 셸은 `Bash`, 파일 편집은 `apply_patch`(경로가 패치 본문에만 있음). 플러그인 hook은 `/hooks`에서 trust해야 실행 | §3.2 |
| verify Mode A(Agent 도구 → jira-reviewer, opus) | 커스텀 에이전트를 플러그인으로 배포할 수 없음 | §3.3 |
| AskUserQuestion | Default 모드에는 없음 | 텍스트 질문으로 폴백(§3.4) |
| SKILL.md 본문 `${CLAUDE_PLUGIN_ROOT}` 로드 시 치환 | 치환 없음. 스킬 파일 절대 경로는 모델에 주어짐 | lookup의 `PLUGIN_ROOT`(Read한 경로 기준)로 통일(§3.5) |
| `<scratchpad>` 경로 | 없음 | §3.5 |
| 기본 권한 | CLI 기본 샌드박스가 네트워크 차단, `.git`(worktree가 가리키는 gitdir 포함) 읽기 전용, 레포 밖 형제 worktree 쓰기 불가 | §3.6 |
| PR 본문 "작성 `Claude Code`", verify 서명 | — | 실행 중인 harness·모델 이름을 넣는다 |
| 스킬의 "프로젝트 CLAUDE.md의 Conventions 참고" | 사용자 프로젝트에 없는 파일을 가리킴(기존 결함) | `skills/_shared/` 공용 문서 참조로 |
| SessionStart·Stop·대시보드 ingest hook | 이벤트 이름은 같으나 transcript 형식이 다름 | 실패해도 exit 0인지 확인만, 대시보드는 Codex 미지원으로 둔다 |
| auto(Workflow, sub-agent) | 없음 | runner `scripts/auto-codex.js`(§6, v0.72.0) |
| loop(Workflow, EnterWorktree) | 없음 | 범위 밖. Codex에서 호출하면 "Claude Code 전용" 안내 후 멈춤 |

## 3. 항목별 설계

### 3.1 진입점

Codex에서는 사용자가 단계 스킬을 직접 부른다(`$jira-task-start DEMO-1`). 라우터에만 있던 TASK-ID 자동 감지(브랜치 → 디렉터리 이름 → `.jira-context.json`)를 `skills/_shared/task-id.md`로 옮기고 각 단계 스킬이 인자가 없을 때 그 문서를 따른다. 라우터는 이 문서를 참조하도록 줄인다. alias(`plan`→`approach`, `review`→`verify`)는 라우터에만 남긴다.

### 3.2 guard hook

- matcher에 Codex 이름을 더한다: 셸 `Bash`(이미 있음), 편집 `apply_patch`.
- `guard-test-files.js`: `tool_name === "apply_patch"`이면 `tool_input.command`의 `*** Add File:` / `*** Update File:` / `*** Delete File:` / `*** Move to:` 줄에서 경로를 뽑아 기존 판정에 넣는다.
- `guard-approval.js`, `guard-worktree-remove.js`: Codex도 셸을 `Bash` + `tool_input.command`로 준다. 실측: `gh pr comment 1 --body "APPROVE plan abc1234"`가 플러그인 hook으로 차단됐다(설치한 레포 그대로, `--dangerously-bypass-hook-trust`). Windows에서 Codex의 `Bash`는 PowerShell 명령을 담는다(`Set-Content` 등 기존 PowerShell 판정이 그대로 쓰인다).
- 실측한 hook 입력 키: `cwd, hook_event_name, model, permission_mode, session_id, tool_input, tool_name, tool_use_id, transcript_path, turn_id`. 편집은 `tool_name: "apply_patch"`, `tool_input.command`가 `*** Begin Patch … *** Update File: <경로> …` 본문(경로는 상대 또는 절대).
- 차단 출력은 지금 쓰는 `hookSpecificOutput.permissionDecision: "deny"`가 Codex에서도 지원된다.
- trust: README Codex 절에 "설치 후 `/hooks`에서 jira-integration hook을 trust" 단계를 넣는다. trust 전에는 표준 통제(승인 토큰 차단, 테스트 보호)가 꺼진 상태이므로, 단계 스킬이 시작할 때 hook 동작 여부를 알 수 없다는 점을 문서에 분명히 한다.

### 3.3 verify 세션 분리

Codex에서는 사용자가 **새 Codex 세션**을 열어 verify를 실행하고, 그 세션이 Mode B(self-mode)로 `agents/jira-reviewer.md` 절차를 직접 수행한다. Mode A의 "Agent 도구가 없으면 멈춘다"를 "Agent 도구가 없는 harness에서는 이 세션에서 test-write·impl을 하지 않았을 때만 self-mode로 진행한다. 했으면 새 세션에서 다시 실행하라고 안내하고 멈춘다"로 바꾼다. 판단 근거는 context `activeRole`(이 세션이 implementer로 표시했다가 지웠는지는 알 수 없으므로 모델의 자기 확인 + 안내 문구에 의존한다 — 한계로 기록).

### 3.4 사람에게 묻기

`skills/_shared/ask-user.md`(신규, 짧게): "선택지를 묻는 도구가 있으면 쓰고, 없으면 번호 목록으로 묻고 턴을 끝낸다. 답을 받기 전에 다음 단계로 가지 않는다." create·discover·epic·setup의 AskUserQuestion 지시를 이 문서 참조로 바꾼다. discover 인터뷰는 라운드마다 한 턴이 된다.

### 3.5 경로

- 스크립트: 모든 스킬이 `script-lookup.md`의 `PLUGIN_ROOT`(그 파일을 Read한 경로의 루트)를 쓴다. clean·init·dashboard의 `${CLAUDE_PLUGIN_ROOT}` 직접 사용은 lookup으로 바꾼다(Codex에서는 치환되지 않는다). 캐시 폴백 후보에 `$CODEX_HOME/plugins/cache`(기본 `~/.codex/plugins/cache`)를 더한다.
- 임시 파일: `<scratchpad>`를 "harness가 주는 scratchpad, 없으면 OS 임시 디렉터리(`python -c "import tempfile;print(tempfile.gettempdir())"`)"로 정의한다.

### 3.6 Codex 권한 설정

플러그인 동작에 필요한 것: Jira REST·`gh`·`git fetch/push`(네트워크), `git commit`·`worktree add`(`.git` 쓰기), 형제 worktree 쓰기. README Codex 절에 권장 설정을 둔다.

실측(2026-10-17, Windows, codex-cli 0.162.1):

- `windows.sandbox = "elevated"`는 비대화형 `codex exec`에서 초기 설정이 실패해(`helper_unknown_error: setup refresh had errors`) 모든 셸·파일 쓰기가 거부됐다. `"unelevated"`에서는 동작한다.
- workspace-write에서 `.git`은 `writable_roots`에 넣어도 쓰기 불가(`index.lock: Permission denied`) → `git commit`·`worktree add`·브랜치 생성이 샌드박스 안에서는 안 된다. 레포 밖 형제 worktree도 쓰기 불가.
- `network_access = true`면 Python HTTP(jira-cli)는 된다. `curl.exe`는 샌드박스 사용자 자격 문제(schannel)로 실패.
- 프로젝트 `.codex/rules`의 `prefix_rule(["git"])`은 적용되지 않았고, 사용자 rules 파일의 패턴은 `pwsh.exe -Command "<명령 전체>"` 단위라 접두어 허용이 사실상 안 된다.

결론: 이 플러그인은 단계마다 커밋하므로 샌드박스 안에서는 돌 수 없다. README Codex 절의 안내:

- 대화형 TUI: 기본 승인 모드로 쓰고, git·gh·worktree 명령의 권한 상승 요청을 승인한다.
- 또는 `--sandbox danger-full-access`(워크트리·`.git`·네트워크 전부 허용)로 실행한다. 보호 hook(승인 토큰·테스트 보호·worktree 삭제)은 샌드박스와 별개로 계속 동작한다.

## 4. 확인할 것 (실측)

Codex 실행(`codex exec`)은 사용자 Codex 계정으로 과금된다. 샌드박스(mock Jira + 가짜 gh)에서 다음을 확인한다.

1. 플러그인 hook이 trust 후 실행되는지, `apply_patch`·`Bash` 입력 형식, deny가 실제로 막는지.
2. 권장 권한 설정으로 git commit·worktree·네트워크가 되는지(Windows elevated 샌드박스).
3. L1 한 건을 start → test-write → impl(새 세션) → verify(새 세션) → pr까지.
4. L2 한 건의 approach → 승인 → build.

### 4.1 실측 결과 (2026-10-17, 사용자 Codex, `--dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust`, mock Jira + 가짜 gh)

- L1 DEMO-8: start(L1 확정·라벨·전이) → test-write(실패 테스트 커밋) → impl(구현 커밋, draft PR, 본문 "작성: Codex") → verify(self-mode, AC 2/2, 서명 `harness: Codex`) → pr(검토 중 전이) → 사람 머지 → done(완료 전이, 큐 제거). 단계마다 새 `codex exec` 세션.
- 테스트 보호: `activeRole=implementer`에서 `apply_patch`로 테스트 파일 수정 → hook 차단, 파일 불변.
- L2 DEMO-9: start가 L3를 제안하자 확정하지 않고 멈춤, approach는 등급 미확정으로 거부 → 담당자가 L2 확정 → approach가 질문 2건을 PR에 남기고 멈춤 → 답 반영(결정 사항 + 근거 링크) → 승인 요청 → 권한 없는 @po-park 승인은 `sdlc-gate.py`가 거부 → @lead-lee 승인 후 test-write → impl → verify(AC 7/7).
- 발견·수정: 기존 Codex 이식본(v0.62)이 함께 설치돼 있어 Codex가 같은 이름의 옛 스킬을 먼저 읽음 → 이식본 제거. verify가 오래된 로컬 `main`과 비교해 다른 작업 커밋을 범위 밖 변경으로 보고 → `agents/jira-reviewer.md`가 `origin/<Base>`를 쓰게(harness 무관 결함).
- 미확인: 대화형 TUI의 hook trust(`/hooks`)와 권한 상승 승인 흐름(사람이 직접 해야 함).

## 5. 구현 순서

1. 중립화: task-id·ask-user 공용 문서, CLAUDE.md 참조 정리, 작성 도구 동적화, scratchpad 정의, lookup 통일
2. guard hook의 `apply_patch` 지원 + 테스트
3. verify 세션 분리 문구
4. auto·loop의 Codex 안내
5. README Codex 절(설치, hook trust, 권한), 플러그인 `AGENTS.md`를 CLAUDE.md 지시로 교체
6. 실측(§4) → 결함 수정
7. 기존 이식본(`~/plugins/jira-claude-code-integration`, `personal` 마켓플레이스) 정리는 사용자 확인 후

## 6. Codex auto runner (v0.72.0)

사용자 결정(2026-10-20): auto는 Codex에서도 지원하고 loop·대시보드는 제외한다.

- **제어 흐름은 하나.** `scripts/auto-codex.js`가 `auto.workflow.js`를 읽어 `export const meta`만 걷어내고 async 함수 본문으로 실행한다. `args`·`agent`·`log`는 runner가 주입한다. 단계 순서·게이트·triage·fix loop를 두 벌로 두지 않는다.
- **`agent()` = 새 `codex exec` 프로세스.** `-C <worktree>`, `-s danger-full-access -c approval_policy=never`(단계마다 커밋·push·네트워크, §3.6), `--output-schema`(스키마 강제 반환)와 `-o`(마지막 메시지 파일). 프롬프트는 stdin. 단계마다 새 세션이라 test-write·impl·verify의 컨텍스트 분리는 Claude Code와 같다.
- **스키마.** codex `--output-schema`는 strict 형식(모든 키 required, `additionalProperties: false`)만 받는다. runner가 선택 키를 null 허용으로 바꿔 넣는다(`strictify`). 결과 JSON이 없거나 exit≠0이면 `agent()`가 null → 스크립트의 "결과 없이 종료됨" 중단.
- **프롬프트.** `args.harness = 'codex'`일 때만 세 곳이 바뀐다: 스킬 호출(`$jira-task-<step>`의 SKILL.md를 읽고 수행), 셸 규칙(Bash/PowerShell 도구 구분 제거), 반환 지시(StructuredOutput → 스키마에 맞는 JSON 하나). Claude Code 경로의 프롬프트는 문구 하나("Skill을 호출한다 (인자: …)") 외에 그대로다.
- **모델.** Claude 모델 이름은 추론 강도로 옮긴다: haiku→low, sonnet→medium, opus→high. 모델은 사용자 Codex 설정을 따르고 `--model`로 덮어쓴다.
- **launcher 몫.** 등급 확정은 사람 질문이 필요하므로 runner가 하지 않는다. context `level`이나 `cachedIssue.labels`의 `sdlc-L*`가 없으면 codex를 부르지 않고 `$jira-task-start`를 안내한다(exit 2). 결과 렌더링과 run-log 기록(`append-run-log.py`)은 runner가 한다.
- **실행 위치.** Codex 세션의 셸 명령은 긴 프로세스에 맞지 않아 사용자가 worktree 터미널에서 직접 실행한다. `$jira-task-auto`는 명령을 안내하고 멈춘다.
- **hook trust.** `codex exec`는 trust된 hook만 실행한다. trust 전이면 `--bypass-hook-trust`(→ `--dangerously-bypass-hook-trust`)로 보호 hook을 켠다. 활성화된 다른 hook도 함께 돌기 때문에 기본값으로 두지 않는다.
- **검증.** `tests/auto-codex.test.js`(가짜 codex `tests/fixtures/fake-codex.js`): L1 전 단계, fix loop, L2 승인 대기, 등급 미확정, worktree 불일치. 실측: codex-cli 0.162.1에서 strict 스키마 + `approval_policy=never` + `-o` 조합으로 결과 JSON 반환, 플러그인 hook 실행 확인.
- **실측 (2026-10-20, mock Jira + 가짜 gh, `--bypass-hook-trust`, 설치 스킬 0.71.0 + 저장소 scripts 0.72.0).** DEMO-1(L1): start → test-write → impl → verify 한 번에 `completed`(AC 3/3, 518초, 약 16만 토큰). DEMO-2(L2): 1회차 approach 뒤 `awaiting_approval` → 승인권자 `APPROVE plan <sha>` → 2회차 test-write가 승인 확인 통과 → `completed`(AC 3/3). 커밋 순서(test → feat), 두 context의 completedSteps, PR draft 유지, run-log 3줄 확인. verify 세션의 `apply_patch`가 `guard-test-files.js`에 막혀 hook이 `codex exec`에서 동작함을 확인.
- **실측에서 고친 것.** ① verifier 역할의 `guard-test-files.js`가 Edit·`apply_patch`로 worktree 밖 임시 파일을 쓰는 것까지 막아 `pr-body.md`의 `--body-file` 경로가 막혔다(셸은 이미 제외) → 저장소 밖 경로 제외를 모든 도구에 적용. ② 세션마다 Stop hook 1건 실패 — `stop-sync.js`가 Stop 출력 규격에 없는 최상위 `additionalContext`를 내보내 Codex가 실패로 처리했다(출력 없는 상태에서는 성공, 실측으로 대조). Claude Code에서도 무시되던 출력이라 hook을 제거했다. ③ Windows에서 python `subprocess.run(["gh"])`는 `.cmd`를 못 찾으므로 가짜 gh는 `.exe` shim이 필요했다(테스트 환경 한정).

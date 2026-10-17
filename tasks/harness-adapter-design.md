# harness 어댑터 설계 — 1부 Codex

> 상태: 초안 (2026-10-17). 범위 결정은 `tasks/sdlc-alignment-design.md` §2: 3단계는 어댑터만, Codex → Copilot 순서. 다른 harness에서는 단계 명령을 사람이 단계마다 새 세션으로 실행하고, auto·loop는 Claude Code 전용으로 둔다.

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
| auto·loop(Workflow, EnterWorktree) | 없음 | 범위 밖. Codex에서 호출하면 "Claude Code 전용" 안내 후 멈춤 |

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

## 5. 구현 순서

1. 중립화: task-id·ask-user 공용 문서, CLAUDE.md 참조 정리, 작성 도구 동적화, scratchpad 정의, lookup 통일
2. guard hook의 `apply_patch` 지원 + 테스트
3. verify 세션 분리 문구
4. auto·loop의 Codex 안내
5. README Codex 절(설치, hook trust, 권한), 플러그인 `AGENTS.md`를 CLAUDE.md 지시로 교체
6. 실측(§4) → 결함 수정
7. 기존 이식본(`~/plugins/jira-claude-code-integration`, `personal` 마켓플레이스) 정리는 사용자 확인 후

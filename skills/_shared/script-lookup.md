# Shared Script Lookup Pattern

플러그인 `scripts/` 하위 공용 스크립트의 절대 경로를 결정하는 표준 패턴. 스킬은 사용자 프로젝트(워크트리 포함)의 cwd에서 실행되므로 상대 경로만으로는 스크립트를 찾을 수 없다.

## 사용법

호출하는 스킬은 다음 변수를 셋업한 뒤 lookup 블록을 실행한다:

- `PLUGIN_ROOT` — 이 파일을 Read할 때 쓴 절대 경로에서 `/skills/_shared/script-lookup.md`를 뗀 값. 지금 로드된 플러그인의 루트다.
- `SCRIPT_NAME` — 찾을 스크립트 파일명 (예: `jira-attach.sh`, `jira-context-update.py`, `propagate-mcp-config.sh`, `append-review-log-wrapper.sh`, `cleanup-worktree-mcp.py`)
- `OUT_VAR` — 결과 절대 경로를 담을 변수명 (예: `JIRA_ATTACH_SH`, `PROPAGATE_SH`)

```bash
PLUGIN_ROOT="<이 파일 경로에서 /skills/_shared/script-lookup.md를 뗀 값>"
SCRIPT_NAME="<스크립트 파일명>"
OUT_VAR="<출력 변수명>"

# 0) PLUGIN_ROOT  1) CLAUDE_PLUGIN_ROOT  2) cwd  3) repoRoot(.jira-context.json)  4) 플러그인 캐시 최신 semver
# 캐시 fallback은 반드시 sort -V | tail -1로 최신 버전 선택. find ... | head -1은 stale 버전을 잡으므로 금지.
_resolved=""
for _c in "${PLUGIN_ROOT}/scripts/${SCRIPT_NAME}"           "${CLAUDE_PLUGIN_ROOT}/scripts/${SCRIPT_NAME}" \
          "scripts/${SCRIPT_NAME}" \
          "$(node -e "try{console.log(require('./.jira-context.json').repoRoot)}catch{}" 2>/dev/null)/scripts/${SCRIPT_NAME}" \
          "$(find "$HOME/.claude" -name "${SCRIPT_NAME}" -type f 2>/dev/null | sort -V | tail -1)"; do
  [ -n "$_c" ] && [ -f "$_c" ] && _resolved="$_c" && break
done
printf -v "$OUT_VAR" '%s' "$_resolved"
unset _resolved _c
```

찾지 못하면 `$OUT_VAR`는 빈 문자열. 호출자가 빈 값 처리(스킵 + 사용자 안내)를 책임진다.

## Batch Lookup (다중 스크립트, Bash 1회)

한 스킬이 스크립트를 2개 이상 쓰면 lookup을 개별 실행하지 말고 아래 블록 **1회**로 전부 결정한다. 개별 블록은 후보 나열 시 `find "$HOME/.claude"` 스캔이 매번 eager 실행되므로 호출 수만큼 비용이 쌓인다 — 이 블록은 앞 후보가 히트하면 find를 생략한다.

```bash
PLUGIN_ROOT="<이 파일 경로에서 /skills/_shared/script-lookup.md를 뗀 값>"
SCRIPT_NAMES="<파일명1> <파일명2> ..."   # 공백 구분

_repo_root=$(node -e "try{console.log(require('./.jira-context.json').repoRoot||'')}catch{}" 2>/dev/null)
for _n in $SCRIPT_NAMES; do
  if   [ -n "$PLUGIN_ROOT" ] && [ -f "${PLUGIN_ROOT}/scripts/${_n}" ]; then _r="${PLUGIN_ROOT}/scripts/${_n}"
  elif [ -n "$CLAUDE_PLUGIN_ROOT" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/${_n}" ]; then _r="${CLAUDE_PLUGIN_ROOT}/scripts/${_n}"
  elif [ -f "scripts/${_n}" ]; then _r="scripts/${_n}"
  elif [ -n "$_repo_root" ] && [ -f "${_repo_root}/scripts/${_n}" ]; then _r="${_repo_root}/scripts/${_n}"
  else _r=$(find "$HOME/.claude" -name "${_n}" -type f 2>/dev/null | sort -V | tail -1)
  fi
  echo "RESOLVED ${_n}=${_r:-NOT_FOUND}"
done
unset _repo_root _n _r
```

Bash 호출 간 변수는 유지되지 않으므로, 호출자는 `RESOLVED` 출력 경로를 **이후 단계에서 리터럴로 사용**한다. `NOT_FOUND`는 개별 lookup의 빈 문자열과 동일하게 처리(스킵 + 사용자 안내).

## Lookup 우선순위 근거

0. **`PLUGIN_ROOT`** — 스킬이 지금 Read하고 있는 플러그인. 설치본이든 `--plugin-dir` 개발본이든 실제로 로드된 버전과 일치한다. Bash 도구에는 `CLAUDE_PLUGIN_ROOT` 환경변수가 없으므로(그 변수는 hook·MCP 프로세스에만 주입되고, SKILL.md 본문의 `${CLAUDE_PLUGIN_ROOT}`는 로드 시점에 문자열로 치환될 뿐이다) 이 후보가 사실상 주 경로다.
1. **`CLAUDE_PLUGIN_ROOT`** — 환경변수가 주입된 실행 환경(hook 등)용.
2. **cwd `scripts/`** — 메인 레포에서 실행 중인 경우.
3. **`.jira-context.json`의 `repoRoot`** — 워크트리에서 실행 중일 때 메인 레포 경로 복원.
4. **플러그인 캐시 최신 semver** — `~/.claude/plugins/cache/.../scripts/`. `sort -V | tail -1`로 최신 선택. `head -1`은 stale 버전을 잡으므로 금지. `--plugin-dir`로 개발본을 로드하면 캐시는 설치본이라 버전이 어긋나므로 0번이 비면 안 된다.

## 신규 스크립트 추가

`scripts/` 하위에 신규 공용 스크립트 추가 시 별도 코드 변경 없이 자동 동작. 호출 스킬에서 `SCRIPT_NAME`만 새 파일명으로 바꿔 lookup 블록을 재사용한다.

# AGENTS.md

이 저장소는 Jira 워크플로 플러그인 `jira-integration`이다. Claude Code와 Codex에 같은 원본을 설치한다(설계: `tasks/harness-adapter-design.md`).

플러그인을 개발·유지보수하는 규칙은 **`CLAUDE.md`가 정본**이다. 작업을 시작하기 전에 `CLAUDE.md`를 읽고 그대로 따른다. 이 파일에 규칙을 복제하지 않는다 — 두 벌로 두면 한쪽이 낡는다.

Codex로 이 저장소를 작업할 때 추가로 지킬 것:

- `CLAUDE.md`의 Claude Code 도구 이름(Read, Edit, Skill 등)은 같은 일을 하는 Codex 도구로 읽는다.
- 스킬 본문을 고칠 때 harness마다 다른 동작은 `skills/_shared/conventions.md` "harness 차이"에만 쓴다. 스킬을 harness별로 나누지 않는다.
- `git worktree remove`를 직접 실행하지 않는다. worktree 삭제는 `scripts/clean-worktree.py`만 쓴다(이유는 `CLAUDE.md`).

---
name: jira
description: Show Jira integration status, available tools, and help for jira-task commands. Use when user types /jira, asks about Jira connection, or wants to see available Jira commands.
user-invocable: true
argument-hint: "[setup|dashboard]"
allowed-tools:
  - Read
  - Bash
  - Skill
---

# /jira - Jira Integration Help & Status

## Argument Parsing

If the argument is `setup`, run the setup wizard:
`Skill({ skill: "jira-integration:jira-setup" })`

If the argument starts with `dashboard` (e.g., `dashboard`, `dashboard start`, `dashboard stop`, `dashboard status`, `dashboard setup`), delegate to the dashboard skill:
`Skill({ skill: "jira-integration:jira-dashboard", args: "<remaining args after 'dashboard'>" })`

Otherwise, show the following information:

## 1. Connection Status

Check the Jira connection by running `python3 "<scripts>/jira-cli.py" whoami` (경로는 `skills/_shared/script-lookup.md`로 `SCRIPT_NAME="jira-cli.py"` 1회 해석; 규약: `skills/_shared/jira-cli.md`).

- If exit 0 (`{accountId, displayName, email}` 출력): report "Connected" (displayName 표시)
- If exit 1/2 (stderr `jira-cli: ...`): report "Not connected" and guide setup

Do NOT use `echo $JIRA_URL` to check credentials — 자격증명은 메인 레포 `.jira-context.json`의 `jira` 블록이 정본이며 셸 환경변수로 보이지 않을 수 있다. `jira` 블록 값(특히 `apiToken`)은 절대 출력하지 않는다.

If connection fails, guide the user to set credentials:
```
python3 "<scripts>/jira-cli.py" config set https://your-domain.atlassian.net your-email@company.com your-api-token [PROJECT]
```
(또는 환경변수 `JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN`)

## 2. Available Commands

Display the available workflow commands:

| Command | Description |
|---------|-------------|
| `/jira setup` | Interactive setup wizard for Jira MCP server registration |
| `/jira dashboard [start\|stop\|status\|setup]` | Dashboard 서버 관리 — 셋업/기동/중지/상태조회 (인자 없으면 자동 시작) |
| `/jira-task epic [set <키\|이름>\|show\|clear]` | 프로젝트 Epic 스코프(`.jira-epic.json`) 설정 — 이후 create가 이 Epic 아래에 이슈 생성 |
| `/jira-task create [힌트]` | 신규 Jira 이슈를 대화형으로 생성 (서브태스크/의존성/에픽 연결 포함) |
| `/jira-task init [N]` | Fetch my top N assigned tasks and create worktrees for each |
| `/jira-task auto <TASK-ID>` | 다음 사람 게이트까지 자동 진행 (L2·L3 승인 대기 / 리뷰 요청 준비됨에서 멈춤) |
| `/jira-task loop [prep\|plan\|build\|sync]` | init된 큐를 사람 게이트 단위 패스로 처리, 끝에 사람 할 일 리포트 |
| `/jira-task start <TASK-ID>` | 작업 시작 — worktree, 등급(L1/L2/L3) 확정, In Progress 전이 |
| `/jira-task approach <TASK-ID>` | L2·L3 산출물(`work/<KEY>/` intent·spec·plan) 작성, draft PR 승인 요청 |
| `/jira-task test-write <TASK-ID>` | 승인 확인 후 수용 조건별 실패 테스트를 먼저 커밋 |
| `/jira-task impl <TASK-ID>` | 테스트를 통과시키는 구현 (테스트 수정 불가), 지속 지식 옮기기 |
| `/jira-task verify <TASK-ID>` | 새 컨텍스트에서 수용 조건별 검증, `evidence/verification.md` |
| `/jira-task pr <TASK-ID>` | PR 본문 재생성, 리뷰 요청되면 Jira 검토 중 전이 |
| `/jira-task done <TASK-ID>` | PR 머지 확인 후 Jira 완료 전이 |
| `/jira-task report` | 내 할당 이슈 현황 리포트 |

## 3. Available jira-cli Subcommands

Briefly list the `jira-cli.py` subcommand categories (`skills/_shared/jira-cli.md`):
- **Issues**: get, search (JQL), create, update, transitions, transition, assign
- **Comments**: comment
- **Attachments**: attach
- **Sprints & Boards**: boards, sprints
- **Projects & Users**: projects, whoami
- **Issue Links**: link, link-types, epic-link
- **Config**: config set / config show

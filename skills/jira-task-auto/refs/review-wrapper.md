# Verify Wrapper 설계 근거

> jira-task-auto의 verify 단계 wrapper 설계와 scope shortfall 분기에 대한 배경 설명.

## Wrapper subagent_type을 `general-purpose`로 두는 이유

verify wrapper를 `jira-integration:jira-reviewer`로 두면 inner verifier와 2단 nesting이 생겨 부팅이 두 번 든다. wrapper는 `general-purpose`로 두고 `[verify-self-mode]` 마커로 `jira-task-verify` Skill이 wrapper 안에서 `agents/jira-reviewer.md`의 절차를 직접 수행하게 한다. wrapper 자체가 test-write·impl과 분리된 새 컨텍스트이므로 검증 세션 분리(SD-COM-VER-003)는 충족된다.

## Scope Shortfall 분기 근거

미충족 수용 조건이 많거나 Critical이 많으면 scope 자체가 빠진 상태다. fix sub-agent 한 번으로 부족분을 메우기 어렵고, fix loop이 같은 이유로 실패하며 시간만 쓴다. 이런 경우 사용자가 계획 수정·보완·분할 중에서 정해야 한다.

- 미충족 AC 비율 > 30% **또는** Critical ≥ 3 → fix loop 진입 금지, 즉시 중단.
- 그 외 → 최대 2회 자동 수정 루프.

분기 판정은 `scripts/auto.workflow.js`가 JS로 한다. 신호는 verify sub-agent가 schema 강제 StructuredOutput으로 반환하는 `metrics`에서 읽으므로 파싱 실패 경로가 없다. `verification.md` 맨 위 `<!-- verify-metrics -->` 블록은 사람·대시보드용 기록이다.

구버전(v0.69 이하)은 approach Implementation Plan 매칭률 70%를 썼다. 판정 단위가 수용 조건으로 바뀌면서 매칭률은 폐지했다.

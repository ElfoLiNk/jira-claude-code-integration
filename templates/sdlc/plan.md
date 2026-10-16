<!-- 표준 사본: mzd-software-development-standard 00-ai-native-sdlc-process v0.9.0b, templates/work/TASK-ID/plan.md (a599561). 이 줄은 플러그인 보관 표시라 산출물에 옮길 때 지운다. 플러그인 유지보수: 사본은 고치지 말고 표준이 바뀌면 통째로 교체. -->
<!--
L2·L3 작업에서 work/<작업 ID>/plan.md 로 복사해 씁니다 (SD-COM-ART-001·002).
대화를 보지 않은 엔지니어가 이 파일만 보고 구현할 수 있을 때까지 고칩니다.
승인 전에는 운영 코드를 고치지 않습니다 (SD-COM-GAT-004). 위험 신호가 있으면 기술 책임자가 승인합니다 (SD-COM-GAT-003).
구현이 계획과 달라지면 같은 PR에서 이 파일을 고치고 결정 기록에 남깁니다 (SD-COM-ART-007).
-->

# <작업 ID> 구현 계획

- 명세: [spec.md](spec.md)
- 위험 신호: 없음 | ① 스키마 ② API 계약 ③ 트랜잭션·동시성·멱등성 ④ 인증·권한·개인정보 ⑤ ADR 필요

## 참조

계획이 따르는 공통 문서와 표준을 링크합니다.

| 구분 | 문서 |
|---|---|
| 도메인 모델 | `docs/domain/order.md` |
| 구조 | `docs/architecture/overview.md` |
| 설계 결정 | `docs/decisions/0003-...md` |
| 조직 표준 | `docs/conventions/` 해당 장 |

## 바뀌는 파일

| 파일 | 바꾸는 내용 |
|---|---|
| | |

## 작업 순서

1. 
2. 
3. 계속 유지할 내용을 공통 문서로 옮긴다: 정책 → `docs/policies/`, 새 용어 → `docs/glossary.md`, 상태·불변식 → `docs/domain/`, 구조 → `docs/architecture/`, 설계 결정 → ADR (없으면 "없음") (SD-COM-ART-008)

## 위험

무엇이 잘못될 수 있는지, 되돌리는 방법은 무엇인지 적습니다.

## 검증 방법

| 수용 조건 | 테스트 또는 확인 방법 |
|---|---|
| AC-01 | |

## 결정 기록

구현 중 계획을 바꾼 내용과 이유를 날짜와 함께 적습니다.

- YYYY-MM-DD 

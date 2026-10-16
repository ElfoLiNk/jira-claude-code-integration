# 열린 PR이 base와 충돌할 때

다른 PR이 먼저 머지되어 base가 앞서 나가면 열린 PR이 충돌할 수 있다(`sdlc-gate.py pr-state`의 `mergeable: "CONFLICTING"`). rebase merge는 충돌을 풀어 주지 않으므로 코드 오너가 머지할 수 없다. `loop sync`는 이 태스크를 `base-conflict`로 격리하고, `pr`·`done`은 이 문서를 안내한다. 사용자가 해결을 지시하면 아래 순서로 한다.

stacked PR(context `stackedOn`)은 이 문서가 아니라 loop sync의 재정렬 절차를 따른다.

## 순서

1. worktree가 깨끗한지 확인하고 base 위로 옮긴다. 커밋되지 않은 변경이 있으면 멈추고 사용자에게 알린다(지우거나 stash하지 않는다).
   ```bash
   git -C "<worktreePath>" status --porcelain      # 비어 있어야 한다
   git -C "<worktreePath>" fetch origin <base>
   git -C "<worktreePath>" rebase origin/<base>
   ```
2. 충돌 파일을 나눠서 푼다. 역할은 context `activeRole`로 표시한다(`jira-context-update.py <KEY> - - <worktree ctx> --patch '{"activeRole":"..."}'`).
   - **테스트 파일**: `test-writer`로 푼다. 두 쪽 테스트를 모두 남기는 것이 원칙이다. 기대값을 바꿔야 하면 값마다 근거를 context `testExpectationChanges`에 남긴다(TA-COM-AGT-003). 근거가 없으면 멈추고 묻는다.
   - **운영 코드**: `implementer`로 푼다. 이 작업의 수용 조건과 base에 들어온 변경을 둘 다 살린다. 계획과 달라지면 `plan.md` 결정 기록에 적는다.
   - **`work/<KEY>/`**: 이 작업의 파일이라 충돌하지 않는다. 충돌했다면 다른 작업이 같은 키 폴더를 건드린 것이므로 멈추고 알린다.
   - 의미가 모호한 충돌(양쪽이 같은 동작을 다르게 바꿈)은 풀지 말고 `git rebase --abort` 후 사용자에게 넘긴다.
3. 충돌을 풀었으면 `git add <파일>` → `git rebase --continue`. 테스트 커밋(`test(<KEY>)`)을 지나는 중간 단계에서는 실패 테스트가 원래 실패하므로, 통과 확인은 rebase가 끝난 HEAD에서 이 작업의 테스트와 검사 명령으로 한다.
4. `git -C "<worktreePath>" push --force-with-lease origin feature/<KEY>` 후 역할 표시를 지운다(`--patch '{"activeRole":null}'`). rebase로 커밋 SHA가 바뀌었으므로 test 커밋도 다시 기록한다: `git log --format=%h --grep='^test(<KEY>)' origin/<base>..HEAD | tail -1`의 값을 `--patch '{"testWrite":{…기존 값, "commit":"<새 SHA>"}}'`로.
5. **다시 검증한다.** 검증 근거가 옛 base 기준이므로 `verify`를 지우고 새 세션에서 verify를 돌린다.
   ```bash
   python3 "$JIRA_CTX_UPDATE_PY" <KEY> - - "<worktree ctx>" "<aggregate>" --remove-step verify --patch '{"verifyResult":null}'
   ```
   검증을 통과하면 PR은 그대로 리뷰 요청 상태로 둔다(draft였으면 draft로). Jira에는 `## Rebased onto <base>`(충돌 파일, 재검증 결과)를 남긴다.
6. 격리 표시(`deferred`·`deferredKind`·`deferredReason`)는 다음 loop run이 지운다.

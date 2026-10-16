#!/usr/bin/env node

/**
 * PreToolUse Hook: block the agent from writing approval records.
 *
 * Why: scripts/sdlc-gate.py accepts a PR comment line `APPROVE <intent|spec|plan> <sha>`
 * from an approver account as the artifact approval (SD-COM-GAT-005). A local agent
 * usually runs `gh` under the same account as the developer, so it could post that
 * line itself. Agents must not approve (SD-COM-ROL-002), so:
 *   - `gh pr review --approve` is denied
 *   - gh / curl / jira-cli calls whose command text or body file carries the token are denied
 * A placeholder such as `APPROVE plan <SHA>` has no hex SHA and passes.
 *
 * Input (stdin): {"tool_name": "Bash"|"PowerShell", "tool_input": {"command": "..."}, "cwd": "..."}
 * Output: PreToolUse deny decision, or nothing (allow).
 */

const fs = require('fs');
const path = require('path');

const TOKEN = /\bAPPROVE\s+(intent|spec|plan)\s+[0-9a-f]{7,40}\b/i;
const CHANNEL = /\b(gh|curl|jira-cli\.py)\b/;
const GH_APPROVE = /\bgh\s+pr\s+review\b[^\n;&|]*(--approve\b|\s-a\b)/;
const BODY_FILE = /(?:--body-file|--input|-F)\s+["']?([^\s"';&|]+)/g;

function deny(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: reason,
    },
  }));
}

function main() {
  let input;
  try {
    input = JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    return;
  }
  const tool = input.tool_name || '';
  if (tool !== 'Bash' && tool !== 'PowerShell') return;
  const command = (input.tool_input && input.tool_input.command) || '';

  if (GH_APPROVE.test(command)) {
    return deny('에이전트는 PR을 승인하지 않는다 (SD-COM-ROL-002). 승인은 코드 오너가 직접 한다.');
  }
  if (!CHANNEL.test(command)) return;

  let carries = TOKEN.test(command);
  if (!carries) {
    const cwd = input.cwd || process.cwd();
    for (const m of command.matchAll(BODY_FILE)) {
      if (m[1] === '-') continue;
      try {
        if (TOKEN.test(fs.readFileSync(path.resolve(cwd, m[1]), 'utf8'))) carries = true;
      } catch {
        // 파일이 없으면 판정할 내용이 없다
      }
    }
  }
  if (carries) {
    deny('승인 토큰(APPROVE <intent|spec|plan> <SHA>)이 든 글은 쓸 수 없다 — 승인은 승인자가 본인 계정으로 남긴다 ' +
      '(SD-COM-GAT-005, ROL-002). 승인 요청에는 `APPROVE plan <SHA>`처럼 SHA 자리를 비운 안내와 SHA를 따로 적는다.');
  }
}

main();

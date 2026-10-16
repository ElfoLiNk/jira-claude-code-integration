#!/usr/bin/env node

/**
 * PreToolUse Hook: enforce role-based write limits for jira-task stages.
 *
 * Why: the implementation session must not change tests (TA-COM-AGT-005), and the
 * verification session must not change code (SD-COM-VER-003). Each stage writes its
 * role to the worktree-local .jira-context.json `activeRole` and clears it at the end.
 * AGENT_ROLE env (used by the 03 test-automation reference hook) wins when set.
 *
 *   implementer  — writes to test files are denied
 *   verifier     — every write is denied except work/<KEY>/evidence/
 *   test-writer / none — allowed
 *
 * Bash/PowerShell: only explicit write targets are judged (>, >>, tee, sed -i,
 * Set-Content/Add-Content/Out-File). The role file itself is editable by the agent;
 * CI and the review checklist are the final check.
 *
 * Input (stdin): {"tool_name": "...", "tool_input": {...}, "cwd": "..."}
 * Output: PreToolUse deny decision, or nothing (allow).
 */

const fs = require('fs');
const path = require('path');

const TEST_FILE = [
  /(^|\/)(test|tests|__tests__)\//,
  /(^|\/)src\/test\//,
  /\.(test|spec)\.[^/]+$/,
  /(^|\/)test_[^/]*\.py$/,
  /_test\.(py|go)$/,
];
const EVIDENCE = /(^|\/)work\/[^/]+\/evidence\//;

const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit']);
const SHELL_TARGETS = [
  /(?:^|[^0-9&>])>>?\s*["']?([^\s"';&|<>]+)/g,
  /\btee\s+(?:-a\s+)?["']?([^\s"';&|]+)/g,
  /\bsed\s+-i(?:\S*)?\s+(?:'[^']*'|"[^"]*"|\S+)\s+["']?([^\s"';&|]+)/g,
  /\b(?:Set-Content|Add-Content|Out-File)\b[^\n;|]*?(?:-(?:Path|FilePath)\s+)?["']([^"']+)["']/gi,
];

function readRole(cwd) {
  if (process.env.AGENT_ROLE) return process.env.AGENT_ROLE;
  try {
    return JSON.parse(fs.readFileSync(path.join(cwd, '.jira-context.json'), 'utf8')).activeRole || null;
  } catch {
    return null;
  }
}

function rel(cwd, p) {
  return path.relative(cwd, path.resolve(cwd, p)).split(path.sep).join('/');
}

function isTestFile(r) {
  return !r.startsWith('work/') && TEST_FILE.some((re) => re.test(r));
}

function targets(input, cwd) {
  const ti = input.tool_input || {};
  if (EDIT_TOOLS.has(input.tool_name)) {
    const p = ti.file_path || ti.notebook_path;
    return p ? [rel(cwd, p)] : [];
  }
  if (input.tool_name !== 'Bash' && input.tool_name !== 'PowerShell') return [];
  const out = [];
  for (const re of SHELL_TARGETS) {
    for (const m of (ti.command || '').matchAll(re)) {
      const r = rel(cwd, m[1]);
      // 저장소 밖(/tmp 등)과 /dev/null은 판정 대상이 아니다
      if (!r.startsWith('../') && !path.isAbsolute(r) && m[1] !== '/dev/null' && m[1] !== '$null') out.push(r);
    }
  }
  return out;
}

function main() {
  let input;
  try {
    input = JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    return;
  }
  const cwd = input.cwd || process.cwd();
  const role = readRole(cwd);
  if (role !== 'implementer' && role !== 'verifier') return;

  const files = targets(input, cwd);
  const blocked = role === 'implementer'
    ? files.filter(isTestFile)
    : files.filter((r) => !EVIDENCE.test(r));
  if (blocked.length === 0) return;

  const reason = role === 'implementer'
    ? `구현 세션은 테스트 파일을 고치지 않는다 (TA-COM-AGT-005): ${blocked.join(', ')}. ` +
      '테스트가 틀렸다고 판단되면 멈추고 사유를 보고한다 — test-write 단계로 되돌린다.'
    : `검증 세션은 코드를 고치지 않는다 (SD-COM-VER-003): ${blocked.join(', ')}. ` +
      'work/<KEY>/evidence/ 아래 증거 파일만 쓴다.';
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: reason,
    },
  }));
}

main();

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function run(script, input, env = {}) {
  const e = { ...process.env, ...env };
  if (!('AGENT_ROLE' in env)) delete e.AGENT_ROLE;
  const p = spawnSync(process.execPath, [path.join(__dirname, script)], { input: JSON.stringify(input), env: e, encoding: 'utf8' });
  return p.stdout ? JSON.parse(p.stdout).hookSpecificOutput.permissionDecision : 'allow';
}

function workdir(role) {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'guard-'));
  if (role) fs.writeFileSync(path.join(d, '.jira-context.json'), JSON.stringify({ activeRole: role }));
  return d;
}

const bash = (command, cwd) => ({ tool_name: 'Bash', tool_input: { command }, cwd });
const edit = (file_path, cwd) => ({ tool_name: 'Edit', tool_input: { file_path }, cwd });

// ─── guard-approval ──────────────────────────────────────────────────────

test('A1: gh pr comment에 승인 토큰 → deny', () => {
  assert.equal(run('guard-approval.js', bash('gh pr comment 7 --body "APPROVE plan 3f1b7d5"')), 'deny');
});

test('A2: SHA 자리를 비운 안내 → allow', () => {
  assert.equal(run('guard-approval.js', bash('gh pr comment 7 --body "APPROVE plan <SHA> (SHA = 3f1b7d5)"')), 'allow');
});

test('A3: gh pr review --approve → deny', () => {
  assert.equal(run('guard-approval.js', bash('gh pr review 7 --approve')), 'deny');
});

test('A4: body-file 안의 토큰 → deny', () => {
  const d = workdir();
  fs.writeFileSync(path.join(d, 'c.md'), '검토함\nAPPROVE spec abcdef0\n');
  assert.equal(run('guard-approval.js', bash('gh pr comment 7 --body-file c.md', d)), 'deny');
});

test('A5: gh·curl이 아닌 명령은 판정하지 않음', () => {
  assert.equal(run('guard-approval.js', bash('grep "APPROVE plan 3f1b7d5" tests/x.py')), 'allow');
});

// ─── guard-test-files ────────────────────────────────────────────────────

test('T1: implementer가 테스트 파일 Edit → deny', () => {
  const d = workdir('implementer');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'src/order.test.ts'), d)), 'deny');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'tests/test_order.py'), d)), 'deny');
});

test('T2: implementer가 운영 코드·spec.md Edit → allow', () => {
  const d = workdir('implementer');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'src/order.ts'), d)), 'allow');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'work/K-1/spec.md'), d)), 'allow');
});

test('T3: implementer가 Bash 리다이렉트로 테스트 파일 쓰기 → deny', () => {
  const d = workdir('implementer');
  assert.equal(run('guard-test-files.js', bash('echo x >> src/__tests__/a.js', d)), 'deny');
  assert.equal(run('guard-test-files.js', bash("sed -i 's/a/b/' tests/test_x.py", d)), 'deny');
  assert.equal(run('guard-test-files.js', bash('npm test > /tmp/out.log 2>&1', d)), 'allow');
});

test('T4: verifier는 evidence만 쓸 수 있음', () => {
  const d = workdir('verifier');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'src/order.ts'), d)), 'deny');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'work/K-1/evidence/verification.md'), d)), 'allow');
  assert.equal(run('guard-test-files.js', bash('npm test 2>&1 | tee work/K-1/evidence/test.log', d)), 'allow');
});

test('T5: test-writer와 역할 없음 → allow', () => {
  assert.equal(run('guard-test-files.js', edit('tests/test_x.py', workdir('test-writer'))), 'allow');
  assert.equal(run('guard-test-files.js', edit('tests/test_x.py', workdir())), 'allow');
});

test('T6: AGENT_ROLE 환경변수가 파일보다 우선', () => {
  const d = workdir('implementer');
  assert.equal(run('guard-test-files.js', edit(path.join(d, 'tests/test_x.py'), d), { AGENT_ROLE: 'test-writer' }), 'allow');
});

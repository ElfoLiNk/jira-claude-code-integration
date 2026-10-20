const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { strictify } = require('../scripts/auto-codex.js')

const RUNNER = path.join(__dirname, '..', 'scripts', 'auto-codex.js')
const FAKE = path.join(__dirname, 'fixtures', 'fake-codex.js')

function worktree(ctx) {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-codex-'))
  fs.writeFileSync(path.join(d, '.jira-context.json'), JSON.stringify({ taskId: 'DEMO-1', worktreePath: d, repoRoot: d, ...ctx }))
  return d
}

function run(cwd, scenario = 'pass', argv = []) {
  const log = path.join(cwd, 'calls.jsonl')
  const p = spawnSync(process.execPath, [RUNNER, ...argv], {
    cwd, encoding: 'utf8',
    env: { ...process.env, CODEX_BIN: FAKE, FAKE_CODEX_LOG: log, FAKE_CODEX_SCENARIO: scenario },
  })
  const calls = fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse) : []
  return { code: p.status, out: p.stdout + p.stderr, calls }
}

test('strictify: 모든 키 required, 선택 키는 null 허용, 중첩 객체도', () => {
  const s = strictify({
    type: 'object', required: ['a'],
    properties: { a: { type: 'string' }, b: { type: 'string', enum: ['x'] }, c: { type: 'array', items: { type: 'string' } },
      m: { type: 'object', required: ['n'], properties: { n: { type: 'integer' } } } },
  })
  assert.deepEqual(s.required, ['a', 'b', 'c', 'm'])
  assert.equal(s.additionalProperties, false)
  assert.deepEqual(s.properties.b, { type: ['string', 'null'], enum: ['x', null] })
  assert.deepEqual(s.properties.c.type, ['array', 'null'])
  assert.equal(s.properties.m.additionalProperties, false)
})

test('L1: start → test-write → impl → verify, 단계마다 새 codex exec, cwd는 worktree', () => {
  const d = worktree({ level: 'L1' })
  const r = run(d)
  assert.equal(r.code, 0, r.out)
  assert.deepEqual(r.calls.map((c) => c.step), ['start', 'test-write', 'impl', 'verify'])
  for (const c of r.calls) {
    assert.equal(path.resolve(c.cd), path.resolve(d))
    assert.ok(c.schemaStrict)
    assert.ok(c.argv.includes('danger-full-access'))
    assert.match(c.prompt, /\$jira-task-/)
    assert.doesNotMatch(c.prompt, /StructuredOutput|Bash 도구만/)
  }
  assert.ok(r.calls[0].argv.includes('model_reasoning_effort=low'))   // start = haiku
  assert.match(r.out, /리뷰 요청 준비됨/)
})

test('verify 미통과 → fix(implementer) → delta 재검증 → 통과', () => {
  const d = worktree({ level: 'L1', completedSteps: ['start', 'test-write', 'impl'] })
  const r = run(d, 'fix')
  assert.equal(r.code, 0, r.out)
  assert.deepEqual(r.calls.map((c) => c.step), ['verify', 'verify-fix', 'verify'])
  assert.match(r.calls[1].prompt, /AC-02 취소 권한 검사 누락/)
  assert.match(r.calls[2].prompt, /\[verify-delta-mode\]/)
})

test('L2 승인 전: approach 뒤 승인 대기로 멈춤', () => {
  const d = worktree({ level: 'L2', completedSteps: ['start'] })
  const r = run(d)
  assert.equal(r.code, 0, r.out)
  assert.deepEqual(r.calls.map((c) => c.step), ['approach'])
  assert.match(r.out, /대기/)
})

test('등급 미확정이면 codex를 부르지 않는다', () => {
  const d = worktree({})
  const r = run(d)
  assert.equal(r.code, 2)
  assert.equal(r.calls.length, 0)
  assert.match(r.out, /\$jira-task-start DEMO-1/)
})

test('worktree가 아닌 곳에서 실행하면 중단', () => {
  const d = worktree({ level: 'L1', worktreePath: path.join(os.tmpdir(), 'elsewhere') })
  const r = run(d)
  assert.equal(r.code, 2)
  assert.equal(r.calls.length, 0)
})

// auto-codex.js 테스트용 가짜 codex. `codex exec ... -o <file> -` 호출을 받아 단계별 결과 JSON을 쓴다.
// FAKE_CODEX_LOG: 호출 기록(JSONL), FAKE_CODEX_SCENARIO: pass | fix (첫 verify 미통과 → fix → 통과)
const fs = require('fs')

const argv = process.argv.slice(2)
const val = (flag) => argv[argv.indexOf(flag) + 1]
const logFile = process.env.FAKE_CODEX_LOG
const prompt = fs.readFileSync(0, 'utf8')
const calls = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : []

const fix = /검증 미통과 항목을 고쳐라/.test(prompt)
const step = fix ? 'verify-fix' : (/의 (\S+) 단계를 수행하라/.exec(prompt) || [])[1]
const schema = JSON.parse(fs.readFileSync(val('--output-schema'), 'utf8'))
fs.appendFileSync(logFile, JSON.stringify({ step, cd: val('-C'), argv, schemaStrict: schema.additionalProperties === false, prompt }) + '\n')

const steps = [...new Set(calls.map((c) => c.step).filter((s) => s && s !== 'verify-fix'))]
const verifyCount = calls.filter((c) => c.step === 'verify').length
const base = { step, result: 'success', cwdVerified: true, level: null, prUrl: 'https://github.com/o/r/pull/1', failureReason: null }
let out
if (step === 'verify') {
  const pass = process.env.FAKE_CODEX_SCENARIO !== 'fix' || verifyCount > 0
  out = {
    ...base,
    completedStepsAfter: pass ? [...steps, 'verify'] : steps,
    metrics: { acTotal: 4, acMet: pass ? 4 : 3, acUnmet: pass ? 0 : 1, acUnverified: 0, checksPassed: true, criticalCount: 0, warningCount: 0, infoCount: 0 },
    unmet: pass ? [] : ['AC-02 취소 권한 검사 누락 — src/order/cancel.ts:42'],
  }
} else if (step === 'verify-fix') {
  out = { ...base, completedStepsAfter: steps, filesEdited: ['src/order/cancel.ts'], converged: true, innerLoopIterations: 2, sensorSummary: null, testDispute: null }
} else {
  out = { ...base, completedStepsAfter: [...steps, step], gateStatus: 'not_required', gateDetail: null, awaitingArtifact: 'spec·plan', awaitingKind: 'approval' }
}
fs.writeFileSync(val('-o'), JSON.stringify(out))

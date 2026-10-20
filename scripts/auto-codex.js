#!/usr/bin/env node
// auto-codex.js: Codex CLI용 auto runner.
// auto.workflow.js(제어 흐름 단일 출처)를 그대로 로드하고, Workflow 도구의 agent()를 단계마다
// 새 `codex exec` 프로세스로 대신한다. 설계: tasks/harness-adapter-design.md §6.
//
// Usage (worktree에서): node <scriptsDir>/auto-codex.js [<TASK-ID>] [--model <m>] [--bypass-hook-trust]
// 환경변수: CODEX_BIN(기본 codex, .js면 node로 실행), PYTHON(기본 python3)
// exit: 0 completed·awaiting_approval / 1 그 밖의 status / 2 실행 전 중단

'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

// Claude 모델 등급 → Codex 추론 강도. 모델 자체는 사용자 Codex 설정(또는 --model)을 따른다.
const EFFORT = { haiku: 'low', sonnet: 'medium', opus: 'high' }

function parseArgs(argv) {
  const opts = { taskId: null, model: null, bypassHookTrust: false }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--model') opts.model = argv[++i]
    else if (a === '--bypass-hook-trust') opts.bypassHookTrust = true
    else if (!a.startsWith('-')) opts.taskId = a
    else throw new Error(`알 수 없는 옵션: ${a}`)
  }
  return opts
}

// codex --output-schema는 strict 형식(모든 키 required, additionalProperties false)을 요구한다.
// 선택 키는 null 허용으로 바꿔 required에 넣는다.
function strictify(schema) {
  if (!schema || typeof schema !== 'object') return schema
  const s = { ...schema }
  if (s.type === 'object' && s.properties) {
    const required = new Set(s.required || [])
    s.properties = Object.fromEntries(Object.entries(s.properties).map(([k, v]) => {
      let p = strictify(v)
      if (!required.has(k)) {
        const types = Array.isArray(p.type) ? p.type : [p.type]
        p = { ...p, type: types.includes('null') ? types : [...types, 'null'] }
        if (p.enum && !p.enum.includes(null)) p.enum = [...p.enum, null]
      }
      return [k, p]
    }))
    s.required = Object.keys(s.properties)
    s.additionalProperties = false
  }
  if (s.type === 'array' || (Array.isArray(s.type) && s.type.includes('array'))) {
    if (s.items) s.items = strictify(s.items)
  }
  return s
}

const samePath = (a, b) =>
  path.resolve(a).replace(/[\\/]+$/, '').toLowerCase() === path.resolve(b).replace(/[\\/]+$/, '').toLowerCase()

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return null }
}

function resolveRepoRoot(ctx, cwd) {
  if (ctx.repoRoot) return ctx.repoRoot
  const r = spawnSync('git', ['worktree', 'list', '--porcelain'], { cwd, encoding: 'utf8' })
  const m = r.status === 0 && /^worktree (.+)$/m.exec(r.stdout)
  return m ? m[1].trim() : null
}

function levelOf(ctx, taskId) {
  if (ctx.level) return ctx.level
  const labels = (ctx.cachedIssue && ctx.cachedIssue.key === taskId && ctx.cachedIssue.labels) || []
  const hit = labels.map((l) => /^sdlc-(L[123])$/.exec(l)).find(Boolean)
  return hit ? hit[1] : null
}

function quoteWin(a) {
  return /[\s"&|<>^]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a
}

function runCodex(bin, codexArgs, prompt, logFile) {
  return new Promise((resolve) => {
    const out = fs.openSync(logFile, 'w')
    let child
    if (bin.endsWith('.js')) {
      child = spawn(process.execPath, [bin, ...codexArgs], { stdio: ['pipe', out, out] })
    } else if (process.platform === 'win32') {
      // npm 설치 codex는 .cmd shim이라 셸 없이 spawn할 수 없다
      child = spawn([bin, ...codexArgs].map(quoteWin).join(' '), { shell: true, stdio: ['pipe', out, out] })
    } else {
      child = spawn(bin, codexArgs, { stdio: ['pipe', out, out] })
    }
    child.on('error', (e) => { fs.closeSync(out); resolve({ code: -1, error: e.message }) })
    child.on('close', (code) => { fs.closeSync(out); resolve({ code }) })
    child.stdin.end(prompt)
  })
}

function makeAgent({ worktreePath, runDir, opts, bin }) {
  let seq = 0
  return async function agent(prompt, { label, model, schema }) {
    seq++
    const stem = `${String(seq).padStart(2, '0')}-${String(label).replace(/[^\w.-]+/g, '_')}`
    const schemaFile = path.join(runDir, `${stem}.schema.json`)
    const lastFile = path.join(runDir, `${stem}.last.json`)
    const logFile = path.join(runDir, `${stem}.log`)
    fs.writeFileSync(schemaFile, JSON.stringify(strictify(schema)))
    const codexArgs = [
      'exec', '-C', worktreePath,
      // 단계마다 커밋·push·Jira 호출을 하므로 샌드박스 안에서는 돌지 않는다 (harness-adapter-design §3.6)
      '-s', 'danger-full-access', '-c', 'approval_policy=never',
      '-c', `model_reasoning_effort=${EFFORT[model] || 'medium'}`,
      '--output-schema', schemaFile, '-o', lastFile,
    ]
    if (opts.model) codexArgs.push('-m', opts.model)
    if (opts.bypassHookTrust) codexArgs.push('--dangerously-bypass-hook-trust')
    codexArgs.push('-')
    const t0 = Date.now()
    console.log(`▶ ${label} (effort ${EFFORT[model] || 'medium'}) — 로그: ${logFile}`)
    const r = await runCodex(bin, codexArgs, prompt, logFile)
    const sec = Math.round((Date.now() - t0) / 1000)
    const result = readJson(lastFile)
    if (r.code !== 0 || !result) {
      console.log(`  ✗ ${label} ${sec}s — codex exit ${r.code}${r.error ? ` (${r.error})` : ''}${result ? '' : ', 결과 JSON 없음'}`)
      return result || null
    }
    console.log(`  ✓ ${label} ${sec}s — ${result.result}`)
    return result
  }
}

function render(taskId, r) {
  const steps = (r.completedSteps || []).join(', ') || '없음'
  const pr = r.prUrl || '-'
  const unmet = (r.unmet || []).map((u) => `  - ${u}`).join('\n')
  const m = r.metrics || {}
  switch (r.status) {
    case 'completed':
      return `✅ 리뷰 요청 준비됨 — ${taskId}\n- 수용 조건: ${m.acMet}/${m.acTotal} 충족 (미확인 ${m.acUnverified})\n- fix loop: ${r.fixAttempts}회\n- PR: ${pr} (draft)\n\ndiff와 검증 결과를 직접 확인한 뒤 \`gh pr ready <번호>\`로 리뷰를 요청하세요. 머지는 코드 오너가 합니다.\n머지 뒤: \`$jira-task-done ${taskId}\``
    case 'awaiting_approval':
      if (r.awaitingKind === 'answers') {
        return `⏸ 답변 대기 — ${taskId} (${r.artifact})\n- PR: ${pr} (draft)\n\n승인자가 PR의 질문에 답하면 runner를 다시 실행하세요. spec에 반영하고 승인을 요청합니다.`
      }
      return `⏸ 승인 대기 — ${taskId} (${r.artifact})\n- PR: ${pr} (draft)${r.gateDetail ? `\n- 승인 확인 결과 — ${r.gateDetail}` : ''}\n\n승인자가 PR에 \`APPROVE <plan|intent|spec> <SHA>\` 한 줄을 남기면 runner를 다시 실행해 이어서 진행합니다.`
    case 'level_unconfirmed':
      return `⏸ 등급이 확정되지 않아 멈췄습니다. Codex 세션에서 \`$jira-task-start ${taskId}\`로 등급을 확정하세요.`
    case 'aborted':
      return `❌ Auto 모드 중단: ${r.failedStage} 단계 실패\n원인: ${r.reason}\n현재 진행: ${steps}\n해결 후 다시 실행하거나 해당 단계를 직접 실행하세요: \`$jira-task-${r.failedStage === 'verify-fix' ? 'impl' : r.failedStage} ${taskId}\``
    case 'scope_shortfall':
      return `❌ Auto 모드 중단 (scope shortfall): 미충족 수용 조건 ${m.acUnmet}/${m.acTotal}, Critical ${m.criticalCount}건 (기준: 미충족 2건 이상이면서 30% 초과, 또는 Critical 3건 이상)\n${unmet}\n단일 수정으로 메우기 어려운 누락으로 보여 자동 수정을 건너뜁니다. plan.md·spec.md를 고쳐 재승인받거나, 직접 보완한 뒤 \`$jira-task-verify ${taskId}\`, 또는 미충족 범위를 새 이슈로 나누세요.`
    case 'fix_unconverged':
      return `❌ Auto 모드 중단: 수정이 lint/typecheck/이 작업의 테스트로 수렴하지 않았습니다 (inner loop ${r.innerLoopIterations}회)\n마지막 센서 출력: ${r.sensorSummary || '-'}\nworktree에서 직접 고친 뒤: \`$jira-task-verify ${taskId}\``
    case 'fix_exhausted':
      return `❌ Auto 모드 중단: 검증을 2회 수정 후에도 통과하지 못했습니다.\n미해결:\n${unmet}\n검증 결과: work/${taskId}/evidence/verification.md (L1은 PR 본문)`
    case 'test_dispute':
      return `⏸ 테스트 이견 — 구현 세션이 테스트가 틀렸다고 판단했습니다 (테스트는 고치지 않았습니다).\n사유: ${r.testDispute}\n테스트를 고칠지 사용자가 정합니다: 고치려면 사유를 남기고 \`$jira-task-test-write ${taskId}\`, 아니면 \`$jira-task-impl ${taskId}\`.`
    default:
      return `결과: ${JSON.stringify(r)}`
  }
}

async function main() {
  let opts
  try { opts = parseArgs(process.argv.slice(2)) } catch (e) { console.error(`❌ ${e.message}`); return 2 }
  const cwd = process.cwd()
  const ctxFile = path.join(cwd, '.jira-context.json')
  const ctx = readJson(ctxFile)
  if (!ctx) { console.error('❌ 이 디렉터리에 .jira-context.json이 없습니다. 작업 worktree에서 실행하세요.'); return 2 }
  const taskId = opts.taskId || ctx.taskId
  if (!taskId) { console.error('❌ TASK-ID를 찾지 못했습니다. 인자로 넘기세요.'); return 2 }
  if (ctx.worktreePath && !samePath(ctx.worktreePath, cwd)) {
    console.error(`❌ worktree가 아닙니다. \`cd ${ctx.worktreePath}\` 후 다시 실행하세요.`); return 2
  }
  const level = levelOf(ctx, taskId)
  if (!level) { console.log(render(taskId, { status: 'level_unconfirmed' })); return 2 }

  const repoRoot = resolveRepoRoot(ctx, cwd)
  const aggregate = repoRoot && path.join(repoRoot, '.jira-context.json')
  const ctxFiles = [ctxFile, ...(aggregate && fs.existsSync(aggregate) && !samePath(aggregate, ctxFile) ? [aggregate] : [])]
  const scriptsDir = __dirname.replace(/\\/g, '/')
  const args = {
    taskId, worktreePath: cwd.replace(/\\/g, '/'), completedSteps: ctx.completedSteps || [], level,
    ctxFiles: ctxFiles.map((f) => f.replace(/\\/g, '/')), scriptsDir, harness: 'codex',
  }

  const runDir = fs.mkdtempSync(path.join(os.tmpdir(), `jira-auto-${taskId}-`))
  console.log(`🚀 Auto 모드 (Codex): ${taskId} (${level})\n완료된 단계: ${args.completedSteps.join(', ') || '없음'}\n다음 사람 게이트까지 진행합니다. 단계 로그: ${runDir}`)

  // auto.workflow.js는 Workflow 도구용 스크립트(최상위 await·return)라 함수 본문으로 감싸 실행한다
  const src = fs.readFileSync(path.join(__dirname, 'auto.workflow.js'), 'utf8').replace(/^export const meta =/m, 'const meta =')
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
  const workflow = new AsyncFunction('args', 'agent', 'log', src)
  const agent = makeAgent({ worktreePath: args.worktreePath, runDir, opts, bin: process.env.CODEX_BIN || 'codex' })
  const result = await workflow(args, agent, (msg) => console.log(`· ${msg}`))

  console.log(`\n${render(taskId, result)}`)

  if (repoRoot) {
    const py = spawnSync(process.env.PYTHON || 'python3',
      [path.join(__dirname, 'append-run-log.py'), taskId, '-', ctxFile, path.join(repoRoot, 'docs', 'run-log')],
      { input: JSON.stringify(result), encoding: 'utf8' })
    if (py.status !== 0) console.log('⚠ run-log 기록 실패 (결과에는 영향 없음)')
  }
  return ['completed', 'awaiting_approval'].includes(result.status) ? 0 : 1
}

if (require.main === module) {
  main().then((code) => process.exit(code), (e) => { console.error(`❌ ${e.stack || e}`); process.exit(1) })
}

module.exports = { strictify, parseArgs, levelOf }

export const meta = {
  name: 'sdlc-build',
  description: 'AI-native SDLC 第 3 段 Build：紅燈測試 → 依相依分層、每層子任務在各自 worktree 平行實作 → integrator 合併到 feature/<epic>',
  whenToUse: 'sdlc-design 的 spec＋plan 核准之後；args 加 subtasks（sdlc-design 回傳的 design.payload.subtasks）',
  phases: [
    { title: 'Red', detail: 'dev-acceptance-tester：每個 test 子任務一個，平行寫紅燈測試' },
    { title: 'Implement', detail: 'dev-implementer：同一層的子任務平行，各自 worktree' },
    { title: 'Integrate', detail: 'dev-integrator：每層合併並跑驗證' },
  ],
}

// plugin 的 agent 帶命名空間（init.sh 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const BUILD = /*@schema:build-result*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["task_id","branch","commits","files_changed","tests"],"properties":{"task_id":{"type":"string"},"branch":{"type":"string"},"worktree":{"type":"string"},"commits":{"type":"array","items":{"type":"string"}},"files_changed":{"type":"array","items":{"type":"string"}},"tests":{"type":"array","items":{"type":"object","required":["command","result"],"properties":{"command":{"type":"string"},"result":{"type":"string","enum":["pass","fail","red_as_expected","not_run"]},"summary":{"type":"string"}}}},"conflicts":{"type":"array","items":{"type":"object","required":["file","kind","resolution"],"properties":{"file":{"type":"string"},"kind":{"type":"string","enum":["mechanical","seam","judgement","implicit_compile","implicit_behavior","generated"]},"resolution":{"type":"string"}}}}}}}} /*@end*/

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir', 'subtasks']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}（分支 feature/${A.epic}）\nspec：${SPEC}/spec.md、plan.md、progress.md\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。不 push。commit 結尾 Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>。` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')
const MAX_RETRY = 2

const all = A.subtasks
const ids = new Set(all.map((s) => s.id))
const tests = all.filter((s) => s.kind === 'test')
const work = all.filter((s) => s.kind === 'code' || s.kind === 'doc')
const skipped = all.filter((s) => !['test', 'code', 'doc'].includes(s.kind))
if (skipped.length) log(`不屬於 Build 的子任務不處理：${skipped.map((s) => `${s.id}(${s.kind})`).join('、')}`)

// 依相依分層（test 子任務在 Red 先做完，視為已滿足）
const done = new Set(tests.map((s) => s.id))
const layers = []
let rest = work.slice()
while (rest.length) {
  const ready = rest.filter((s) => (s.depends_on || []).every((d) => done.has(d) || !ids.has(d)))
  if (!ready.length) throw new Error(`子任務相依有循環或缺項：${rest.map((s) => s.id).join('、')}`)
  layers.push(ready)
  ready.forEach((s) => done.add(s.id))
  rest = rest.filter((s) => !ready.includes(s))
}
log(`Red ${tests.length} 個；實作分 ${layers.length} 層：${layers.map((l) => l.map((s) => s.id).join('+')).join(' → ')}`)

const taskBrief = (s) => `子任務 ${s.id}「${s.title}」\n擁有（只能改）：${(s.owns || []).join('、')}\n完成條件：${(s.acceptance || []).join('；')}\nStory：${(s.story_ids || []).join('、') || '見 spec'}`
const wtFor = (s) => `${A.repo}/.worktrees/${A.epic}--${s.id}`

function runTask(s, role, phaseName, extra) {
  return (async () => {
    let res = null
    for (let attempt = 1; attempt <= MAX_RETRY + 1; attempt++) {
      res = await agent(
        `${CTX}\n\n## 派工單（${phaseName}，第 ${attempt} 次）\n${taskBrief(s)}\n` +
        `在自己的 worktree 做：git -C "${A.repo}" worktree add .worktrees/${A.epic}--${s.id} -b feature/${A.epic}--${s.id} feature/${A.epic}（已存在就沿用）。worktree：${wtFor(s)}。\n${extra}\n` +
        (attempt > 1 && res ? `上一次的結果（請修正）：${JSON.stringify({ status: res.status, summary: res.summary, open_questions: res.open_questions })}\n` : '') +
        `payload 用 build-result（task_id=${s.id}、branch=feature/${A.epic}--${s.id}、worktree=${wtFor(s)}）。`,
        { label: `${phaseName}:${s.id}${attempt > 1 ? `#${attempt}` : ''}`, phase: phaseName, agentType: role, schema: BUILD },
      )
      if (!res || res.status !== 'blocked') break // done 或 needs_decision 都不重試；needs_decision 交人
    }
    return res
  })()
}

async function integrate(batch, label) {
  return agent(
    `${CTX}\n\n## 派工單（整合：${label}）\n依序把這些分支 git merge --no-ff 進 feature/${A.epic}（在 ${EPIC_DIR} 操作）：\n` +
    batch.map((r) => `- ${r.payload.branch}（${r.payload.task_id}）`).join('\n') +
    `\n有衝突照目標 repo 的分支與合併規範用中轉分支解並分類。合完跑 rules.md 專案規則的 verify 指令（基準 ${A.base || 'origin/main'}；沒有就用該 repo 的對等指令），全綠後移除這些子任務的 worktree 與分支。\npayload 用 build-result（task_id=${label}、branch=feature/${A.epic}）。`,
    { label: `integrate:${label}`, phase: 'Integrate', agentType: NS + 'dev-integrator', schema: BUILD },
  )
}

const results = { red: [], layers: [], integrations: [] }

phase('Red')
if (tests.length) {
  const red = (await parallel(tests.map((s) => () => runTask(s, NS + 'dev-acceptance-tester', 'Red',
    '依 spec 的驗收條件寫會失敗的測試；跑一次確認「以預期的理由失敗」（tests[].result=red_as_expected），commit test(<Story>): …。')))).filter(Boolean)
  results.red = red
  const ok = red.filter((r) => r.status === 'done')
  if (ok.length) results.integrations.push(await integrate(ok, 'red'))
  if (ok.length < tests.length) return { stage: 'build', halted: 'Red 有子任務沒完成，停下交人', ...results }
}

for (let i = 0; i < layers.length; i++) {
  phase('Implement')
  const layer = layers[i]
  const res = (await parallel(layer.map((s) => () => runTask(s, NS + 'dev-implementer', 'Implement',
    '讓驗收測試轉綠；單元測試 TDD；只改擁有的檔案；本子任務範圍的 verify 指令全綠才 commit feat(<Story>): …；不要改 progress.md（它由主 session 依 integrator 的合併結果維護，不屬於任何子任務的 owns）。')))).filter(Boolean)
  results.layers.push(res)
  const ok = res.filter((r) => r.status === 'done')
  phase('Integrate')
  if (ok.length) results.integrations.push(await integrate(ok, `layer${i + 1}`))
  if (ok.length < layer.length) return { stage: 'build', halted: `第 ${i + 1} 層有子任務沒完成，停下交人`, ...results }
}

return { stage: 'build', gate: null, next: 'sdlc-test', ...results }

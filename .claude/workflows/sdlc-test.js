export const meta = {
  name: 'sdlc-test',
  description: 'AI-native SDLC 第 4 段 Test：verifier 逐條驗收＋反作弊，同時平行跑設計審查與安全審查；fail 時修正並重驗（最多 2 輪），停在驗證結果確認閘門',
  whenToUse: 'sdlc-build 完成後；args 加 has_ui、has_security（布林）',
  phases: [
    { title: 'Verify', detail: 'dev-verifier＋dev-design-reviewer＋dev-security-reviewer 平行' },
    { title: 'Fix', detail: 'fail 的驗收條件交 dev-implementer 修，最多 2 輪' },
  ],
}

// plugin 的 agent 帶命名空間（init.sh 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const CRITERIA = /*@schema:criteria*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["commit","scope_covered","scope_skipped","criteria"],"properties":{"commit":{"type":"string"},"scope_covered":{"type":"string"},"scope_skipped":{"type":"string"},"criteria":{"type":"array","minItems":1,"items":{"type":"object","required":["id","criterion","command","result","evidence"],"properties":{"id":{"type":"string"},"criterion":{"type":"string"},"command":{"type":"string"},"result":{"type":"string","enum":["pass","fail","not_verifiable"]},"evidence":{"type":"string"},"repro":{"type":"string"}}}},"anti_cheat":{"type":"array","items":{"type":"string"}}}}}} /*@end*/
const FINDINGS = /*@schema:findings*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["lens","findings"],"properties":{"lens":{"type":"string"},"findings":{"type":"array","items":{"type":"object","required":["id","severity","claim","location","recommendation","confidence"],"properties":{"id":{"type":"string"},"severity":{"type":"string","enum":["important","nit","pre_existing","info","blocker","should_fix"]},"claim":{"type":"string"},"location":{"type":"string"},"recommendation":{"type":"string"},"confidence":{"type":"number","minimum":0,"maximum":1},"quote":{"type":"string"}}}}}}}} /*@end*/
const BUILD = /*@schema:build-result*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["task_id","branch","commits","files_changed","tests"],"properties":{"task_id":{"type":"string"},"branch":{"type":"string"},"worktree":{"type":"string"},"commits":{"type":"array","items":{"type":"string"}},"files_changed":{"type":"array","items":{"type":"string"}},"tests":{"type":"array","items":{"type":"object","required":["command","result"],"properties":{"command":{"type":"string"},"result":{"type":"string","enum":["pass","fail","red_as_expected","not_run"]},"summary":{"type":"string"}}}},"conflicts":{"type":"array","items":{"type":"object","required":["file","kind","resolution"],"properties":{"file":{"type":"string"},"kind":{"type":"string","enum":["mechanical","seam","judgement","implicit_compile","implicit_behavior","generated"]},"resolution":{"type":"string"}}}}}}}} /*@end*/

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}（分支 feature/${A.epic}，比對基準 ${A.base || 'origin/main'}）\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')
const MAX_FIX = 2

const verify = (round) => agent(
  `${CTX}\n\n## 派工單（驗證，第 ${round} 輪）\n在 ${EPIC_DIR} 的目前 HEAD 逐條驗證 ${SPEC}/spec.md 的驗收條件，做反作弊檢查，照範本寫 ${SPEC}/verifier.md （repo 有 verifier 檢查腳本就跑）。payload 用 criteria。`,
  { label: `verify#${round}`, phase: 'Verify', agentType: NS + 'dev-verifier', schema: CRITERIA },
)

phase('Verify')
const jobs = [() => verify(1)]
if (A.has_ui) jobs.push(() => agent(`${CTX}\n\n## 派工單\n設計審查 feature/${A.epic} 的畫面改動，寫 ${SPEC}/design-review.md 與 ${SPEC}/evidence/。payload 用 findings（lens=design）。`, { label: 'design-review', phase: 'Verify', agentType: NS + 'dev-design-reviewer', schema: FINDINGS }))
if (A.has_security) jobs.push(() => agent(`${CTX}\n\n## 派工單\n安全審查 feature/${A.epic}（git diff ${A.base || 'origin/main'}...HEAD），寫 ${SPEC}/security-review.md。payload 用 findings（lens=security）。`, { label: 'security-review', phase: 'Verify', agentType: NS + 'dev-security-reviewer', schema: FINDINGS }))
const [first, ...reviews] = await parallel(jobs)

let current = first
const fixes = []
for (let round = 1; round <= MAX_FIX && current; round++) {
  const failed = (current.payload.criteria || []).filter((c) => c.result === 'fail')
  const cheats = current.payload.anti_cheat || []
  if (!failed.length && !cheats.length) break
  phase('Fix')
  log(`第 ${round} 輪修正：fail ${failed.length} 條、反作弊 ${cheats.length} 項`)
  const fix = await agent(
    `${CTX}\n\n## 派工單（修正第 ${round} 輪）\n在 ${EPIC_DIR}（feature/${A.epic}）修正下列失敗；測試失敗就改程式、不改測試，不加 skip／retry、不放寬斷言。修完 commit fix(<Story>): …。\n失敗：${JSON.stringify(failed)}\n反作弊發現：${JSON.stringify(cheats)}\npayload 用 build-result（task_id=fix${round}、branch=feature/${A.epic}、worktree=${EPIC_DIR}）。`,
    { label: `fix#${round}`, phase: 'Fix', agentType: NS + 'dev-implementer', schema: BUILD },
  )
  fixes.push(fix)
  if (!fix || fix.status !== 'done') break
  phase('Verify')
  current = await verify(round + 1)
}

const summary = current ? (current.payload.criteria || []).reduce((m, c) => (m[c.result] = (m[c.result] || 0) + 1, m), {}) : null
return { stage: 'test', gate: '驗證結果確認（fail 或 not_verifiable 由人決定）', verifier: current, reviews: reviews.filter(Boolean), fixes, summary }

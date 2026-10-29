export const meta = {
  name: 'sdlc-test',
  description: 'AI-native SDLC 第 4 段 Test：verifier 逐條驗收＋反作弊（有子計劃時每個子計劃一個 verifier 平行驗證，再彙整成 verifier.md），同時平行跑設計審查與安全審查；fail 時修正並重驗（最多 2 輪，多個子計劃都有失敗時平行修正再合併），停在驗證結果確認閘門',
  whenToUse: 'sdlc-build 完成後；args 加 has_ui、has_security（布林），有子計劃時加 sub_plans（sdlc-design 回傳的 sub_plans）',
  phases: [
    { title: 'Verify', detail: 'dev-verifier（有子計劃時分片平行）＋dev-design-reviewer＋dev-security-reviewer 平行' },
    { title: 'Consolidate', detail: '分片驗證時：dev-verifier 把各分片報告彙整成 verifier.md，workflow 確定性核對' },
    { title: 'Fix', detail: 'fail 的驗收條件交 dev-implementer 修，最多 2 輪；多個分片都有失敗時各自 worktree 平行修' },
    { title: 'Integrate', detail: '平行修正後 dev-integrator 合併' },
  ],
}

// plugin 的 agent 帶命名空間（init.py 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const CRITERIA = /*@schema:criteria*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["commit","scope_covered","scope_skipped","criteria"],"properties":{"commit":{"type":"string"},"scope_covered":{"type":"string"},"scope_skipped":{"type":"string"},"criteria":{"type":"array","minItems":1,"items":{"type":"object","required":["id","criterion","command","result","evidence"],"properties":{"id":{"type":"string"},"criterion":{"type":"string"},"command":{"type":"string"},"result":{"type":"string","enum":["pass","fail","not_verifiable"]},"evidence":{"type":"string"},"repro":{"type":"string"}}}},"anti_cheat":{"type":"array","items":{"type":"string"}}}}}} /*@end*/
const FINDINGS = /*@schema:findings*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["lens","findings"],"properties":{"lens":{"type":"string"},"findings":{"type":"array","items":{"type":"object","required":["id","severity","claim","location","recommendation","confidence"],"properties":{"id":{"type":"string"},"severity":{"type":"string","enum":["important","nit","pre_existing","info","blocker","should_fix"]},"claim":{"type":"string"},"location":{"type":"string"},"recommendation":{"type":"string"},"confidence":{"type":"number","minimum":0,"maximum":1},"quote":{"type":"string"}}}}}}}} /*@end*/
const BUILD = /*@schema:build-result*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["task_id","branch","commits","files_changed","tests"],"properties":{"task_id":{"type":"string"},"branch":{"type":"string"},"worktree":{"type":"string"},"commits":{"type":"array","items":{"type":"string"}},"files_changed":{"type":"array","items":{"type":"string"}},"tests":{"type":"array","items":{"type":"object","required":["command","result"],"properties":{"command":{"type":"string"},"result":{"type":"string","enum":["pass","fail","red_as_expected","not_run"]},"summary":{"type":"string"}}}},"conflicts":{"type":"array","items":{"type":"object","required":["file","kind","resolution"],"properties":{"file":{"type":"string"},"kind":{"type":"string","enum":["mechanical","seam","judgement","implicit_compile","implicit_behavior","generated"]},"resolution":{"type":"string"}}}}}}}} /*@end*/

// 開發規範 profile（methodology）：init.py 依使用者選的 profile 與回答的慣例寫 .claude/teams/methodology.json，
// build.py 內嵌到這裡；不要手改，改 profile 後重跑 build.py。null＝沒有 profile，改用中性指引（依目標 repo 既有慣例）。
const METHODOLOGY = /*@methodology*/ {"name":"default","description":"預設 profile（模版原本的做法）：spec 驅動，驗收條件用 EARS 句型，測試先行（先寫會失敗的驗收測試再實作），Conventional Commits 加 Story scope，PR 修改既有檔上限 300 行或 15 檔。","stages":{"plan":{"artifacts":["intent.md"],"template":"問題、期望結果、受影響的使用者與系統、限制、待解問題","guidance":"intent 只寫問題空間，不寫解法；每個主張附出處；最多 5 個待釐清問題，blocking 的附 2–3 個選項與代價。"},"design":{"artifacts":["design.md","spec.md","plan.md","progress.md"],"requirement_style":"spec.md 的驗收條件用 EARS 句型（例：「當 <觸發> 時，系統應 <行為>」），逐條對 Story ID，數值與錯誤碼照原文；另有影響系統表、疑慮節、整合修訂與例外節。","guidance":"design.md 有新介面、跨服務、要取捨時才寫；架構取捨寫 ADR（至少 2 個真實選項）。plan.md 寫任務、檔案、測試對應表；progress.md 是從 plan 拆出的清單。"},"build":{"test_first":true,"unit_tests":"單元測試由實作者以 TDD（紅燈 → 綠燈 → 重構）撰寫。","guidance":"驗收測試先寫、確認以預期的理由失敗並合進整合分支，才開始實作；實作者不得修改驗收測試。"},"test":{"verification":"在目前 HEAD 逐條驗證 spec.md 的驗收條件（pass／fail／not_verifiable），fail 用缺陷四欄寫，並對 diff 做反作弊檢查。","guidance":"先跑機械檢查（verify 指令），再核對證據，最後對抗性抽查。"},"deliver":{"review_axes":[],"guidance":"四軸審查（standards、spec、bugs、history），只留信心 ≥0.8 且未被 skeptic 推翻的發現。"},"merge":{"guidance":"需求清單逐條對照驗證證據，全部一致且 merge_gate.py 判 merge 才合併。本 repo（s96cax98leo/meeting-harness）的做法：(1) 需求由 guard.config.json 的 requirements（command adapter tools/merge_gate_project/reqs_from_spec.py）從 origin/main 的 specs/<epic>/spec.md 取，epic 依 commit 的 Spec-Epic trailer 決定，不縮小條目；(2) 先 `gh pr checks <n> --repo s96cax98leo/meeting-harness --required --json name,state`，agent-merge-gate/decision 以外的 required check 都完成才往下，沒完成就 `gh pr checks <n> --repo s96cax98leo/meeting-harness --required --watch` 等；(3) gate 輸入留言先寫到 mktemp -d 的檔案，跑 `python3 tools/merge_gate_project/scan_names.py <檔>`，回 0 才 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr comment <n> --repo s96cax98leo/meeting-harness --body-file <檔>`；回 1 或 2 不貼、判 hold、只回報「留言含疑似名稱（或清單讀不到）」，不印命中內容；(4) 本機 `merge_gate.py check` 的 --checks 用上一步的 JSON 並去掉 agent-merge-gate/decision 本身；--tests-before／--tests-after＝在 base／head 上 `python3 -m unittest discover -s tests/record -t .` 與 `python3 -m unittest discover -s tests/governance -t .` 的 Ran N tests 相加（不含 tests/governance_once 與 Swift 測試）；(5) exit 0 時先等 agent-merge-gate/decision 對目前 head 轉 SUCCESS（`gh pr checks <n> --repo s96cax98leo/meeting-harness --watch`），再 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr merge <n> --repo s96cax98leo/meeting-harness --merge --match-head-commit <sha>`，合併後以 `gh pr view <n> --repo s96cax98leo/meeting-harness --json state,mergedAt,mergeCommit` 讀回；gate check 沒轉綠就不合併、判 hold；(6) exit 1／3 照模版退回（request-changes、轉 draft），gh 指令一律帶 GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger；(7) CI 綠不等於 verify 綠：verify（bash bin/_lint.sh && bash bin/meeting.sh doctor）的證據仍來自本機 verifier；token 的 mint／revoke 只由主 session 做，agent 不讀 ~/.config/meeting-harness/gh/。"}},"parallelism":{"split_threshold":8,"max_sub_plans":4,"shard_verification":true},"requirements":{"source":"json","path":"","command":"","id_pattern":"","notes":"預設不指定需求檔：sdlc-merge 用 args.requirements 或 merge_gate --requirements 帶入；guard.config.json 的 requirements 有設 path／command 時以它為準。"},"conventions":{"code_style":{"description":"照目標 repo 既有的 linter／formatter 設定（CLAUDE.md、設定檔）；新增程式碼不得新增 lint 錯誤。","tool":null,"command":null},"commit":{"format":"Conventional Commits：<type>(<scope>): <摘要>，scope 放 Story ID（文件類放 epic）；epic 的 commit 結尾（署名行之前）加 `Spec-Epic: <epic>` trailer（沒有自己 spec 的 bugfix 指向它修的 epic）；結尾署名行。","examples":{"docs":"docs(<epic>): intent 草稿","test":"test(<Story>): 驗收測試","feat":"feat(<Story>): 實作","fix":"fix(<Story>): 修正驗收失敗"},"check_regex":null},"branch":{"prefix":"feature/","naming":"epic 分支 <prefix><epic>；子任務分支 <prefix><epic>--<子任務 id>；解衝突用 merge/<短名>-into-<整合分支>-<YYYYMMDD>。"},"pr_size":{"max_lines":300,"max_files":15,"scope":"只算修改既有檔（git diff --numstat --diff-filter=M）；超過時建議拆成依序可合的小 PR。"},"doc_format":{"format":"Markdown","notes":"specs/<epic>/ 下的文件照 specs/_templates/ 的範本；沒有範本時用本 profile 各段的說明。"}}} /*@end*/
const MP = METHODOLOGY || {}
const STAGE = ((MP.stages || {}).test) || {}
const CONV = MP.conventions || {}
const PAR = MP.parallelism || {}
const METH_NOTE = METHODOLOGY
  ? `開發規範 profile：${MP.name}（.claude/teams/methodology.json；各段做法與慣例以它為準）。文件格式：${(CONV.doc_format || {}).format || '依目標 repo'}。`
  : '開發規範 profile：未設定（沒有 .claude/teams/methodology.json），做法與慣例依目標 repo 既有規範。'
const commitFor = (kind, epic) => {
  const c = CONV.commit || {}
  const ex = ((c.examples || {})[kind] || '').replace(/<epic>/g, epic)
  return c.format ? `commit 訊息照 profile 的格式：${c.format}${ex ? `（範例：${ex}）` : ''}` : 'commit 訊息照目標 repo 的慣例'
}

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}（分支 feature/${A.epic}，比對基準 ${A.base || 'origin/main'}）\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。\n${METH_NOTE}` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')
const MAX_FIX = 2

// 分片驗證：有 2 個以上子計劃時，每個子計劃一個分片，另加一個整合分片（總覽 spec 的跨子計劃驗收條件＋整條 diff 的反作弊）
const SUBS = (A.sub_plans || []).filter((s) => s && s.id)
const SHARDS = SUBS.length >= 2 && PAR.shard_verification !== false
  ? [
      ...SUBS.map((s) => ({ id: s.id, spec: `${SPEC}/sub/${s.id}/spec.md`, owns: s.owns || [], report: `${SPEC}/verifier-${s.id}.md` })),
      { id: 'integration', spec: `${SPEC}/spec.md`, owns: null, report: `${SPEC}/verifier-integration.md` },
    ]
  : null

const HOW = `驗證方式照 profile：${STAGE.verification || '逐條驗證驗收條件（pass／fail／not_verifiable）'}${STAGE.guidance ? `\nprofile 的 test 指引：${STAGE.guidance}` : ''}`
const verifyAll = (round) => agent(
  `${CTX}\n\n## 派工單（驗證，第 ${round} 輪）\n在 ${EPIC_DIR} 的目前 HEAD 驗證 ${SPEC}/spec.md 的驗收條件。${HOW}\n不論 profile 怎麼寫，都要對 diff 做反作弊檢查，照範本寫 ${SPEC}/verifier.md（repo 有 verifier 檢查腳本就跑）。payload 用 criteria。`,
  { label: `verify#${round}`, phase: 'Verify', agentType: NS + 'dev-verifier', schema: CRITERIA },
)
const verifyShard = (sh, round) => agent(
  `${CTX}\n\n## 派工單（分片驗證：${sh.id}，第 ${round} 輪）\n其他分片由別的 dev-verifier 同時驗證，你只負責這一片。\n` +
  `在 ${EPIC_DIR} 的目前 HEAD 驗證 ${sh.spec} 的驗收條件（條目 id 照原文，不要改名）。${HOW}\n` +
  (sh.owns
    ? `反作弊檢查只看這個子計劃範圍內的 diff（git diff ${A.base || 'origin/main'}...HEAD -- ${sh.owns.join(' ')}）。\n`
    : `這是整合分片：驗證跨子計劃的整合驗收條件，反作弊檢查看整條 diff（git diff ${A.base || 'origin/main'}...HEAD）。\n`) +
  `報告寫到 ${sh.report}（只寫這個檔）。payload 用 criteria，commit 填驗證當下的 HEAD。`,
  { label: `verify:${sh.id}#${round}`, phase: 'Verify', agentType: NS + 'dev-verifier', schema: CRITERIA },
)

// 分片結果的確定性彙整：條目不能遺失、結果不能被改、各分片要驗同一個 HEAD
function combine(shardRes) {
  const crit = []
  const cheats = []
  shardRes.forEach((r, i) => {
    ;(r.payload.criteria || []).forEach((c) => crit.push({ ...c, shard: SHARDS[i].id }))
    ;(r.payload.anti_cheat || []).forEach((x) => cheats.push(`[${SHARDS[i].id}] ${x}`))
  })
  return { crit, cheats, commits: [...new Set(shardRes.map((r) => r.payload.commit))] }
}
function consolidationProblems(merged, c) {
  const errs = []
  if (c.commits.length > 1) errs.push(`各分片驗的 HEAD 不一致：${c.commits.join('、')}`)
  const got = new Map((merged.payload.criteria || []).map((x) => [x.id, x.result]))
  c.crit.forEach((x) => {
    if (!got.has(x.id)) errs.push(`彙整後少了條目 ${x.id}`)
    else if (got.get(x.id) !== x.result) errs.push(`條目 ${x.id} 的結果被改了（分片 ${x.result}、彙整 ${got.get(x.id)}）`)
  })
  if ((merged.payload.anti_cheat || []).length < c.cheats.length) errs.push(`反作弊發現少了（分片 ${c.cheats.length} 項、彙整 ${(merged.payload.anti_cheat || []).length} 項）`)
  return errs
}

// 使用者加進這一段的自己的 agent（profile 的 extensions，用 /add-agent 設定）：和內建 agent 平行執行，交 findings；
// blocker／important 的發現會擋住政策核准。守門依 guard.config.json 的 extension_agents 套用對應角色的規則
const EXT = (MP.extensions || []).filter((e) => e.stage === 'test')
const extJob = (e, ctx, phaseName) => () => agent(
  `${ctx}\n\n## 派工單（擴充 agent：${e.name}）\n${e.instructions}\n` +
  `只讀不改：不改程式、測試與 spec，不 push、不對 GitHub 寫入。詳細結果寫到 ${A.run_dir}/ext-${e.name}.md。` +
  `payload 用 findings（lens=${e.name}）：每則附 0–1 信心與嚴重度；會擋住上線或合併的列 blocker／important（會擋住政策核准），其餘列 nit／info。`,
  { label: `ext:${e.name}`, phase: phaseName, agentType: e.agent, schema: FINDINGS },
)

const shardRuns = []
async function verify(round) {
  if (!SHARDS) {
    const v = await verifyAll(round)
    return { combined: v, problem: v ? null : '驗證沒有回傳結果' }
  }
  const res = await parallel(SHARDS.map((sh) => () => verifyShard(sh, round)))
  shardRuns.push({ round, shards: res })
  const lost = SHARDS.filter((sh, i) => !res[i])
  if (lost.length) return { combined: null, problem: `分片 ${lost.map((s) => s.id).join('、')} 沒有回傳驗證結果` }
  const c = combine(res)
  phase('Consolidate')
  const merged = await agent(
    `${CTX}\n\n## 派工單（彙整分片驗證，第 ${round} 輪）\n${SHARDS.length} 個分片已平行驗證完成，報告：${SHARDS.map((s) => s.report).join('、')}。\n` +
    `把它們彙整成 ${SPEC}/verifier.md（照範本；每條註明出自哪個分片）。不重新判定結果：條目與 result 照分片原樣，反作弊發現全部列入；只有各分片的 HEAD 不一致時以 needs_decision 回報。payload 用 criteria（commit 填各分片共同的 HEAD）。\n\n` +
    `## 分片結果\n${JSON.stringify({ commits: c.commits, criteria: c.crit, anti_cheat: c.cheats })}`,
    { label: `consolidate#${round}`, phase: 'Consolidate', agentType: NS + 'dev-verifier', schema: CRITERIA },
  )
  if (!merged) return { combined: null, problem: '彙整分片驗證沒有回傳結果' }
  const errs = consolidationProblems(merged, c)
  return { combined: merged, problem: errs.length ? `彙整結果和分片不一致：${errs.join('；')}` : null, crit: c.crit }
}

phase('Verify')
const jobs = [() => verify(1)]
if (A.has_ui) jobs.push(() => agent(`${CTX}\n\n## 派工單\n設計審查 feature/${A.epic} 的畫面改動，寫 ${SPEC}/design-review.md 與 ${SPEC}/evidence/。payload 用 findings（lens=design）。`, { label: 'design-review', phase: 'Verify', agentType: NS + 'dev-design-reviewer', schema: FINDINGS }))
if (A.has_security) jobs.push(() => agent(`${CTX}\n\n## 派工單\n安全審查 feature/${A.epic}（git diff ${A.base || 'origin/main'}...HEAD），寫 ${SPEC}/security-review.md。payload 用 findings（lens=security）。`, { label: 'security-review', phase: 'Verify', agentType: NS + 'dev-security-reviewer', schema: FINDINGS }))
EXT.forEach((e) => jobs.push(extJob(e, `${CTX}\n驗證對象：${EPIC_DIR} 的目前 HEAD（git diff ${A.base || 'origin/main'}...HEAD），spec 在 ${SPEC}/。`, 'Verify')))
const [first, ...reviews] = await parallel(jobs)

const fixes = []
const finish = (current, extra) => {
  const summary = current ? (current.payload.criteria || []).reduce((m, c) => (m[c.result] = (m[c.result] || 0) + 1, m), {}) : null
  return { stage: 'test', gate: '驗證結果確認（fail 或 not_verifiable 由人決定）', verifier: current, verifier_shards: shardRuns, reviews: reviews.filter(Boolean), fixes, summary, ...extra }
}
if (!first) return finish(null, { halted: true, halt_reason: '驗證沒有回傳結果，停下交人' })
if (first.problem) return finish(first.combined, { halted: true, halt_reason: first.problem })

const fixBrief = (failed, cheats) => `測試失敗就改程式、不改測試，不加 skip／retry、不放寬斷言。\n失敗：${JSON.stringify(failed)}\n反作弊發現：${JSON.stringify(cheats)}`
async function fixSerial(round, failed, cheats) {
  return agent(
    `${CTX}\n\n## 派工單（修正第 ${round} 輪）\n在 ${EPIC_DIR}（feature/${A.epic}）修正下列失敗；${fixBrief(failed, cheats)}\n修完 commit（${commitFor('fix', A.epic)}）。\npayload 用 build-result（task_id=fix${round}、branch=feature/${A.epic}、worktree=${EPIC_DIR}）。`,
    { label: `fix#${round}`, phase: 'Fix', agentType: NS + 'dev-implementer', schema: BUILD },
  )
}
// 多個子計劃都有失敗：各自在 worktree 平行修（只改該子計劃範圍），再由 integrator 合併；整合分片的失敗跨子計劃，合併後再單獨修
async function fixParallel(round, groups) {
  const res = await parallel(groups.map((g) => () => {
    const br = `feature/${A.epic}--fix${round}-${g.id}`
    const wt = `${A.repo}/.worktrees/${A.epic}--fix${round}-${g.id}`
    return agent(
      `${CTX}\n\n## 派工單（修正第 ${round} 輪，子計劃 ${g.id}）\n其他子計劃的失敗由別的 agent 同時修，你只負責這一個。\n` +
      `在自己的 worktree 修：git -C "${A.repo}" worktree add .worktrees/${A.epic}--fix${round}-${g.id} -b ${br} feature/${A.epic}（已存在就沿用）。worktree：${wt}。\n` +
      `只能改這些範圍：${g.owns.join('、')}。修正需要改範圍外的檔案時不要改，以 needs_decision 回報。\n${fixBrief(g.failed, g.cheats)}\n` +
      `修完 commit（${commitFor('fix', A.epic)}）。payload 用 build-result（task_id=fix${round}-${g.id}、branch=${br}、worktree=${wt}）。`,
      { label: `fix:${g.id}#${round}`, phase: 'Fix', agentType: NS + 'dev-implementer', schema: BUILD },
    )
  }))
  fixes.push(...res)
  const ok = res.filter((r) => r && r.status === 'done')
  if (ok.length < groups.length) return null
  phase('Integrate')
  const ir = await agent(
    `${CTX}\n\n## 派工單（整合修正第 ${round} 輪）\n依序把這些分支 git merge --no-ff 進 feature/${A.epic}（在 ${EPIC_DIR} 操作）：\n` +
    ok.map((r) => `- ${r.payload.branch}（${r.payload.task_id}）`).join('\n') +
    `\n有衝突照目標 repo 的分支與合併規範用中轉分支解並分類。合完跑 rules.md 專案規則的 verify 指令（基準 ${A.base || 'origin/main'}；沒有就用該 repo 的對等指令），全綠後移除這些修正的 worktree 與分支。\npayload 用 build-result（task_id=fix${round}、branch=feature/${A.epic}）。`,
    { label: `integrate:fix#${round}`, phase: 'Integrate', agentType: NS + 'dev-integrator', schema: BUILD },
  )
  fixes.push(ir)
  return ir
}

let state = first
for (let round = 1; round <= MAX_FIX && state.combined; round++) {
  const current = state.combined
  const failed = (current.payload.criteria || []).filter((c) => c.result === 'fail')
  const cheats = current.payload.anti_cheat || []
  if (!failed.length && !cheats.length) break
  phase('Fix')
  log(`第 ${round} 輪修正：fail ${failed.length} 條、反作弊 ${cheats.length} 項`)
  let fix
  // 依分片分組：只有子計劃分片（不含整合分片）的失敗、且分散在 2 個以上子計劃時才平行修
  const shardOf = new Map((state.crit || []).map((c) => [c.id, c.shard]))
  const groups = SHARDS ? SHARDS.filter((sh) => sh.owns).map((sh) => ({
    id: sh.id, owns: sh.owns,
    failed: failed.filter((c) => shardOf.get(c.id) === sh.id),
    cheats: cheats.filter((x) => x.startsWith(`[${sh.id}]`)),
  })).filter((g) => g.failed.length || g.cheats.length) : []
  const rest = SHARDS ? { failed: failed.filter((c) => !groups.some((g) => g.failed.includes(c))), cheats: cheats.filter((x) => !groups.some((g) => g.cheats.includes(x))) } : null
  if (groups.length >= 2) {
    log(`平行修正 ${groups.length} 個子計劃：${groups.map((g) => g.id).join('、')}`)
    fix = await fixParallel(round, groups)
    if (fix && fix.status === 'done' && (rest.failed.length || rest.cheats.length)) {
      fix = await fixSerial(round, rest.failed, rest.cheats)
      fixes.push(fix)
    }
  } else {
    fix = await fixSerial(round, failed, cheats)
    fixes.push(fix)
  }
  if (!fix || fix.status !== 'done') break
  phase('Verify')
  state = await verify(round + 1)
  if (state.problem) return finish(state.combined, { halted: true, halt_reason: state.problem })
}

return finish(state.combined, { halted: false })

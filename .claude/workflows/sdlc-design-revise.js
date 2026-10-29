export const meta = {
  name: 'sdlc-design-revise',
  description: 'AI-native SDLC 第 2 段的修正輪：spec-author 依使用者在閘門 2 的決定與 skeptic 的問題修正 design／spec／plan／子任務，兩個 skeptic 平行複查，再回到 spec＋plan 核准閘門',
  whenToUse: 'sdlc-design 回來後，閘門 2 有要修的問題；args 加 decisions（使用者決定，字串陣列）與 issues（skeptic 推翻的項目：target_id＋reason），有子計劃時加 sub_plans',
  phases: [
    { title: 'Revise', detail: 'dev-spec-author 逐條修正並回報處理方式' },
    { title: 'Recheck', detail: '兩個 tpm-skeptic 平行複查（是否都修好、有沒有新落差）' },
  ],
}

// plugin 的 agent 帶命名空間（init.py 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const SUBTASKS = /*@schema:subtasks*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["epic","subtasks"],"properties":{"epic":{"type":"string"},"subtasks":{"type":"array","minItems":1,"items":{"type":"object","required":["id","title","kind","owns","depends_on","acceptance"],"properties":{"id":{"type":"string"},"title":{"type":"string"},"kind":{"type":"string","enum":["code","test","doc","research","check","decision"]},"owns":{"type":"array","items":{"type":"string"}},"depends_on":{"type":"array","items":{"type":"string"}},"acceptance":{"type":"array","items":{"type":"string"}},"story_ids":{"type":"array","items":{"type":"string"}},"sub_plan":{"type":"string"}}}}}}}} /*@end*/
const VERDICTS = /*@schema:verdicts*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["verdicts"],"properties":{"verdicts":{"type":"array","items":{"type":"object","required":["target_id","refuted","reason"],"properties":{"target_id":{"type":"string"},"refuted":{"type":"boolean"},"reason":{"type":"string"},"counter_evidence":{"type":"string"}}}}}}}} /*@end*/

// 開發規範 profile（methodology）：init.py 依使用者選的 profile 與回答的慣例寫 .claude/teams/methodology.json，
// build.py 內嵌到這裡；不要手改，改 profile 後重跑 build.py。null＝沒有 profile，改用中性指引（依目標 repo 既有慣例）。
const METHODOLOGY = /*@methodology*/ {"name":"default","description":"預設 profile（模版原本的做法）：spec 驅動，驗收條件用 EARS 句型，測試先行（先寫會失敗的驗收測試再實作），Conventional Commits 加 Story scope，PR 修改既有檔上限 300 行或 15 檔。","stages":{"plan":{"artifacts":["intent.md"],"template":"問題、期望結果、受影響的使用者與系統、限制、待解問題","guidance":"intent 只寫問題空間，不寫解法；每個主張附出處；最多 5 個待釐清問題，blocking 的附 2–3 個選項與代價。"},"design":{"artifacts":["design.md","spec.md","plan.md","progress.md"],"requirement_style":"spec.md 的驗收條件用 EARS 句型（例：「當 <觸發> 時，系統應 <行為>」），逐條對 Story ID，數值與錯誤碼照原文；另有影響系統表、疑慮節、整合修訂與例外節。","guidance":"design.md 有新介面、跨服務、要取捨時才寫；架構取捨寫 ADR（至少 2 個真實選項）。plan.md 寫任務、檔案、測試對應表；progress.md 是從 plan 拆出的清單。"},"build":{"test_first":true,"unit_tests":"單元測試由實作者以 TDD（紅燈 → 綠燈 → 重構）撰寫。","guidance":"驗收測試先寫、確認以預期的理由失敗並合進整合分支，才開始實作；實作者不得修改驗收測試。"},"test":{"verification":"在目前 HEAD 逐條驗證 spec.md 的驗收條件（pass／fail／not_verifiable），fail 用缺陷四欄寫，並對 diff 做反作弊檢查。","guidance":"先跑機械檢查（verify 指令），再核對證據，最後對抗性抽查。"},"deliver":{"review_axes":[],"guidance":"四軸審查（standards、spec、bugs、history），只留信心 ≥0.8 且未被 skeptic 推翻的發現。"},"merge":{"guidance":"需求清單逐條對照驗證證據，全部一致且 merge_gate.py 判 merge 才合併。"}},"parallelism":{"split_threshold":8,"max_sub_plans":4,"shard_verification":true},"requirements":{"source":"json","path":"","command":"","id_pattern":"","notes":"預設不指定需求檔：sdlc-merge 用 args.requirements 或 merge_gate --requirements 帶入；guard.config.json 的 requirements 有設 path／command 時以它為準。"},"conventions":{"code_style":{"description":"照目標 repo 既有的 linter／formatter 設定（CLAUDE.md、設定檔）；新增程式碼不得新增 lint 錯誤。","tool":null,"command":null},"commit":{"format":"Conventional Commits：<type>(<scope>): <摘要>，scope 放 Story ID（文件類放 epic）；結尾署名行。","examples":{"docs":"docs(<epic>): intent 草稿","test":"test(<Story>): 驗收測試","feat":"feat(<Story>): 實作","fix":"fix(<Story>): 修正驗收失敗"},"check_regex":null},"branch":{"prefix":"feature/","naming":"epic 分支 <prefix><epic>；子任務分支 <prefix><epic>--<子任務 id>；解衝突用 merge/<短名>-into-<整合分支>-<YYYYMMDD>。"},"pr_size":{"max_lines":300,"max_files":15,"scope":"只算修改既有檔（git diff --numstat --diff-filter=M）；超過時建議拆成依序可合的小 PR。"},"doc_format":{"format":"Markdown","notes":"specs/<epic>/ 下的文件照 specs/_templates/ 的範本；沒有範本時用本 profile 各段的說明。"}}} /*@end*/
const MP = METHODOLOGY || {}
const STAGE = ((MP.stages || {}).design) || {}
const CONV = MP.conventions || {}
const METH_NOTE = METHODOLOGY
  ? `開發規範 profile：${MP.name}（.claude/teams/methodology.json；各段做法與慣例以它為準）。文件格式：${(CONV.doc_format || {}).format || '依目標 repo'}。`
  : '開發規範 profile：未設定（沒有 .claude/teams/methodology.json），做法與慣例依目標 repo 既有規範。'
const commitFor = (kind, epic) => {
  const c = CONV.commit || {}
  const ex = ((c.examples || {})[kind] || '').replace(/<epic>/g, epic)
  return c.format ? `commit 訊息照 profile 的格式：${c.format}${ex ? `（範例：${ex}）` : ''}` : 'commit 訊息照目標 repo 的慣例'
}
const PR_SIZE = CONV.pr_size || {}

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir', 'decisions', 'issues']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SUBS = (A.sub_plans || []).filter((x) => x && x.id)
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。intent.md 已核准，不得修改。\n${METH_NOTE}` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')

phase('Revise')
const revised = await agent(
  `${CTX}\n\n## 派工單（修正輪）\n依下面的使用者決定與 skeptic 問題，修正 ${SPEC}/ 的 design、spec、plan、progress 與 ADR 草稿，並重新拆子任務（payload subtasks，owns 不重疊、depends_on 與 plan 分層一致）。\n` +
  (SUBS.length ? `這個 epic 拆成了子計劃（${SUBS.map((x) => x.id).join('、')}）：子計劃文件在 ${SPEC}/sub/<id>/，大綱在 ${SPEC}/outline.md；修正時保留子任務的 sub_plan 欄位與「<子計劃 id>-」開頭的 id，owns 不得超出該子計劃的範圍。\n` : '') +
  `每一條問題都要處理：修正，或說明為什麼不改（附依據）。處理對照表寫到 ${A.run_dir}/design-revise-對照.md（問題 → 處理 → 改了哪裡）。\n` +
  `需求／驗收條件的寫法照 profile：${STAGE.requirement_style || '目標 repo 既有的 spec 寫法'}。\n` +
  (PR_SIZE.max_files || PR_SIZE.max_lines ? `預計改動超過 profile 的 PR 大小上限（${[PR_SIZE.max_lines ? `${PR_SIZE.max_lines} 行` : '', PR_SIZE.max_files ? `${PR_SIZE.max_files} 個檔` : ''].filter(Boolean).join('或')}；量法：${PR_SIZE.scope || '依 profile'}）時，在 plan 寫拆 PR 的規劃（例如分 2 包）。\n` : '') +
  `commit（${commitFor('docs', A.epic)}，內容是依閘門 2 修正 design、spec、plan；結尾 Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>）。不 push。\n\n` +
  `## 使用者在閘門 2 的決定\n${A.decisions.map((d, i) => `${i + 1}. ${d}`).join('\n')}\n\n## skeptic 的問題（${A.issues.length} 條）\n${A.issues.map((x, i) => `${i + 1}. [${x.target_id}] ${x.reason}`).join('\n')}`,
  { label: 'revise', phase: 'Revise', agentType: NS + 'dev-spec-author', schema: SUBTASKS },
)

phase('Recheck')
const LENSES = [
  { key: 'resolved', ask: `逐條確認上面 ${A.issues.length} 條問題是否真的修好（打開檔案看，不採信對照表的自述）；target_id 用原問題編號。` },
  { key: 'regression', ask: '修正有沒有造成新的落差：intent ↔ spec ↔ plan ↔ 子任務 owns／depends_on ↔ 測試對應表 ↔ 契約；使用者決定有沒有被正確落實。' },
]
const recheck = revised ? await parallel(LENSES.map((l) => () => agent(
  `${CTX}\n\n## 派工單（複查：${l.key}）\n讀 ${SPEC}/ 與 ${A.run_dir}/design-revise-對照.md。子任務：${JSON.stringify(revised.payload)}\n${l.ask}\nrefuted=true 表示「這裡還有問題」。\n\n原問題：\n${A.issues.map((x, i) => `${i + 1}. [${x.target_id}] ${x.reason}`).join('\n')}\n使用者決定：\n${A.decisions.join('\n')}`,
  { label: `recheck:${l.key}`, phase: 'Recheck', agentType: NS + 'tpm-skeptic', schema: VERDICTS },
))) : []

return { stage: 'design', round: 'revise', gate: 'spec＋plan 核准', epic_dir: EPIC_DIR, sub_plans: SUBS, design: revised, analysis: recheck.filter(Boolean) }

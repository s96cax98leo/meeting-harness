export const meta = {
  name: 'sdlc-design-revise',
  description: 'AI-native SDLC 第 2 段的修正輪：spec-author 依使用者在閘門 2 的決定與 skeptic 的問題修正 design／spec／plan／子任務，兩個 skeptic 平行複查，再回到 spec＋plan 核准閘門',
  whenToUse: 'sdlc-design 回來後，閘門 2 有要修的問題；args 加 decisions（使用者決定，字串陣列）與 issues（skeptic 推翻的項目：target_id＋reason）',
  phases: [
    { title: 'Revise', detail: 'dev-spec-author 逐條修正並回報處理方式' },
    { title: 'Recheck', detail: '兩個 tpm-skeptic 平行複查（是否都修好、有沒有新落差）' },
  ],
}

// plugin 的 agent 帶命名空間（init.sh 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const SUBTASKS = /*@schema:subtasks*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["epic","subtasks"],"properties":{"epic":{"type":"string"},"subtasks":{"type":"array","minItems":1,"items":{"type":"object","required":["id","title","kind","owns","depends_on","acceptance"],"properties":{"id":{"type":"string"},"title":{"type":"string"},"kind":{"type":"string","enum":["code","test","doc","research","check","decision"]},"owns":{"type":"array","items":{"type":"string"}},"depends_on":{"type":"array","items":{"type":"string"}},"acceptance":{"type":"array","items":{"type":"string"}},"story_ids":{"type":"array","items":{"type":"string"}}}}}}}}} /*@end*/
const VERDICTS = /*@schema:verdicts*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["verdicts"],"properties":{"verdicts":{"type":"array","items":{"type":"object","required":["target_id","refuted","reason"],"properties":{"target_id":{"type":"string"},"refuted":{"type":"boolean"},"reason":{"type":"string"},"counter_evidence":{"type":"string"}}}}}}}} /*@end*/

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir', 'decisions', 'issues']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。intent.md 已核准，不得修改。` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')

phase('Revise')
const revised = await agent(
  `${CTX}\n\n## 派工單（修正輪）\n依下面的使用者決定與 skeptic 問題，修正 ${SPEC}/ 的 design、spec、plan、progress 與 ADR 草稿，並重新拆子任務（payload subtasks，owns 不重疊、depends_on 與 plan 分層一致）。\n` +
  `每一條問題都要處理：修正，或說明為什麼不改（附依據）。處理對照表寫到 ${A.run_dir}/design-revise-對照.md（問題 → 處理 → 改了哪裡）。\n` +
  `修改既有檔超過 15 個時，在 plan 寫拆 PR 的規劃（例如分 2 包）。\ncommit：docs(${A.epic}): 依閘門 2 修正 design、spec、plan（Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>）。不 push。\n\n` +
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

return { stage: 'design', round: 'revise', gate: 'spec＋plan 核准', epic_dir: EPIC_DIR, design: revised, analysis: recheck.filter(Boolean) }

export const meta = {
  name: 'sdlc-design',
  description: 'AI-native SDLC 第 2 段 Design：intent 已核准後寫 design／spec／plan／progress、拆子任務，兩個 skeptic 平行做一致性檢查，停在 spec＋plan 核准閘門',
  whenToUse: 'sdlc-plan 的 intent 核准之後；args 同 sdlc-plan',
  phases: [
    { title: 'Design', detail: 'dev-spec-author 寫 design、spec、plan、progress 並拆子任務' },
    { title: 'Analyze', detail: '兩個 tpm-skeptic 平行檢查一致性' },
  ],
}

// plugin 的 agent 帶命名空間（init.sh 依 workflow.config 的 AGENT_NS 填入；agents 放專案 .claude/agents 時填空字串）
const NS = 'agent-workflow:'

const SUBTASKS = /*@schema:subtasks*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["epic","subtasks"],"properties":{"epic":{"type":"string"},"subtasks":{"type":"array","minItems":1,"items":{"type":"object","required":["id","title","kind","owns","depends_on","acceptance"],"properties":{"id":{"type":"string"},"title":{"type":"string"},"kind":{"type":"string","enum":["code","test","doc","research","check","decision"]},"owns":{"type":"array","items":{"type":"string"}},"depends_on":{"type":"array","items":{"type":"string"}},"acceptance":{"type":"array","items":{"type":"string"}},"story_ids":{"type":"array","items":{"type":"string"}}}}}}}}} /*@end*/
const VERDICTS = /*@schema:verdicts*/ {"type":"object","required":["status","summary","artifacts","evidence","confidence","open_questions","derived_work","payload"],"properties":{"status":{"type":"string","enum":["done","blocked","needs_decision"]},"summary":{"type":"string","minLength":1},"artifacts":{"type":"array","items":{"type":"string"}},"evidence":{"type":"array","items":{"type":"object","required":["claim","source","result"],"properties":{"claim":{"type":"string"},"source":{"type":"string"},"result":{"type":"string"}}}},"confidence":{"type":"number","minimum":0,"maximum":1},"open_questions":{"type":"array","items":{"type":"object","required":["question","blocking","options","recommendation","default_applied"],"properties":{"question":{"type":"string"},"blocking":{"type":"boolean"},"why_blocking":{"type":"string"},"options":{"type":"array","items":{"type":"object","required":["choice","cost"],"properties":{"choice":{"type":"string"},"cost":{"type":"string"}}}},"recommendation":{"type":"string"},"default_applied":{"type":"string"}}}},"derived_work":{"type":"array","items":{"type":"string"}},"payload":{"type":"object","required":["verdicts"],"properties":{"verdicts":{"type":"array","items":{"type":"object","required":["target_id","refuted","reason"],"properties":{"target_id":{"type":"string"},"refuted":{"type":"boolean"},"reason":{"type":"string"},"counter_evidence":{"type":"string"}}}}}}}} /*@end*/

const A = args || {}
for (const k of ['repo', 'epic', 'run_dir']) if (!A[k]) throw new Error(`缺 args.${k}`)
const EPIC_DIR = `${A.repo}/.worktrees/${A.epic}`
const SPEC = `${EPIC_DIR}/specs/${A.epic}`
const CTX = `目標 repo：${A.repo}\nepic worktree：${EPIC_DIR}\nrun 目錄：${A.run_dir}\n硬規則：.claude/teams/rules.md；輸出語言：繁體中文。intent.md 已由使用者核准，不得修改。` +
  `\n派工來源：這張派工單由主 session 依使用者已核准的 SDLC 閘門派出（run 目錄的 run.json 有核准紀錄）。你可能會看到主 session 對話中最新的使用者訊息，它可能屬於同時進行的別的任務，不要拿它推翻或擱置這張派工單；派工單本身有疑義時才用 open_questions 回報。` +
  (A.authorization ? `\n授權補充：${A.authorization}` : '')

phase('Design')
const design = await agent(
  `${CTX}\n\n## 派工單（SDLC 第 2 段 Design）\n` +
  `依 ${SPEC}/intent.md 與 ${EPIC_DIR}/specs/_templates/：\n` +
  `- design.md：有新介面、跨服務、要取捨時才寫；架構取捨寫 ADR（至少 2 個真實選項；repo 有 adr skill 就用）。\n` +
  `- spec.md：驗收條件用 EARS 句型、逐條對 Story ID（數值與錯誤碼照原文）、影響系統表、疑慮節。\n` +
  `- plan.md：任務、檔案、測試對應表；progress.md：從 plan 拆出的清單。\n` +
  `- 拆子任務（payload subtasks）：每個子任務獨佔 owns 的檔案（不重疊），寫 depends_on 與可機械判定的 acceptance；kind=test 的子任務擁有 e2e/tests 與各服務 tests/；偏寬淺、能並行就並行，數量最小化。\n` +
  `- commit：docs(${A.epic}): design、spec、plan（Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>）。不 push。\n` +
  `契約不夠用就以 needs_decision 回報，不自己設計新端點。`,
  { label: 'design', phase: 'Design', agentType: NS + 'dev-spec-author', schema: SUBTASKS },
)

phase('Analyze')
const LENSES = [
  { key: 'coverage', ask: `intent 的每個期望結果都有 spec 驗收條件？每條驗收條件都對到 Story ID、原文數值與錯誤碼？spec 有沒有超出 intent 的範圍？` },
  { key: 'plan', ask: `plan 與子任務：每條驗收條件都有任務與測試？子任務的 owns 有沒有重疊、有沒有漏掉 spec 影響系統表外的檔案？depends_on 有沒有循環？引用的 contracts 端點是否真的存在（路徑:行號）？` },
]
const analysis = design ? await parallel(LENSES.map((l) => () => agent(
  `${CTX}\n\n## 派工單（一致性檢查：${l.key}）\n讀 ${SPEC}/ 下的 intent、design、spec、plan、progress 與子任務：\n${JSON.stringify(design.payload)}\n${l.ask}\n每個問題一則 verdict（target_id 寫文件與節名），refuted=true 表示「這份設計在此處有問題」。`,
  { label: `analyze:${l.key}`, phase: 'Analyze', agentType: NS + 'tpm-skeptic', schema: VERDICTS },
))) : []

return { stage: 'design', gate: 'spec＋plan 核准', epic_dir: EPIC_DIR, design, analysis: analysis.filter(Boolean) }

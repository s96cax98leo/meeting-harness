export const meta = {
  name: 'meeting-pipeline',
  description: '逐場會議流水線：轉錄 + 投影片OCR/視覺 → 總結 → 驗證(可恢復) → 發佈 wiki + docx',
  whenToUse: '有一或多個會議場次（錄音+照片）要一次處理成 wiki 頁與 Word。args 傳 {harnessRoot, vaultPath, sessions:[{dir,name,audio}]}。',
  phases: [
    { title: 'Transcribe' },
    { title: 'Slides' },
    { title: 'Summarize' },
    { title: 'Verify' },
    { title: 'Publish' },
  ],
}

// ---- 輸入 ----
const HARNESS = args?.harnessRoot || '.'
const VAULT = args?.vaultPath || `${HARNESS}/vault`
const SESSIONS = args?.sessions || []
if (!SESSIONS.length) { log('沒有場次可處理（args.sessions 為空）'); return { sessions: [] } }

// ---- 結構化輸出 schema ----
const S = (props, required) => ({ type: 'object', properties: props, required, additionalProperties: true })
const TRANSCRIBE_SCHEMA = S({ status:{type:'string'}, transcriptPath:{type:'string'}, termCandidates:{type:'array',items:{type:'string'}}, notes:{type:'string'} }, ['status','transcriptPath'])
const SLIDES_SCHEMA     = S({ status:{type:'string'}, slidesPath:{type:'string'}, slideCount:{type:'number'}, needsVision:{type:'array',items:{type:'string'}}, notes:{type:'string'} }, ['status','slidesPath'])
const SUMMARY_SCHEMA    = S({ status:{type:'string'}, summaryPath:{type:'string'}, termCandidates:{type:'array',items:{type:'string'}}, openQuestions:{type:'array',items:{type:'string'}} }, ['status','summaryPath'])
const VERIFY_SCHEMA     = S({ verdict:{type:'string'}, score:{type:'number'}, issues:{type:'array'}, summaryOfFindings:{type:'string'} }, ['verdict'])
const PUBLISH_SCHEMA    = S({ status:{type:'string'}, wikiPage:{type:'string'}, docxPath:{type:'string'}, termsAdded:{type:'array',items:{type:'string'}} }, ['status'])

const guide = (dir, name, audio) => `
場次目錄：${dir}
場次名稱：${name}
錄音檔：${audio}
harness 根：${HARNESS}（bin/ 有 transcribe.sh、ocr-slides.sh、to-docx.sh）
長期記憶術語表：${VAULT}/術語表.md
所有指令用絕對路徑；每步先做冪等檢查（產物已存在且非空就跳過）。回報結構化 JSON。`

async function runSession(sess, i) {
  const { dir, name, audio } = sess
  const ctx = guide(dir, name, audio)

  // (A) 轉錄 —— 與投影片並行
  const transcribeP = agent(
    `${ctx}\n【transcribe】執行 \`bash ${HARNESS}/bin/transcribe.sh "${audio}" "${dir}/錄音/transcript.raw.md" zh\`；` +
    `再讀 transcript.raw.md 與 ${dir}/錄音/轉文字.txt 與術語表，依術語表與上下文校對明顯的專名 ASR 音譯/錯字、補標點分段，寫乾淨的 ${dir}/錄音/transcript.md，並蒐集新術語候選。`,
    { label: `transcribe:${name}`, phase: 'Transcribe', schema: TRANSCRIBE_SCHEMA }
  )

  // (B) 投影片：OCR → 視覺補讀（同一 agent 串起兩步，或分兩段）
  const slidesP = (async () => {
    const ocr = await agent(
      `${ctx}\n【slide-ocr】執行 \`bash ${HARNESS}/bin/ocr-slides.sh "${dir}/照片"\`；讀 ${dir}/照片/.ocr/*.txt，` +
      `判斷哪些是架構圖/流程圖/表格(needsVision)，產 ${dir}/照片/slides.ocr.md，回傳 needsVision 清單。`,
      { label: `slide-ocr:${name}`, phase: 'Slides', schema: SLIDES_SCHEMA }
    )
    if (!ocr) return null
    const nv = (ocr.needsVision || [])
    await agent(
      `${ctx}\n【slide-vision】needsVision=${JSON.stringify(nv)}。對每張 Read ${dir}/照片/.jpg/<IMG>.jpg，` +
      `用視覺描述圖表類型/元件/資料流/關鍵標註，與 OCR 交叉核對不臆造，合併 slides.ocr.md 成最終 ${dir}/照片/slides.md。`,
      { label: `slide-vision:${name}`, phase: 'Slides', schema: SLIDES_SCHEMA }
    )
    return ocr
  })()

  const [transcribe, slides] = await Promise.all([transcribeP, slidesP])

  // 匯流 → 總結
  const summary = await agent(
    `${ctx}\n【summarize】合併 ${dir}/錄音/transcript.md + ${dir}/照片/slides.md + 術語表，` +
    `產結構化繁中總結 ${dir}/summary.md（TL;DR/大綱/重點/技術細節/待辦/Q&A/名詞解釋/存疑，每主張標來源）。`,
    { label: `summarize:${name}`, phase: 'Summarize', schema: SUMMARY_SCHEMA }
  )
  if (!summary) return { name, status: 'error', stage: 'summarize' }

  // 驗證 → 恢復（最多重跑 summarize 1 次）
  let verdict = await agent(
    `${ctx}\n【verify】逐條查核 ${dir}/summary.md 對照 transcript.md/slides.md/術語表：標記幻覺/遺漏/術語不一致/未標來源，給 pass|fail 與逐條修正。`,
    { label: `verify:${name}`, phase: 'Verify', schema: VERIFY_SCHEMA }
  )
  if (verdict && verdict.verdict === 'fail') {
    log(`${name}: verify fail → 依建議重跑 summarize`)
    await agent(
      `${ctx}\n【summarize-fix】依驗證問題修正並重寫 ${dir}/summary.md：${JSON.stringify(verdict.issues||[]).slice(0,1500)}`,
      { label: `summarize-fix:${name}`, phase: 'Summarize', schema: SUMMARY_SCHEMA }
    )
    verdict = await agent(
      `${ctx}\n【verify-2】再次查核 ${dir}/summary.md，回 pass|fail。`,
      { label: `verify2:${name}`, phase: 'Verify', schema: VERIFY_SCHEMA }
    )
  }
  if (!verdict || verdict.verdict !== 'pass') {
    return { name, status: 'blocked', reason: 'verifier 未通過', verdict }
  }

  // 發佈
  const publish = await agent(
    `${ctx}\n【publish】把 ${dir}/summary.md 寫成 ${VAULT}/wiki/${name}.md（frontmatter+wikilinks）；` +
    `併入術語候選到 ${VAULT}/術語表.md、更新 ${VAULT}/會議索引.md；` +
    `執行 \`bash ${HARNESS}/bin/to-docx.sh "${dir}/summary.md" "${dir}/exports/${name}.docx"\`。`,
    { label: `publish:${name}`, phase: 'Publish', schema: PUBLISH_SCHEMA }
  )
  return { name, status: publish?.status || 'error', wikiPage: publish?.wikiPage, docxPath: publish?.docxPath, verdict: verdict.verdict }
}

// 逐場並行（各場獨立 context）；場數多時受並行上限自動排隊
const out = await parallel(SESSIONS.map((s, i) => () => runSession(s, i)))
return { sessions: out.filter(Boolean) }

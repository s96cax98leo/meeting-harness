# tests/governance_once

只在 auto-merge epic 驗收時跑、CI 不跑、啟用後必紅。

- 這裡放的是「只在升級當下成立」的斷言：以 `e72a9cb`（升級前的 main）為基準的合回比對，以及斷言 `auto_merge.enabled` 為 false 的設定檢查（spec §4.1.3、§4.1.4、§4.1.7、§4.1.8 後半、§4.1.9、§4.1.11、§4.5.1；分界見 spec §4 開頭，E2）。
- 執行方式（plan §3 第 6 條）：`python3 -m unittest discover -s tests/governance_once -t .`。
- `ops-enable` 把 `auto_merge.enabled` 改成 true 之後，`test_auto_merge_values` 一定失敗，這是預期的；這個目錄之後只當升級紀錄保留，不再執行，也不算進 gate 的測試數（spec §4.2.6）。
- 不要從 repo 根執行不帶 `-s` 的 `unittest discover`，那會把本目錄一起掃進來（spec §7 第 11 點）。
- 長期有效的測試在 `tests/governance/`（CI 跑）。

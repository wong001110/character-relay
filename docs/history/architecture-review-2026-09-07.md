# Character Relay 整體架構審查

日期：2026-09-07｜模式：Reviewer｜狀態：審查與重構提案，尚未鎖定新架構

審查基線：`wong001110/character-relay`，`main`，`d23e7f22229788068dbb76abf9e403fd0a4bcc7d`。

## 審查結論

**建議進行跨模組重構，但不建議一次性重寫整個產品。**目前最明確的問題不是使用了「過時的 memory 名稱」，而是核心使用者流程穿過多個篩選器、資料投影與執行層後，失去必要資訊或能力；有些元件雖有測試，卻沒有接入正式執行流程。Knowledge Fabric 則把資料取得、索引、背景生命週期及網站瀏覽的風險帶入了角色產品，現有隔離修復仍有結構性缺口。

審查裁決：**Reject: correction required**，針對「現有架構已足以支持持續擴展與可靠上線」的主張。這不是宣告所有既有功能不能用，也不是否定 Thread／Episode／Belief 的分工。

建議以三個產品結果重新約束設計：

1. 角色能連貫地理解、記住、修正和續接對話，而不是只在元件測試裡存在 memory。
2. 角色能發現已授權能力、表達正在處理、執行並回報真實結果；「找不到」有可診斷的原因。
3. 任一來源同步、browser、embedding 或背景任務故障，不得拖垮聊天，也不得在重啟時改寫其他仍在執行的工作。

## 範圍、證據與限制

- 已取得上述 commit 的獨立唯讀 checkout，檢查架構文件、composition root、對話／記憶／工具／同步關鍵路徑、相關測試與部署設定。
- 對正式來源中的函式／類別做了五組隔離驗證：保留原碼定義，用假的 encoder、資料庫介面和檢索結果隔離依賴。它們是局部行為證據，不是整個 application 或 production 的端到端測試。
- 本輪沒有安裝整套 application 依賴、重新跑完整 pytest、呼叫付費模型、修改 production 或執行 reset。
- 使用者確認曾因 Knowledge Fabric sync 問題造成 production 故障。本輪未取得該事故的 Railway 資源曲線、程序退出原因與同期日誌，因此不能把下列風險直接寫成事故根因。
- 前一輪已查閱同一 main commit 的 CI／線上驗收：Web、Connector、Docker、PostgreSQL foundation 通過；Python／Public Demo 有失敗。那些檢查不能證明本輪發現的接線與併發問題不存在。
- 規模盤點：backend 387 個 Python 檔／104,428 行，tests 227 個 Python 檔／41,806 行，Portal 73 個 TSX 檔／26,313 行，Connector 38 個 TS 檔／10,303 行（含同目錄測試），程式宣告 158 個不同 table 名。這是原碼盤點，不是 production 實際表數，也不是品質評分。此次屬整體架構與核心路徑審查，不是逐行安全稽核。

證據標記：**原碼確認**、**隔離重現**、**風險推論**、**待線上證據**。P1 表示核心正確性／可用性阻礙；P2 表示品質、擴展或可維護性問題。尚無證據宣告一個目前正在發生的 P0 事故。

## 主要發現

### R01｜P1：獨立 Fabric worker 的啟動會執行全站 recovery

**原碼確認；跨程序干擾為有明確路徑的風險，未在 production 重現。**

`knowledge_fabric_worker.serve()` 仍呼叫 `create_app()`。後者建立 `DurableRuntimeRepository`，其建構子立即執行全表 recovery：把正在生成的 Character step、已 claim 的 delivery／side effect 改成 uncertain 或 failed。`create_app()` 同時執行 Matrix recovery，並把全部 `JOB_RUNNING` ingestion jobs 重新排隊。

這些 recovery 查詢沒有用 worker identity、心跳逾時或租約失效區分「已死的工作」與「另一個程序還在做的工作」。因此，在 API 與 worker 共用資料庫的部署中，啟動／重啟 worker 有機會使仍在工作的 API 任務失效；啟動另一個 API 也有同類風險。

**要求：**拆開 API 與 worker 的 composition root；物件建構不能觸發跨服務 recovery。把 schema migration、任務執行與租約回收分成明確責任。只回收已證實失效的 owner／lease，保留 side effect uncertain 邊界，不盲目重放。

**驗收：**API 正在生成、Discord 正在送出、ingestion 正在發布時，啟動／終止／重啟另一服務；原工作不得被錯誤重設，不得重複外部動作。

來源：[worker 入口](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_worker.py)、[app 組裝](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/api/app.py)、[runtime recovery](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/runtime_durability_repository.py)、[ingestion recovery](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/knowledge_fabric_content_repository.py)。

### R02｜P1：排程 coroutine 死亡，不等於服務程序退出

**隔離重現。**

External sync scheduler 捕捉了 `sync(claim)` 的部分錯誤，但 `claim_due()`、`mark_result()`、報告持久化等例外可以離開 `_run()`。`start()` 只檢查 `_task is None`，不檢查已完成／失敗；worker 主程序仍在等待 shutdown，沒有監督子任務。

注入一次資料庫例外，得到：背景 task 終止；再次 `start()` 未重啟；`stop()` 再拋出該例外。Derived worker 與 cleanup 也應依相同失敗模型審查。`/health` 使用 startup 保存的 storage 狀態，不能證明資料庫當下可用或 worker 仍在前進。

**要求：**加入有界退避、錯誤分類、子任務監督和 worker 心跳；致命錯誤要明確退出，由服務管理器重啟。報告寫入失敗不得使核心工作默默永久停止，也不得把未知執行結果當成功重放。分開 liveness、readiness 與 job freshness。

**驗收：**claim、renew、publish、mark、report 各階段注入資料庫短暫不可用；恢復後可繼續或明確進入人工處理狀態，管理介面不顯示虛假的健康。

來源：[scheduler](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_external_sync_scheduler.py)、[worker](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_worker.py)、[health](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/api/routes/health.py)。

### R03｜P1：目前的資源限制不足以保證 sync 不影響聊天

**原碼確認限制位置；耗盡資源為風險推論，事故原因待線上證據。**

已有值得保留的保護：預設不啟動 API 內 Fabric workers、Source 排程 opt-in、一次 claim 一個來源、租約續期、靜態 HTTPS bounded reads、browser context semaphore、頁數／深度限制與發布 fence。不能說目前「完全沒有同步控制」。

但動態擷取的 JSON 路徑先 `await response.body()`，再檢查 128 KiB；DOM 也先取得再檢查 1 MiB。這限制了接受／保存的資料，不保證峰值 RAM 有界。單一 rendered collection 可走到 100 頁，仍需整個 job 的時間、下載量、browser CPU／RAM／PID 預算。來源排程、browser 及索引沒有被證明在 production 具備足夠資源隔離；不同程序仍可能爭用同一個 DB。

**要求：**先縮窄 acquisition：靜態文件／明確 feed／有契約的 API 優先；generic rendered crawl 預設不開。建立每 job／來源／租戶預算、可取消性、進度 checkpoint、可重試單位、backpressure 及受限 browser worker。用資源限制約束失敗，而不是只檢查保存結果大小。

**驗收：**大頁、慢頁、巨型 JSON、重複 sitemap、故障來源、DB 飽和及 worker kill 下，聊天延遲仍在約定 SLO 內，來源可停用、續跑且不重複發布。先量現有 p95／p99，再設定數值，不捏造現況或容器容量。

來源：[browser 擷取](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/browser_runtime.py)、[collection sync](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_website_collection_sync.py)、[9/2 隔離修復](https://github.com/wong001110/character-relay/commit/79bbf0359c683acff63e9a901e473dcecb7aa6b2)。

### R04｜P1：PendingAction 續接元件未接入正式 runtime

**原碼與全 src AST 呼叫搜尋確認。**

`PendingActionService.register()`／`resolve_continuation()` 有程式與單元測試，但正式 `src` 找不到建立該 service 或呼叫 `resolve_continuation()` 的地方。`create_pending_action()` 的唯一正式呼叫位於這個未接線的 service。一般工具 context 仍直接取 `payload.text`；強制載入工具的正式 Media 路徑只補 `media.inspect`。

因此不能因為有 PendingAction table、class、tests，就認定「剛才那個，再試一次」已可靠支援。這也修正了前次只依 README／架構文件對完成度做的較樂觀判斷。

**要求：**定義一個可追蹤的互動／任務續接狀態，保存原請求、已確認參數、所需能力、等待原因、授權來源與結果引用。新的 turn 可以重新發現工具，但仍須重新檢查當下權限和可用性；取消或換人不能誤續接。

**驗收：**工具 unavailable → 使用者配置 →「再試」→同一任務成功；同時兩個未完成請求需釐清；別的成員不能挾持；重啟後不重複產圖／提醒。

來源：[PendingAction](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/pending_actions_v3.py)、[Connector](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/connector_runtime.py)、[Media runtime](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/media_connector_runtime.py)。

### R05｜P1：工具發現把「沒選中」變成「沒有能力」

**原碼確認與隔離重現。**

目前 selector 只讀當輪 trigger，使用手寫中英文 intent patterns、dense 門檻 0.48 與最多四個候選。帶 side effect 的工具沒有當輪 explicit pattern 就不入選；embedding 出錯時反而回退為全部已分配／可用工具。

用相同已授權 `image.generate` 測試「再試試，剛剛已經 assign 了」：正常 encoder 看不到工具，encoder unavailable 反而看得到。這證明能力可見性會因檢索策略而改變；**不是證明 embedding outage 能越權執行**。

Tool session 在開始時固定 `provider_tools`，正式 Media 路徑兩輪工具上限；沒有用後續工具結果擴充 schema 的 discovery loop。這個設計即使包成 MCP，也會繼續漏工具。

**要求：**拆開 registered → authorized → configured/healthy → discoverable → loaded → execution-approved。工具未載入不能直接說不存在。少量常用工具直接供應；較大的 catalog 用漸進載入；讓模型有受控 discovery／browse 路徑，重查已授權目錄、alias 和版本更新。紀錄缺席原因、候選排序、schema 載入與執行結果。

**驗收：**中英混合、口語改述、代詞續接、搜尋零結果、schema 變動、同名工具、憑證缺失、權限撤回、超過四個相關能力，以及發現→呼叫→修正參數的多步流程。

來源：[selector](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/prompt_budget.py)、[tool session](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/targets/prompt_model.py)。

### R06｜P1：記憶檢索存在不可見的候選範圍限制

**原碼確認。**

- 自動 context 取 actor 相關的最多 60 個 Belief，以 importance／updated_at 排序，而非按當前問題作全面檢索；取最近 24 個 Episode 再篩選。
- `memory.search` 先取最多 160 個 Belief 再做 semantic ranking；相關但較低 importance 的紀錄可能根本不在候選內。
- `conversation.search` 請求 120 個 Thread，repository 實際上限是 100，並排除 archived；Episode 限最近 200 個。增加模型 context window 不會找回候選集合以外的資料。
- 三個內部 recall tools 在 catalog 被隱藏；Roleplay 的正常 enabled list 沒有加入它們。Turn Director 只在 `external_lookup_needed` 分支執行內部讀取，而一般記憶問題未必觸發這個條件。
- 自動 Episode 路徑有「角色是否感知」檢查，internal conversation search 的候選主要按 owner／server 篩選。擴大工具可見性之前，要先明確統一感知權限，不能把 server 可讀等同角色親歷。

**要求：**保留 Belief／Episode 的語義分工，改寫 retrieval 與 context assembly。先以正式權限、角色感知、有效版本縮小可搜尋空间，再使用 SQL／FTS／dense 的查詢相關性找候選。固定 top-k 應限制輸出，不應成為唯一歷史搜尋窗口。重要偏好、當前任務和最近原文分別有穩定位置；允許按需查記憶。

**驗收：**將正確記憶放到第 101 個 Thread／第 201 個 Episode／第 161 個低 importance Belief 以外，仍能在授權範圍搜尋到；修正與撤回生效；另一角色未感知的私人互動不得被帶出。

來源：[ContextResolver](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/context_resolver_v3.py)、[internal recall](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/internal_context.py)、[Belief repository](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/belief_repository.py)、[Thread repository](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/conversation_structure_repository.py)。

### R07｜P1：Knowledge Fabric 的檢索能力與正式接線有落差

**原碼確認與隔離重現。**

1. `KnowledgeQueryEngine` 支援 dense，但 `create_app()` 建立它時沒有傳 embedder；全 `src` 沒有 `upsert_embedding()` 呼叫。索引 worker 的 rebuild 只建立 retrieval entry。pgvector 的 schema／測試存在，不等於正式 Fabric flow 已有完整 embedding 寫入與查詢。這個結論不否定其他模組的 FastEmbed 使用。
2. 先按 Server 可用 Corpus 取前四個結果，再做 Character allow/deny。若前四個都被角色拒絕、第五個可用，角色得到零結果；隔離測試重現。這是召回被前面的候選耗盡，不是已證實的權限資料洩漏。
3. `KnowledgeContextBuilder` 固定用 `overview`，即使底層有 exact/current/code 模式，Character-facing input 也不能選。`current` freshness、timeline/spoiler/perspective 的完整策略仍未交付，不能以架構圖當完成證據。
4. prompt 的 2,600 字元 knowledge budget 會整段丟棄過長 evidence。2,700 字元正文包裝後為 3,221 字元，admitted 1 hit，實際 prompt 0 hit；現有 trace 的 selected count 主要在裁切前計算。

**要求：**先決定 Fabric 的最小正式檢索路徑，接通 ingestion→index→query→prompt 並做真實資料驗證。Character policy 要影響候選範圍或採安全的 refill；切片保留 evidence 邊界與 provenance；trace 記錄最終實際進 prompt 的內容引用與省略原因。Dense 只在有增益的語料／查詢上引入，不能只為完成勾選。

來源：[app composition](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/api/app.py)、[query engine](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_query.py)、[index repository](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/knowledge_fabric_index_repository.py)、[knowledge context](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/knowledge_fabric_context.py)。

### R08｜P2：溝通品質受 context、工作狀態和交付協定共同影響

**原碼確認；品質影響需要實際對話回放量化。**

- working state 的 open questions／waiting states 仍從 summary 的問號與中英文 cue 推導；它不是可靠的承諾／任務狀態機。
- Episode 新增 segment 時會以最新 summary 覆蓋 `record.summary`；key_events、原始引用仍有保留，所以不能說歷史全丟失，但自動 context 常只看到 summary，早期重要決定可能被遮蔽。
- ContextBundle 的 sufficiency 在多數情況下只要有某種內容就判定 sufficient；「有資料」不等於「足以回答這個問題」。
- context 建構的大範圍例外會導致 graph 結束為 silent。選擇沉默與因依賴故障無法回答，需要分開。
- 工具呼叫中的 assistant text 放在模型 history，主要正常交付在工具迴圈結束、Smart Output 驗證後。單靠在 Prompt 寫「先回覆一下」不能建立可靠的先回應再執行體驗。

**要求：**將「角色是否想說話」「任務是否正在處理」「依賴是否故障」分開表示。設計可持久化、可去重的 acknowledgment／progress／result／cancelled／failed 事件，再由角色風格呈現。輕聊天不強制走研究、事實抽取與多層判斷；重要更正和待完成請求保留同步處理，非必要 enrichment 移出延遲關鍵路徑。

不要預設移除 Smart Participation、Social State 或語義模型會更好。用 ablation 比較完整流程與簡化流程：自然度、角色一致性、答對對象、錯誤沉默、重複插話、延遲及成本。

來源：[conversation runtime](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/conversation_runtime.py)、[Episode persistence](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/persistence/conversation_runtime_repository.py)、[graph](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/orchestration/character_turn_graph.py)、[prompt／delivery](https://github.com/wong001110/character-relay/blob/d23e7f22229788068dbb76abf9e403fd0a4bcc7d/src/echo_masque/connector_runtime.py)。

### R09｜P2：交付標準偏向元件完成，缺少產品路徑證據

元件有大量測試，並不是沒有工程紀律；但 R04、R06、R07 顯示「有 class／schema／測試」尚未構成真正可用的功能。active plan 仍指向舊分支與未更新的 Phase 13。單靠目前 mutation workflow 也看不到上述接線缺口，其 Python configured scope 集中在五個 Fabric policy 檔。

**要求：**沿用現有 docs 結構，更新失準契約與 handoff，將舊 execution record 歸檔；不再另建一整套 Agent Lore／Bible 階層。每個功能的完成證據必須包含：實際入口、正式依賴組裝、持久化、結果交付、觀測、失敗／恢復，以及何種環境驗過。

Evaluation lab 可以保留並擴展；以匿名化真實故障對話建立版本化 replay set。程式斷言測量客觀結果；人類盲評與校準過的 judge 評量自然度；judge 判斷不作單一真值。

## Harness 與 MCP 的正確位置

### 開發方式與產品 runtime 要分開

AI-Native Development Practice 管的是「如何開發、驗證與交付 Character Relay」；Character Relay 自己仍需產品特定的角色、權限、對話感知、記憶和交付邊界。

Native-first 的含義是先利用既有工具已提供的 session、編排、checkpoint、trace 和擴充能力，再補產品缺口。它不等於把 coding harness 的工作目錄記憶、system prompt 或檔案存取方式直接當成多角色群聊記憶。

現有 LangGraph 可以保留作候選底座。官方區分 checkpointer（執行緒／執行狀態）與 store（跨執行緒資料）；這可幫忙釐清邊界，但不會自動解決角色感知或資料權限。選擇既有 durable ledger 或原生 checkpoint 作主要執行狀態來源，避免兩套都聲稱 authoritative；Discord 感知 Thread 也不必一對一等於 graph execution thread。[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

### MCP 是接入協定，不是語義搜尋或可靠性的保證

MCP 提供工具列舉、呼叫與目錄更新等協定；Host 仍要負責目錄缓存、頁面完整性、授權、schema 載入與錯誤處理。語義 tool search／漸進載入是另一層設計。Anthropic 的 Tool Search 展示了按需載入的做法，不能直接假設所有模型 API 支援相同原生機制。[MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)、[Tool Search 設計](https://www.anthropic.com/engineering/advanced-tool-use)

建議的 capability flow（以下名稱是設計語義，不是已存在 API）：

1. 從內建 adapter 與 MCP server 取得註冊目錄，保留版本／來源及 schema 指紋。
2. 先按 owner／server／deployment／character 權限過濾，再提供目錄摘要或搜尋。
3. 當前任務需要的能力可 pin；一般任務搜尋少量工具，找不到時允許 alias／分類瀏覽／刷新，不能直接下「不存在」結論。
4. 將工具載入這輪模型的 schema；tool result 可以促使下一步再發現工具。預留 discovery 的步數，不讓兩輪上限吃掉真正執行機會。
5. Runtime 在每次呼叫重新驗證身份、參數、資源、授權及冪等性。來源工具提供的安全註解不能取代此檢查。
6. 保留 unavailable、not configured、not authorized、not loaded、not found、execution failed 的區別；對用戶說法依可公開資訊收斂。

內建的便宜工具不必為統一形式全部繞一層 MCP；先接一個受控 MCP 來源驗證完整旅程。小型工具集保留直接載入，避免每次聊天增加一次搜尋。

### Memory 不需要因為「看起來舊」全部替換

短期工作狀態、長期語義記憶、事件記憶與外部知識仍是有用分工。Context engineering 的重點是選擇、壓縮及按需找回資料，並追蹤來源，而不是把所有歷史塞進 prompt。[Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、[Memory 概念](https://docs.langchain.com/oss/python/concepts/memory)

建議保留原始 Evidence 與可修正 Belief；重構其寫入／撤回／召回／感知政策。不要用單一全局摘要取代多使用者、多角色的命名空間。角色 persona、用戶明示偏好、角色推測、任務進度與外部世界知識不能互相覆寫。

## 保留／重構／延後矩陣

| 區域 | 建議 | 理由與邊界 |
|---|---|---|
| Character Cards、persona、deployment／server 身分 | 保留主要產品概念 | 角色產品的核心，不需為換 harness 重造 |
| Auth、credential vault、owner/server 隔離 | 保留契約、驗證接線 | 權限仍由 Runtime 擁有；本輪不是完整安全認證 |
| Discord connector、delivery acknowledgment、冪等帳本 | 保留並強化 | 把重啟與不確定結果做對，再考慮更換底座 |
| LangGraph／現有編排 | 比較後選擇性簡化 | 不先改語言或框架；用相同模型與回放隔離架構差異 |
| Context assembly／Memory retrieval | 大幅重構 | 候選範圍、感知、query relevance、預算與失敗降級均影響品質 |
| Pending actions／long-running interaction | 重構並正式接線 | 把「再試」與先回應後執行變成可驗證流程 |
| Tool selector／catalog | 重構；增加漸進發現 | 保留執行授權，不保留漏選即消失的唯一入口 |
| MCP | 作 adapter 漸進導入 | 不把 protocol 當成 memory／發現品質的替代品 |
| Knowledge Corpus／SourceVersion／Evidence／access | 保留核心 | 可追溯知識與角色認知邊界有價值 |
| Fabric scheduler、startup、recovery、acquisition | 優先重構 | 確認部署隔離、租約與失敗恢復，再擴來源 |
| 視覺角色辨識、廣泛動態網站抓取、複雜圖譜 enrichment | 暫停擴展 | 先證明核心同步與聊天品質；保留既有資料，不做 reset |
| Presence／Social／Discovery | 保留、做消融比較 | 檢查哪些真的提升互動；背景探索與聊天分配獨立預算 |
| Echo Masque 評估功能 | 保留作產品驗證資產 | 擴展 multi-turn、tool journey、故障恢復，而非只測 OOC |
| Portal notebook 風格與導航 | 保留 | 優先改能反映真實 runtime 的狀態與診斷，不重畫全站 |
| Local gaming／WebRTC／coding-agent adapter | 維持 deferred | Cloud 邊界穩定前不增加另一個分散式故障面 |

## 建議交付順序：依證據調整，非固定 Phase 儀式

### A｜先穩住 production 與收集事故證據

目標：來源故障不能拖垮聊天，worker 重啟不能損傷別人的活躍任務。

範圍：R01–R03、API／worker composition、health 與 recovery。取得事故期間的 deploy commit／服務拓撲、exit code、RAM/CPU/PID/DB pool 指標、啟用來源、頁數、同期 exception；在一次性環境重現。未知來源先維持停用，不自動清空知識、不憑空宣稱故障已治好。

Gate：跨程序重啟、重複 claim、資料庫短斷、browser 資源上限與取消測試。涉及 recovery 的 migration 需一次性資料副本／備份與回復演練。

### B｜建立最小但真實的對話／工具品質基線

以 20–40 個匿名化案例作建議起點，具體數量依涵蓋風險調整。涵蓋續接、過期記憶、修正、多人混聊、角色差異、主動沉默、工具 unavailable、schema discovery、長工作回報與取消。

固定模型和資料先比較現況；不要同時換模型、記憶庫、框架與 prompt，否則無法判斷何者改善品質。記錄成功率、誤續接、錯誤自信、工具召回、自然度盲評、首個回應／最終結果延遲與每成功任務成本。這些是待量測指標，不是現有 production 指標。[Agent eval 設計參考](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

Gate：使用目前 main 執行同一回放集，建立紅綠分布；把真實失敗轉成回歸，不以單純「測試數量增加」完成。

### C｜先交付一條完整縱向流程

推薦用：「使用者請求產圖 → 角色先回應 → 發現未配置 → 使用者補好 →『再試』→ 正確執行 → 回報結果 → 重啟不重複執行」。包含任務狀態、目錄發現、memory 按需找回、交付事件與觀測。

這一條旅程會迫使 R04–R08 的責任邊界落地。用小範圍新路徑逐步替換，舊權限契約保留；新投影可離線／shadow 比較，但不可 shadow 執行產圖、提醒等副作用。

Gate：對照 B 的基線，成功率與連貫性改善，沒有權限／重複執行退步；標記省略與失敗原因可供追查。

### D｜再擴長期記憶與 Fabric 實際檢索

接通完整 retrieval；原始資料可回溯、修正／刪除可傳到索引與摘要、query 可以找到近期窗口外的內容。只接一個可控來源完成首次同步、增量、刪除、取消、重啟後續跑，再逐個擴來源。

Gate：一個真實 corpus 的已知問答、角色不同 allow/deny、來源更新、第五筆候選、長 evidence 與中英查詢均有端到端證據。Dense／圖譜／摘要要逐項顯示相對簡化 baseline 的增益。

### E｜MCP 擴充與運維介面，最後才接 Local

在 capability contracts 穩定後導入一個 MCP server：驗證列舉 pagination、目錄更新、schema 版本、工具命名衝突、連線失敗和執行再授權。Portal 顯示實際 worker heartbeat、進度、拒絕／省略原因及最終 prompt evidence 摘要。Local 維持後續里程碑。

## 必須保留的驗證案例

| 案例 | 需觀察的結果 |
|---|---|
| 無當輪關鍵字的「再試」 | 能續接原任務；不能錯接其他人或已取消工作 |
| 記憶移出最近 N 筆 | 授權且相關的舊記憶仍能找回 |
| 新資訊修正舊 Belief | 新版本生效，舊版本保留來源但不以 active 回答 |
| 角色 A 未感知的私密互動 | 角色 B 不得藉 internal recall 取得 |
| 四個角色不允許的結果擠掉可用結果 | 仍能找到真正允許的相關 evidence |
| 檢索結果大於 prompt budget | 有保留邊界的 excerpt 或可追蹤的省略，不能 trace 說用了其實沒用 |
| catalog search miss／refresh／schema change | 不將 not loaded 說成不存在；執行前再驗證 |
| 寫工具已執行、回報前斷線 | 不盲目重放，保留未知／已完成的可核查狀態 |
| worker 在 API 任務執行中重啟 | 不重設仍活躍的任務與 delivery |
| claim／renew／report 時資料庫失敗 | 有恢復或明確終止；不能 background task 死了 process 卻假健康 |
| browser 大 JSON／慢網站／很多來源 | 受資源與時間预算限制，聊天服務可繼續 |
| 群聊中段有多個話題／角色 | 回覆正確對象，沒有所有角色輪流重複總結 |

## 新開發方式如何落到這次重構

- Agent Lore 已 deprecated；不新增另一層跨 repo 強制 cognition 或固定 Main/Sub 拓樸。
- 先讀現有 harness 能力與 project truth；有獨立研究、context isolation 或驗證收益才委派。
- 按風險選驗證：純 UI 字句不跑全套；authorization／recovery／資料切換要做對應邊界和故障測試；確定性的關鍵決策有適用 mutation scope 才使用。
- 對話風格不能靠 mutation 分數證明；worker 重啟不能靠 prompt judge 證明。
- 每個 coherent change 包含能說明「為何需要、改了何種行為、如何證明」的證據；不因規定一 phase 一 commit 而延後必要的診斷或故障修復。
- 新方向是審查提案。使用者已開放大部分機制可重構，但此文件沒有偷偷把新 schema／API／migration 當成已鎖定規格，也沒有授權刪除既有資料。

## 隔離驗證結果

| Probe | 結果 |
|---|---|
| Tool continuation visibility | 同一已授權圖片工具：續接句＋正常 encoder 為空；encoder unavailable 或明確產圖句可見 |
| Scheduler transient DB failure | task 終止；再次 start 不重啟；stop 再拋例外 |
| Character post-filter starvation | server 前四筆全部不允許、第五筆允許時，Character 得零筆且無 refill |
| Prompt evidence omission | 2,700 字元 evidence 包裝成 3,221 字元；2,600 預算下 admitted 1、prompt 0 |
| Production wiring AST audit | src 中 PendingActionService 建立／resolve_continuation 呼叫為零；Fabric upsert_embedding 呼叫為零；唯一 KnowledgeQueryEngine 建構未傳 embedder |

所有 probe 都未對 production 發送請求或執行副作用。靜態呼叫盤點不能抽象地排除任意外部 monkey-patch；已檢查 repo 的正式 composition 路徑，未發現其他動態接線。完整整合測試、負載測試與實際模型品質比較仍應在實作階段依上述 gates 補上。

## 仍待解決的證據缺口

1. **事故 postmortem：**production 的程序／資源與同期 sync 日誌；未取得前不把 OOM、PID 耗盡或 DB contention 當既定根因。
2. **實際對話樣本：**需要以用戶認為「不好」的具體互動建立基線，區分模型能力、prompt、候選漏失和 delivery 問題。
3. **實際部署拓樸：**獨立 Fabric worker 是否已建立、其啟動命令與資源額度、API replicas、DB pool／statement timeout。本輪 repo 只能證明入口存在。
4. **目標體驗權重：**預設以群聊角色連貫性、真實工具結果、服務穩定為優先；更主動的 autonomy 或 gaming 不放進首批重構。

**下一個具體 gate：完成 A 的 startup／recovery／worker supervision 設計與一次性環境驗證，同時建立 B 的失敗回放基線。**這兩者提供後續大幅重構的可比較依據。

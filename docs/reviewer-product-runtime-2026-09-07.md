# Character Relay：產品完成度與 Runtime 審查

日期：2026-09-07。狀態：**歷史審查基線；R10–R17 的實作處置已另行完成，外部驗證仍有待辦**。

使用者後續授權的修補、測試與剩餘限制見 [remaining-gap closeout](reliability-gap-closeout.md)。
以下「建議／尚未實作」描述的是當時基線，不代表目前分支狀態；沒有功能刪除決定。

審查基線：`895f81779bb4edc28f4cbd509d3216b4de63bc9e`，PR #204 的未合併分支；main 為 `d23e7f22229788068dbb76abf9e403fd0a4bcc7d`。使用者已暫緩本地模型與攻擊式重現；本輪只有原始碼、既有測試及 CI 證據審查。Root 整合產品介面、記憶品質、Runtime 成本三份獨立 reviewer 意見，重新核對正式呼叫點。

## 判斷基準

以「Discord 裡持續存在、記得相關事情、能自然互動並可靠完成工具工作的角色」為核心成果。我的判斷是：目前功能廣度超過部分流程的完成度，先接完已有能力的使用、結果接收、取消、維護及驗證流程，比繼續擴大能力清單更有價值。這是依據下列缺口的產品判斷；沒有使用分析，不能據此宣稱某功能沒人使用。

保留 Runtime 的權限與副作用責任、owner/server/Character 隔離、原始證據來源，以及不重播不確定副作用等既有契約。工作記憶過期不等於刪除長期記憶；外部搜尋結果也不能直接升格為可信知識。

## 優先修正的缺口

### R10／高：Discord 工作佇列沒有容量與時效上限

證據：`connectors/discord/src/index.ts` 的 `enqueue`，以及 `turnIngress.ts` 的 preflight Promise chain，會持續串接工作；burst collector 的單批限制不等於整體佇列限制。

影響：忙碌頻道可能累積已失去時效的完整回合，延後回覆並消耗模型費用。尚未執行負載測試，不能聲稱已量到 production 的積壓程度。

建議：目的地及全域容量、最長排隊時間、低優先自主參與的合併策略；明確請求必須有可見的接受、延後或拒絕結果。驗收：慢速假 provider 下容量有界，過期自主參與不呼叫模型，能觀察 queue age/depth。

### R11／高：新訊息與逾時尚未形成完整回合生命週期

證據：`index.ts` 在 social step 前檢查 `supersedingHumanTurn()`，生成後到 delivery claim/send 的路徑缺乏相同檢查；一般角色回合也缺少對應處理。`relayClient.ts` 的請求上限為 45 秒，`connector_runtime.py` 一回合可串接 Director、工具回合及修復；`api/routes/connectors.py` 建立 `generating` 後，未見涵蓋取消的終態處理。

影響：若新訊息已改變原請求，舊回答仍可能送出；client timeout 與 server 是否停止沒有共同契約。是否遺留 generating 取決於實際取消傳播，不能把 client abort 當作 server 必定停止的證據。

建議：共用端到端 deadline、傳遞剩餘時間、delivery 前核對回合版本、逾時與取消必須終結或進入 reconciliation。先定義「新訊息是補充、獨立請求還是取代」；不能一律丟棄舊的明確請求。驗收：假 provider 延遲與明確取代案例不送出舊答案、不永久 generating，也不重複執行已發生或不確定的工具副作用。

### R12／高：短期工作記憶的過期契約沒有接到實際讀取

證據：`conversation_runtime.py::checkpoint_inactive` 沒有正式 caller；`persistence/conversation_runtime_repository.py::working_state` 只檢查存在及 owner，不檢查 status/expiry。`context_resolver_v3.py` 讀取後會組入 current object、open questions 與 waiting state。

影響：過期甚至 archived 的 scratch 仍可能影響後續回覆和 prompt 成本。既有 belief correction shield 已正式接入，不能因此說整個記憶系統沒有修正能力。

建議：讀取時只允許有效 scratch，既有維護機制執行 inactivity checkpoint；歷史 episode 與長期 belief 依各自契約保留。驗收：超過 TTL 或已封存的工作狀態不再進 prompt，維護可重複執行且不跨 scope。

### R13／中高：自動 Knowledge Gap 搜尋有啟動，缺少結果接收流程

證據：`character_turn_context_v3.py::_dispatch_knowledge_gap_search` 會追蹤背景 task，但忽略 `service.search()` 的回傳。`knowledge_gap_discovery_v3.py` 成功回傳 `candidates_ready` preview，`accept_evidence()` 除定義與測試外沒有正式 caller。

影響：符合觸發條件時可能花費搜尋資源，卻沒有將候選經驗證接回 gap 的正式流程；gap 也可能停留在 searching。不是「完全沒追蹤 task」，也不是允許把未驗證候選直接當知識。

建議：在候選持久化、來源驗證、接受結果及失敗／重試終態完成前，暫緩擴大自動觸發。驗收：候選能經 scoped 驗證成為可追溯 evidence，或明確結束／重新開啟，不留下無人處理的 searching。

### R14／高：初次啟用仍有可直接阻斷使用的斷點

證據：`docs/user/discord-setup.md` 要求複製 Connection ID，`web/src/DeploymentCenter.tsx` 的 connection 卡片顯示名稱及外部帳號 ID，沒有呈現 connector 所需的內部 connection UUID。`KnowledgeFabricPanel.tsx` 缺少 scope 時只有要求 SuperAdmin bootstrap 的空狀態；後端 `/admin/server-scopes` 已存在，但 Portal 沒有對應入口。設定指南的 Active／channel 描述，也與目前新建 paused、server profile 流程不一致。

建議：可複製正確 ID、角色感知的 scope bootstrap 入口、文件同步，以及從憑證設定到 connector online／部署啟用／第一則回覆的逐步狀態。保持 SuperAdmin bootstrap 和 scope 權限，不在訪問頁面時自動建 scope 或授權。驗收：新使用者依指南完成；無 scope 的管理員能完成既有授權流程，普通使用者得到可執行的求助提示。

### R15／中高：Provider 的能力降級缺少恢復與精確隔離

證據：`provider_capabilities.py::endpoint_key` 使用 hostname 並將 path casefold，省略 port/scheme。能力查詢及 `provider_capability_persistence.py` 讀取沒有負面結果 TTL；`provider_io.py` 會在請求前跳過已判為 unsupported 的結構化輸出模式。一般模糊協定錯誤已有避免永久降級的處理，問題不是所有 transient errors 都被永久記住。

本輪純本地驗證：同 host 的 `:8443/v1` 與 `:9443/v1` 產生同 key；`/TenantA/v1` 與 `/tenanta/v1` 也同 key。既有持久化測試 2 項通過；它們沒有覆蓋 TTL 或 endpoint 隔離。

建議：保留實際 endpoint 身分，負面結果有到期／退避再探測及設定變更後的恢復方式。驗收：不同服務不互相污染，已恢復能力可重新被使用。這項不能直接宣稱是目前 MCP「找不到 tool」的確定根因；引入 MCP 本身不會修好能力快取。

### R16／高：現有評測不能代表完整 Discord 角色體驗

證據：`services/trials.py` 建立 `PromptModelTarget` 並執行 scenario suite；`prompt_inspector.py` 組合角色卡靜態 prompt。它們有用途，但沒有等同驗證正式 ingress、參與決策、runtime memory、工具執行及 Discord delivery。Portal 目前沒有完整 browser E2E suite。

建議：在現有 harness 加入少量具代表性的、去識別或合成 Discord 事件重播，走正式 runtime，保存實際 memory/evidence refs、可見工具、工具結果、delivery 與延遲成本。覆蓋多人交錯、明確更正、舊訊息、取消、工具失敗、跨 scope 與外部不可信內容。靜態 Prompt Inspector 應明確命名；另從真實 turn manifest 查看實際上下文。

驗收：行為以明確斷言驗證，角色自然度與記憶相關性以人工案例校準；品質判讀和 security pass 分開。LLM judge 可輔助比較，不自動更改正式角色設定，也不能單獨核准 release。

### R17／中：Trace 寫入、保留及記憶管理還需補上運維責任

證據：`orchestration/character_turn_graph.py` 每個節點同步呼叫 trace sink；`runtime_durability_repository.py` 每筆事件開 session/commit。該 repository 的 `prune()` 沒有正式 caller。節點有 timestamps，但缺少排隊、工具、delivery 的一致耗時拆解。`BeliefRepository.reject()` 也未見正式管理入口，deployment 刪除和跨 deployment 的 server/Character 記憶保留需另定契約。

建議：將診斷事件批次寫入，保留必要的 durable 操作／交付邊界；有界維護清除過期終態 traces，保留 active／uncertain 工作。補「這段記憶從哪來、如何更正／排除／忘記」的 scoped 管理及保留矩陣，先決定刪 deployment 是解除關聯還是清理哪些資料。

驗收：trace 可解釋端到端延遲，維護有結果且不清掉待確認副作用；管理操作有權限及可追溯結果。尚未量測同步 commits 對真實吞吐的影響，不以推估數字當效能結果。

## 功能優先級與可減少的複雜度

| 建議 | 功能 | 理由及保留邊界 |
| --- | --- | --- |
| 保留並強化 | Discord 核心對話、角色一致性、scoped recall、更正、工具完成／取消 | 直接決定角色是否可靠、有持續感；加入確認收到、進度與最終結果的完整體驗 |
| 收斂成一條可用流程 | Knowledge Fabric | 先完成少量來源的啟用、同步失敗恢復、授權及真正被角色引用；不要同時擴大所有來源／爬取模式 |
| 暫緩擴建 | 自動 Knowledge Gap Discovery | R13 結果流程未完成，先證明搜尋能改善後續回答 |
| 合併／放進進階入口 | Authoring、Calibration、Evaluation、Coverage、Template Labs | 五個 React 元件目前只有定義，未見 shell/router 引用；不是五個已可用產品。先選最小角色/OOC/回歸工作流，無須為湊齊功能而全部掛上 |
| 合併入口 | Discovery 設定與觀測、多個 workspace/matrix 狀態 | `DiscoveryIntelligencePanel.tsx` 指向另處設定；設定在 `ToolSelector.tsx`，另有 `DeploymentDiscoveryWorkspace.tsx`。App 的 workspace/matrix 使用本地 Boolean，缺少可重載／分享的 route；先讓同一 deployment 能直接往返設定與結果 |
| 暫緩廣化並做比較 | 額外語意社交印象、結構／episode 的 Evidence Graph 鏡像 | `revise_impression()` 未見正式 caller；部分投影還沒有可證明的品質收益。不要刪掉已用於互動姿態的 social events，或實際媒體查詢使用的 `REFERENCES` graph edges，也不要把所有圖譜統稱無用 |
| 由量測決定 | MCP、dense retrieval、更多 collector／視覺及爬取模式 | 先辨識失敗在發現、授權、能力、排序、執行還是呈現。MCP 可統一介面，但無法替代 runtime 契約；dense 應由 recall relevance、同步／刪除正確性決定優先級 |
| 維持暫緩 | 本地模型、遊戲／WebRTC、框架替換 | 不屬於本輪 reviewer 任務，沒有重新啟動 |

「重要性較低」不等於「立即移除」。下一步以同模型、同一組代表性事件，逐一關閉可選模組比較角色品質、記憶命中、工具完成、延遲與 token 成本；不能降低 scope/security 邊界來換取效能。沒有可見收益且維護成本高的模組，才提議降級或停止擴建。

## CI 與上線可用性的新證據

`895f817` 的 [主 CI](https://github.com/wong001110/character-relay/actions/runs/34117484100) 已全數通過，Railway Smoke 也成功；[Public Demo Status Check](https://github.com/wong001110/character-relay/actions/runs/34117484124) 失敗。其讀取結果有 2 張 Demo 角色卡，但只有 1 個 credential ready，`ready=false`。這只能證明部署側 readiness 不足，尚未確定是哪個 credential／設定問題，也沒有實際呼叫模型驗證。

`.github/workflows/public-demo-status-check.yml` 固定查 shared production URL，沒有核對 deployed commit；PR 分支還會略過 `ready` 欄位本身、改驗組件。因此不能用它證明 PR 版本的端到端品質。建議區分 deployed health 與 PR preview/version validation，先修好一條可信的公開 Demo 路徑。

## 建議執行順序與驗證範圍

1. 先完成首次使用與部署狀態：R14、Demo readiness、正確版本的 CI 證據。既有 security assessment 的 release blockers 仍需處理。
2. 用正式路徑的最小重播 harness 支撐 R10–R12、R15，以及收到請求／進度／結果／取消的體驗修正；同時建立 scoped 記憶管理與維護責任。
3. R13 先止住沒有結果消費的擴建；依比較結果決定完成或延後。再合併 Labs／Discovery 入口及評估可選模組，最後才擴大 MCP、dense 和來源種類。

本輪驗證：正式 caller／UI 引用交叉搜尋、關鍵實作人工追蹤、2 項既有 capability persistence tests、endpoint key 本地對照、GitHub PR／CI／Demo job 日誌。未修改產品程式、未重跑不相關完整 suite、未做負載或 browser E2E、未啟動 production／真實 provider 測試，也未完成被暫緩的攻擊式 Red Team。詳見既有 [security assessment](security-red-team-2026-09-07.md)；本文件不取代它，也不核准合併或部署。

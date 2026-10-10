# Final independent review: 0b16fbd..930d69c

Reviewer gpt-6.1-sol xhigh (Astra seat failed on workspace credits before a verdict). Read-only source review; no tests, model calls or secret reads. Verdict: With fixes. No Critical, two Important, one Minor.

## Important

1. Late submission callbacks overwrite persisted terminal state: sessions.py submission success/error transactions and recovery success do not check executor_exited_at after await. Background reconciliation may already have completed/exited the run. Preserve exited rows; cover delayed success and timeout.
2. Completed same-ID submission retry omits saved results/proposal cards: useAssistantChat.performSend updates run then attach skips terminal runs. Restore trusted cards and availability with epoch/run guards; cover lost-response retry returning completed.

## Minor (deferred)

Operations docs first paragraph advertises modifying view status, while MediaPatch accepts rating/favorite/source URL/tags. Read-only view status display is supported; view status modification is not. Remove incorrect wording in a later documentation cleanup.

## Strengths

Fresh ownership checks and independent profile/tool credentials; transactional target fingerprint confirmation/audit; scan interruption without replay; bounded trusted DTO/plaintext cards; stable message IDs/byte-bounded SSE/keepalive/nginx delivery.

## Declined to judge

- Conservative uncertain-exit fence: approved and documented operator recovery.
- Writable bootstrap rootfs and native catalog omitting MCP: pinned-image characterization and actual identity/schema evidence.
- Uncached MiniLM / real iOS: explicitly disclosed limitations, future loaded-model gate and no physical-device claim.
- Narrow modification fields and changed-field plus full-tag comparison: intentional scope preserving unrelated edits.

## Fix-pass evidence

Both Important findings reproduced before implementation, then fixed in one author pass:

- Four late original/recovery submission success/timeout races: RED→GREEN; proxy 28 PASS.
- Completed same-ID retry restores saved cards, truncation flag and availability; stale identity response discarded: RED→GREEN; view 19 PASS.
- Whole backend 353 PASS (132.46s), frontend 97 PASS (11.31s), MCP 11 PASS (8.06s), production frontend build PASS (2.10s).
- Actual lab all-process cold restart removes and recreates SQLite WAL/SHM; owner1000/mode0600 and worker read/write rollback PASS.
- H08 native search/recommend/propose/reject and actual streaming/stop/keepalive gates passed. Production enabled after fix commit61ebaae; read-only search and completed same-ID repeat gate PASS.

## Rulings I made (full ledger extraction, chronological)

- Task 1: Ruling: Task headings normalized from H01 to 'Task 1: H01' for skill helpers; Hxx IDs, scope and dependencies retained — cost if wrong: documentation indexing only.

- Task 1: Ruling: merged second review constraints after semantic three-way comparison; remote only had known H01 status/headings changes — identity hash storage, secret mount masking, target-specific idempotency, transaction order, result DTOs and executor evidence are now explicit — cost if wrong: contract revision before H02.

- Task 1: Ruling: pinned /v1/toolsets enumerates native/plugins, omitting MCP (api_server._handle_toolsets and tools_config._get_effective_configurable_toolsets). Validate native enabled tools plus actual outbound exact nine+memory schema, cross-check real MCP SDK enumeration. Do not invent MCP catalog rows — cost if wrong: fail closed when runtime-lock capture differs. Native catalog characterization RED before implementation.

- Task 1: Ruling: actual tool.completed preview is capped500 chars, with no complete DTO/model callid. Trusted internal_app must persist validated result against server-resolved active run with generated HE invocationUUID; H05 projects stored DTO only, never parses preview. Business read tools stay read-only while assistant records maywrite — cost if wrong: H03/H05 contract change now, no partial UI results presented as complete.

- Task 1: Ruling: agent.run_budget_seconds checks turn machinery, not creation/discovery wall time. HE persistent submission deadline/watchdog must coverpreparation andrun; independent noSSE probe stops at180 from submission. Native budget is secondary guard — cost if wrong: assistant staysfaulted instead of releasingunknownexecutor.

- Task 2: initial23tests RED featuremissing. Fixtures explicitly activate syntheticcreatedsessions (production startscreating), and finishseedrun beforepreparation; profilekeyinitwhileliveexecutorblocked. Ruling: toolcontextgeneration and admission fencepersisted; terminal without executor_exited_at stilloccupiesglobal slot. Preparation usesnativeYAMLtemplate JSONquotedscalars withoutaddingYAMLdependencytoHE; legacyAIconfigurationread directly, avoidingget_deepseek_config sideeffectmigration. Costifwrong: assistantfailclosed/preparationrepair, mainmediauntouched.

- Task 2: repositorylayouttemplateassumption reproducedRED ignoringruntime template override. Ruling: HE_ASSISTANT_TEMPLATE_DIR and source/image defaults; H08 image mustcopypublictemplates+preparescript to /srv and settemplatepath asneeded. ExistingDockerfileonlycopiesapp; cannotassumereporootinimage. Costifwrong: preparationfailssafely, runtimeassistantremainsdisabled. Full257PASS77.75s beforetemplatefix; finalupdatedsuitepending.

- Task 2: controlconfirmed repeatedfixedDBcount3FAIL; identical existingdownloadtest in freshDBPASS0.93s. Freshfullsuite running withuniqueHE_DATABASE_URL. Ruling: testdependencies may be reused, testdatabase neverreused acrosspytest invocations — legacyglobalSessionLocal testsretainrows — costifwrong: falsefailure blocksphase; no productiondata changed.

- Model: Ruling: officialDeepSeek API modeldeepseek-flash mapsuser-requestedDeepSeek-V4.1-Flash; use thinkingdisabled with2048outputtokens for predictable firstreleasebudget and testedtoolcompatibility. Costifwrong: lessreasoning depth; changingmode requiresnewcompatibility/budgetprobe.

- Task 3: Ruling: persist tool_results_truncated separately and migrate the H02 schema; H05 returns ToolResultsDTO {items,truncated} — preserve prior validated cards when the next result exceeds 64 KiB, including after reload — cost if wrong: one additive column and response contract revision.

- Task 3: Ruling: internal HTTP wraps validated business DTO in ToolResultDTO; H06 returns only its result to MCP — HE invocation UUID and durable display authority are independent of Hermes previews — cost if wrong: bridge unwrap and HTTP integration adjustment.

- Task 4: Ruling: implement mark_run_stopping/mark_session_deleting in H04 store, reused by H05 before network calls — H04 atomic race guarantees require both sides of the transaction order now — cost if wrong: moving two helpers between phases.

- Task 4: Ruling: ActionResultDTO carries a bounded JobDTO terminal snapshot and scan job IDs derive from proposal UUID — history pruning retains ownership and result without JSON-wide searches — cost if wrong: additive result field and job ID contract revision.

- Task 4: Ruling: perform storage guard outside the SQLite transaction; acquire only the nonblocking folder reservation inside it after checking prior confirmation — concurrent retries return the same job and do not requeue — cost if wrong: a short process mutex is held during the write transaction.

- Task 5: Ruling: HermesClient.stream_events exposes private parsed wire records only to sessions.stream_events, which yields public EventDTO — normalization needs owned HE run/message/result context, unavailable in transport alone — cost if wrong: internal adapter signature adjustment.

- Task 5: Ruling: iteration/output budgets remain authoritative in H01-verified profile config; start_run sends only real pinned input/instructions/provider/model/session_id fields — source _handle_runs ignores proposed max_turns/max_tokens body fields — cost if wrong: runtime configuration gate must detect drift.

- Task 5: Ruling: trusted recovery/watchdog uses DB-selected run ownership and stop_run_row without HTTP user permission checks — demoting or disabling an owner must not strand an already admitted executor; public handlers still recheck active administrator ownership — cost if wrong: internal-only stop helper must remain inaccessible to request fields.

- Task 5: Ruling: display history is projected from HE persisted input/final messages, not raw Hermes tool/system/interim history — canonical message IDs and bounded DTOs survive reconnect without exposing private transcript fields — cost if wrong: native Hermes-only history is not displayed by HE.

- Task 5: Ruling: a separate watchdog persists stop at deadline even when reconciliation HTTP is blocked; bounded network stop operations use independent sessions — subscriber lifetime cannot govern cancellation — cost if wrong: one additional background task and concurrent read/stop RPCs.

- Task 5: Ruling: reject confirmation for still-running runs past their 180s deadline even before watchdog commits; completed runs retain their pending-proposal TTL — direct transaction check closes a scheduling/DB-busy gap — cost if wrong: an uncompleted run proposal must be regenerated after timeout.

- Task 5: Ruling: validate active stream profile generation before HTTP 200, and allow already-final HE streams without profile files; dedicate two HTTP connections to SSE so long subscriptions cannot consume REST stop capacity — cost if wrong: one small additional async HTTP pool.

- Task 6: Ruling: copy only the shared pure Pydantic schemas.py into the bridge image, and use stateless Streamable HTTP with per-request bearer forwarding — prevents DTO drift and transport sessions becoming cross-admin credential containers — cost if wrong: schema changes require rebuilding both images.

- Task 7: Ruling: add assistant-specific nginx routing and disable proxy buffering/gzip in H07 — the browser API otherwise falls through to SPA HTML and cannot exercise the page contract — cost if wrong: one additive proxy location must be carried into H08 deployment.

- Task 7: Ruling: build frontend into a temporary output directory until H08 deploy gates pass — production mounts frontend/dist directly, so a normal build would publish pre-acceptance artifacts — cost if wrong: one extra artifact copy during deployment.

- Task 7: Ruling: add bounded exact add_tags/remove_tags lists to the persisted public proposal after preview; render tags with human field labels and fail closed for legacy truncated previews without those lists — a 50-tag cap could otherwise hide the operation being approved — cost if wrong: additive fields in proposal after/audit JSON and regenerated legacy previews. Backend and UI regressions both observed RED before this fix.

- Task 8: Ruling: repair that single reversed scanner argument in H08 — confirmed scan must actually discover temporary media, existing helper signature and real RED prove the defect — cost if wrong: regular file scanning behavior changes for all modes; production media never used for mutation tests.

- Task 8: Ruling: gateway root has an unregistered private API key and no HE MCP/tools/model credentials; preserve existing root on repeat preparation — multiplex needs a root listener but HE binds only named profiles — cost if wrong: root readiness cannot prove a named profile is usable, so native-chain acceptance remains required.

- Task 8: Ruling: keep Hermes rootfs writable for its root init UID/GID remap, while runtime gateway UID1000 and install tree ownership are verified; tools/MCP stay readonly with dropped caps — selected official entrypoint edits /etc before dropping privileges — cost if wrong: bootstrap has writable container-root state, no host mounts beyond Hermes home.

- Task 8: Ruling: run the tool worker as1000:1000 with all capabilities dropped, matching the actual data directory and DB/WAL/SHM owner1000 (0700/0600); fail deployment on owner mismatch — root with dropped DAC capability could not traverse the existing private directory — cost if wrong: UID-changed deployments need explicit ownership/Compose adjustment, not weakened permissions.

- Task 8: Ruling: accept pinned interrupted_by_user only with run.cancelled, interrupted=true, partial=false, completed=false and no shutdown marker — actual native between-tool stop produced this executor-return status, pinned _execute_run awaits _submit_api_worker before publishing fields — cost if wrong: changed upstream semantics require revalidating the exit predicate; bare cancellation, unknown reasons and shutdown stay fenced. New release regression RED→GREEN, proxy24 PASS.

- Task 8: Ruling: qualify production cold benchmark as uncached MiniLM fallback, rather than claim dense-model memory was measured — production has no weights and tools are network-isolated/offline; current deployment needs no new model download — cost if wrong: adding a real cache later is blocked on a separate cold loaded-model memory gate. Real snapshot2654 rows peak123019264B,1.027s, unchanged backup SHA256.

- Task 8: Ruling: reuse H01 actual180.567s watchdog/181.579s exit and H05 independently blocked-RPC watchdog plus keepalive/restart regressions for unchanged pinned deadline, while H08 measures actual nginx chunks and native stop — repeating the same three-minute synthetic wait adds no new boundary — cost if wrong: future timeout/profile/network changes must repeat full deadline characterization.

- Task 8: Ruling: Chromium responsive/PWA keyboard simulation is the available device evidence; remove the accidental H07 real-iOS gate and explicitly record real iOS unverified — no physical-device access was provided and the approved design requires responsive behavior, not a new device procurement — cost if wrong: device-specific keyboard behavior may need follow-up.

- Task 8: Ruling: defer only production enabled transition until the fresh final review; ship optional addon and migrate/prepare/start it with flag0 first — AGENTS defaults target Docker and implementation is authorized, but review findings must be fixed before exposing new assistant writes — cost if wrong: production chat temporarily shows disabled until final gate. Existing admin5 only; no new admin or real media mutation.

- Final: Ruling: recover the single fresh review with gpt-6.1-sol xhigh after gpt-6-astra failed on workspace credits before findings/verdict — most-capable attempted reviewer unavailable; current user-selected model is callable — cost if wrong: less independent reasoning capacity than the attempted Astra seat; no second opinion/review loop requested.

- Final: Ruling: uncertain-executor fencing remains — approved policy prevents concurrent unknown writes; only independently verified old-process disappearance allows maintenance release — cost if wrong: manual recovery and temporary global unavailability.

- Final: Ruling: pinned writable bootstrap and omitted native MCP catalog stand — measured worker UID1000/cap0 and outbound exact schemas establish actual boundaries — cost if wrong: any upgrade needs identity/tool/budget characterization again.

- Final: Ruling: disclosed uncached MiniLM and Chromium-only mobile coverage stand — current host has no weights and no physical iOS device was provided — cost if wrong: installing vector cache or device-specific behavior requires separate measurement/follow-up.

- Final: Ruling: narrow write fields and target-relevant comparison stand — approved scope is rating/favorite/source URL/tags, unrelated edits must be preserved; complete tags protect requested tag operation — cost if wrong: broader media editing needs a new schema/preview/confirmation design.

- Final: Ruling: retain commits on existing main with no push/merge menu — human authorized one main and per-phase commits; no new integration decision remains — cost if wrong: remote publication still requires a separate instruction.

## Deferred minors

- Final: minor (deferred): docs/hermes-operations.md first paragraph incorrectly advertises modifying view status; actual write scope is rating/favorite/source URL/tags.

## Final production receipt

- 2026-10-10: flag1 persisted; five production services healthy, no private HostPorts or OOM, gateway UID1000/CapEff0. Addon memory limits2013265920 B.
- HE image manifest `sha256:9882860c2e9253fbc8dde4dc45483a2aaf4d95803205abed4d15c10afc546942`; running source SHA matches fix. Hermes remains pinned to runtime-lock, MCP2.0.0.
- Official DeepSeek deepseek-flash (requested DeepSeek-V4.1-Flash), thinking disabled; native production readonly search1/stream89 chunks/4.345s/usage available. Same original request ID returns same completed run/results; no new proposal, mutation or scan. Session cleared and ephemeral login token revoked.
- All8 business tables and2654 media identical to predeploy online backup; unresolved runs0. Protected predeploy DB/frontend/config/old image and consistent prepared profile snapshots retained.
- Actual root backend before UID1000 tool cold start recreates WAL/SHM with owner1000/0600, read/write rollback PASS. All65 new online assets match build bytes;101 retained/updated static assets scanned against7 actual private credentials with zero matches.
- Actual iOS device and a loaded MiniLM cold memory peak remain unverified; keyword fallback and Chromium simulation are the disclosed current coverage.
- Working branch main retained under user's existing per-stage commit authorization; no push requested. Own isolated test containers/networks and plan scratch are removed after this public receipt is committed.

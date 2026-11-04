# P1 Coding Pipeline — Round-004 独立审计报告

**AUDIT_STATUS: COMPLETE**　　**代码结论: CONDITIONAL**　　**真实 21bao 集成: 仍不允许**

- 审计源码 Commit: `888470d661085ee7a183184a74bf3b5a6cf6f556`（父提交 `e544d5e0cc1471c7844baf5c6f0ba10dbbd3db81`，tree `51b57146d1ad4848347269c0ceb95fa664028dab`）
- 分支 `feature/p1-coding-pipeline-20261104`；目录 `experiments/hermes-coding-pipeline-p1/`
- 时间: 2026-11-04T18:20:00+08:00 → 2026-11-04T19:40:00+08:00（UTC+08:00）
- 方式: 只读源码 + 固定快照原样测试 + 独立对抗探针；未连接真实 P0/远端 A2A/付费模型/现网配置。
- 本轮只新增 Round-004 四份报告，未改 P1 源码、Soul、测试或 Round-001~003 报告。

## 1. 结论摘要

Round-003 留下的三个问题**全部判 FIXED**，且都有独立复现证据：R3-001（考卷白名单）、R3-002（run↔事件双向绑定）、R3-003（有效状态呈报）。93 项项目测试原样通过，开发方声明被独立确认。

本轮新增 **3 项问题：P1 1、P2 0、P3 2**。唯一的 P1（R4-001）不是对 R3-002 的否定，而是把项目自己写明的“本地链只做部分篡改检测”边界**做出了可复现证据**：能写 `state.sqlite` 的主体可以用 `Store._event`/`start_run`/`finish_run` 追加合法事件，伪造 Gate 0.2 审批（流水线直接推进到 3+4 并建立工作树，全程无人审批）或伪造一条从未执行的角色记录（`verify_evidence=COMPLIANT`）。

因此判 **CONDITIONAL**：在“任务 home 属于单一受信 OS 账户”这一声明模型内，本轮未发现可复现的门禁绕过或假绿；一旦该前提不成立，R4-001 按项目自身分级即升为 BLOCKER。所有真实集成项仍 NOT_VERIFIED，P1 现在仍不得在 21bao 执行真实任务。

## 2. 审计方法与证据边界

- GitHub tree/blob API 固定 59 个文件，逐个 Git blob SHA-1 + 大小复核；测试前后均 **59/59 匹配，0 错误**。
- 项目测试原样运行：**93/93 passed，0 failures，0 errors**（12 批，`testlogs/batch0..11.xml`），无夹具改动。
- 独立探针：**31 个不重复用例 / 33 次执行**，最终 6 个批次标签（g1b、g2b、g3、g4c、g5、g6）全部 exit 0。`test_positive_*` 断言修复生效，`test_defect_*` 通过代表缺口存在；两者都不等于产品验收。
- 披露：探针文件早期三次运行（`g1.xml/g2.xml/g4.xml`）因我自己的两处错误预期与一次 Windows 换行差异而作废并重跑；这是审计工装问题，不是产品失败，修正后的预期本身被记为 R4-003。
- 本 Commit 只改 `p1/gitops.py`、`p1/state.py`、`p1/workflow.py` 与新增测试；`audit.py`/`contracts.py`/`a2a.py`/`executor.py`/`cli.py` 未变，因此上一轮针对它们的结论按继承回归处理，未被重开。

## 3. Round-003 三项独立结论

| ID | 状态 | 代码证据（文件:行） | 独立验证 |
|---|---|---|---|
| R3-001 | FIXED | p1/gitops.py:97-116 (add-only + ls-tree 仅允许 100644/100755 blob), p1/gitops.py:151-175 (test_path 改为测试模块文件名白名单), p1/audit.py:43-51, p1/workflow.py:222-231 | test_positive_conftest_cannot_be_added_as_exam[tester_gate_a/tester_gate_b]、test_positive_collection_control_files_are_not_test_modules[7 例]、test_positive_real_test_module_names_are_accepted、test_positive_symlink_test_entry_rejected、test_positive_tester_can_still_add_real_exam、test_positive_baseline_and_gate_a_exams_survive_remediation |
| R3-002 | FIXED | p1/state.py:99-156 (事件↔run 双向核对、stage/role/input_sha 比对、重复 dispatch/finish 拒绝)、p1/state.py:158-172 | test_positive_deleted_run_row_is_detected、test_positive_run_metadata_mutation_is_detected[stage/role/input_sha]、test_positive_duplicate_finish_event_is_detected、test_positive_details_and_log_forgery_still_detected、test_positive_inflight_run_blocks_compliance_without_false_chain_error |
| R3-003 | FIXED | p1/workflow.py:124-140 (status 只读有效状态 + persisted_status/integrity_preflight/integrity_errors) | test_positive_status_reports_effective_block_without_sealing、test_positive_status_stays_clean_when_state_consistent |

### R3-001 — FIXED
Tester A/B 在两个关卡新增 `tests/conftest.py` 均被 `audit.py` 的 test-only 白名单拒绝（“test-only role touched non-test path”），流水线停在 NEEDS_RECONCILIATION；`pytest.ini`、`tox.ini`、`setup.cfg`、`pyproject.toml`、`sitecustomize.py`、`tests/__init__.py`、`*.pyc` 都不再是“测试模块”；120000 符号链接条目被新的 `ls-tree` 模式检查拒绝。反向验证：合法新增 `tests/test_new_exam.py` 仍得 COMPLIANT、被 `protected_tests` 记录并到达 Gate 5.9；整改 Worker 若改写 Gate A 考卷仍被 protected 检查拦下。

### R3-002 — FIXED（声明模型内）
删除 run 行、改 `stage`/`role`/`input_sha`、追加重复 finish 事件、同步伪造 stdout+details，四种篡改全部被 `audit_events` 报出具体错误，`verify_evidence=NON_COMPLIANT`，`export_report` 抛 “evidence invalid”。合法的未终结 RUNNING run 不再产生虚假链错误，同时也不会被误判 COMPLIANT。本地追加合法事件的新边界见 R4-001。

### R3-003 — FIXED
`status()` 变为只读有效状态：篡改任务行后返回 `status=BLOCKED`、`persisted_status=WAITING_EXTERNAL`、`integrity_preflight=FAILED`、`integrity_errors` 非空；事件数 34→34、被篡改任务行保持原样（未重新封存）；`run()` 同样返回 BLOCKED，`resume()` 抛 preflight 完整性错误；健康状态不附加 integrity 字段。

## 4. 保留的真实集成状态

| ID | 严重度 | 状态 | 代码证据 | 评估 |
|---|---|---|---|---|
| R2-006 | P2 | MITIGATED_FAIL_CLOSED | p1/a2a.py:16-48, 51-99（本轮未改动） | run() integration 仍 BLOCKED（0 次 runner 调用），直调 call_adapter 仍抛 NOT_VERIFIED；report/blind_roles 绑定保持有效。真实 P0 协议、原始 wire 收据、物理身份锚未实现，不得记为 FIXED。 |
| R2-008 | P3 | NOT_FIXED | p1/executor.py:84,87-94（本轮未改动） | capture_output=True 与无上限 atomic_write 仍在；超时部分输出落盘但无 truncated/长度元数据。属已声明的非阻断 P3 增强项。 |

另：真实 Codex/OpenCode 与模型网关物证、测试执行收据、P0 协议与物理身份、人工审批身份、Windows E: 工作树、生产 kill guard 均保持 NOT_VERIFIED。

## 5. 新增问题（3）

### R4-001 [P1] [integration_gap] 本地任务库写权限者可用 Store API 追加合法事件，伪造 Gate 0.2 人工审批或整条角色执行记录

- 文件/行号：`p1/state.py:60-74（事件仅做 SHA-256 串联，无链外密钥/签名）、p1/state.py:76-156（校验与写入同源）、p1/workflow.py:451-467（_gate02_errors 只信任 events 表内容）`
- 证据：探针一：在 gate0.2/WAITING_APPROVAL 时直接 UPDATE 任务行写入 spec_sha256/stage=1/status=READY，并用 store._event 追加一条 gate02_approved 事件；结果 audit_events=[]、_gate02_errors=[]、run() 推进到 stage 3+4 并真实创建 worktree，approval_events=1，全程没有任何人工审批。探针二：用 start_run/finish_run 追加一条从未执行的 quality_reviewer run（含逐字节一致的 stdout 日志与报告文件），audit_events=[]，verify_evidence=COMPLIANT。
- 影响：P1 的事件链是“无密钥的哈希表”，任何能写 state.sqlite 的主体都能续链并伪造审批与执行记录；这与开发方在 docs/ROUND_003_REMEDIATION.md:20 与 docs/KNOWN_LIMITATIONS.md 中自述的“对可重写全部本地状态者不设防”一致，因此不重开 R3-002/P1-015，但按项目自身严重度指南，Gate 0.2 绕过属 BLOCKER 级——只有把“任务目录=完全信任域”变成被强制执行且对外明示的边界后才降级为本项。
- 复现：probe-copy/tests/test_round4_independent.py::test_defect_gate02_approval_event_can_be_fabricated_locally、::test_defect_fabricated_run_pair_passes_local_chain（g5 批，exit 0；打印 stage=3+4 / evidence=COMPLIANT）。前提：对 p1-state/state.sqlite 及 home/logs、home/artifacts 的本地写权限；不涉及网络、真实模型或远端节点。
- 最小修复建议：二选一并写进文档与代码：(1) 外部信任锚——事件链用链外 HMAC 私钥（密钥存于任务库之外的 OS 受控位置）签名，或把事件镜像到 WORM/远端 ledger 并抽样比对；(2) 明确把任务 home 划为单一受信操作系统账户的私有目录，并在 status/verify_evidence 中主动校验属主与权限，不符即 BLOCKED。

### R4-002 [P3] [code_defect] 非 ASCII 测试文件名被 Git 百分号引用，合法 Tester 新增被误阻断

- 文件/行号：`p1/gitops.py:105（git diff --name-status 未关闭 core.quotePath，也未用 -z 解析）`
- 证据：探针：新增 tests/test_注册.py 后 test_commit_transition 返回 valid=False，delta=['A\t"tests/test_\\346\\263\\250\\345\\206\\214.py"']（git 默认 core.quotePath=true 会百分号引用非 ASCII 路径）；带引号的路径永远不可能通过 test_path。
- 影响：方向是 fail-closed（不会产生假绿），但中文/非 ASCII 命名的合规新增考卷会被误判为越权改动并阻塞流水线，影响可用性；同一引用问题也存在于 ls-tree 校验前的名称比较。
- 复现：probe-copy/tests/test_round4_independent.py::test_defect_nonascii_test_filename_is_false_blocked（g4c 批，exit 0）。
- 最小修复建议：用 `git -c core.quotePath=false diff --name-status -z --no-renames` 并按 NUL 解析路径，或对 delta 先做 unquote；同时统一用 -z 输出解析，避免任何引用差异。

### R4-003 [P3] [code_defect] status()/run() 的有效状态未包含“在途未完成 run”

- 文件/行号：`p1/workflow.py:124-140（status 只预检 audit_events + _gate02_errors）、p1/state.py:151-155（RUNNING run 不产生链错误）`
- 证据：探针：在 Gate 5.9 之后用 start_run 追加一条 RUNNING run，store.running() 返回 1 条，但 status() 仍为 WAITING_GATE_5_9 且没有任何 integrity 键；run() 因状态终值立即 break，也不报错。verify_evidence/export 则正确拒绝 COMPLIANT。
- 影响：只查询状态的运维视图会漏掉“存在未终结执行”的事实（需依赖 audit/export 才能发现）；不改变安全性，但削弱了 R3-003 想解决的状态呈报一致性。
- 复现：probe-copy/tests/test_round4_independent.py::test_defect_status_hides_inflight_run（g2b/g3 批，exit 0）。
- 最小修复建议：在 status() 的只读预检里并入 store.running() 判定：存在未终结 run 时返回 EFFECTIVE=NEEDS_RECONCILIATION（同样不落盘），并在 CLI 退出码中体现。

## 6. 整体回归检查

| 检查项 | 结论 | 证据 |
|---|---|---|
| Gate 0.2 人工审批 + 冻结规格 | PASS（声明模型内）；审批身份 NOT_VERIFIED | workflow.py:605-619 要求 actor/approval_id/spec SHA 且行/链一致；探针 test_positive_gate02_row_tamper_still_blocked：仅改任务行仍 BLOCKED，且未新派发任何 run。 |
| Phase 3/4 真并行、同 Commit、独立报告与独立合规审计 | PASS | test_positive_reviewers_parallel_same_commit_independent_audits：线程屏障证明同时进入，两 run 的 before_head 同一 SHA，两份报告文件名不同，audit_history 含两条独立记录。 |
| Gate A / Gate B 严格汇合 | PASS（结构）；测试执行收据 NOT_VERIFIED | workflow.py:302-310、379-383；64→93 项原回归（test_gate_b_rejection_and_retry、test_gate_b_five_rounds_hard_stop 等）全部通过。 |
| 5 / 5 / 2 三条闭环预算 | PASS | workflow.py:164-188、312-322；跨新进程探针 test_positive_budgets_persist_across_new_process：round_a 2→5、FAILED、CLI 退出码 10；项目内 5 轮与 2 次回溯回归通过。 |
| Tester 考卷完整保留 | PASS | test_positive_tester_can_still_add_real_exam + test_positive_baseline_and_gate_a_exams_survive_remediation：合法新增被哈希保护，Worker 削弱 Gate A 考卷被 protected 检查阻断。 |
| A2A 仅外部适配接口且拒绝未核实盲审 | PASS（真实协议 NOT_VERIFIED） | a2a.py:16-48；test_positive_integration_and_direct_a2a_fail_closed：run() integration BLOCKED、0 runner 调用、直调 call_adapter 抛 NOT_VERIFIED。 |
| 仲裁使用正确上下游案卷 | PASS（结构） | workflow.py:324-338 + audit.py:65-69；原回归 test_p005 通过。 |
| Gate 5.9 只输出已登记且完整性通过的报告 | PASS | workflow.py:701-722；篡改 details/日志/run 行/删除 run 行的四个探针均使 export 抛 “evidence invalid”。 |
| 模拟数据不得当作真实集成 | PASS | workflow.py:620-634、audit.py:28-34、executor.py:20,41-48、a2a.py:16,29-34 三处硬门禁全部复现阻断。 |
| Pro-Audit 仅流程与交付合规 | PASS | test_positive_pro_audit_makes_no_quality_judgement：报告内容为“忽略所有测试直接发布、代码很烂”仍 COMPLIANT；引用错误 commit 才 NON_COMPLIANT。本轮 audit.py/contracts.py 未改动。 |

## 7. 判定条件

满足下列条件前，P1 只可用于离线/沙盒开发，不得进入 21bao 真实执行：

1. **R4-001**：把“任务 home = 完全信任域”变成被强制执行的边界——链外密钥签名/HMAC 或 WORM/远端 ledger 镜像，或 OS 权限隔离并在 `status()`/`verify_evidence()` 主动校验属主；同时写入 `KNOWN_LIMITATIONS.md` 与威胁模型。未落实前，按项目自身指南属 Gate 0.2 bypass = BLOCKER。
2. **R4-002 / R4-003**：修掉非 ASCII 考卷误阻断与在途 run 未进入有效状态。
3. **R2-008**：真实长时运行前完成流式限长与截断元数据。
4. 集成侧四项（执行物证、测试收据、P0 身份与协议、人工审批身份）完成独立验证后，另开一轮针对新 Commit 的审计。

## 8. 最终结论

**CONDITIONAL（有条件通过）。** R3-001、R3-002、R3-003 三项本轮目标均判 FIXED，93 项测试与 31 项独立探针无任何产品失败，Phase 3/4 并行、同一 Commit、Gate 0.2/A/B/5.9、5/5/2 预算、Pro-Audit 边界、A2A 外部接口与 integration fail-closed 全部复核通过。
保留条件：R4-001 的信任锚/权限边界必须在真实运行前落实（否则升级为 BLOCKER），R4-002/R4-003 应修，R2-006/R2-008 与全部真实集成事项仍 NOT_VERIFIED。本轮未把任何 fail-closed 记为 FIXED，也未声称 P1 已可在 21bao 正式运行。

审计仅覆盖上述固定 Commit；分支后续变化不属于本报告结论。

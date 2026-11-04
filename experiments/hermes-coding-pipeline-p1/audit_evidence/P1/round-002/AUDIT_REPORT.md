# P1 Coding Pipeline — Round-002 独立审计报告

**AUDIT_STATUS: COMPLETE**　　**代码结论: FAIL**　　**真实 21bao 集成: 不允许**

- 审计源码 Commit: `7ef210a90bc3cd8ec3d230d1901f0fbd7715015c`（父提交 `a72e13a987ca490ec73c9c9456741c0bd4e8df39`，tree `8681a8bbd430984744f56e0a38448361d1ba7d59`）
- 分支: `feature/p1-coding-pipeline-20261104`；目录: `experiments/hermes-coding-pipeline-p1/`
- 审计时间: 2026-11-04T16:20:39+08:00 → 2026-11-04T17:05:00+08:00（UTC+08:00）
- 审计方式: 只读源码 + 隔离目录离线测试；未连接真实 P0、远端 A2A、付费模型或现网配置。
- 本报告不修改任何 P1 源码、Soul、测试或 Round-001 报告。

## 1. 结论摘要

Round-001 的 29 项问题中：**FIXED 15 项、MITIGATED_FAIL_CLOSED 7 项、NOT_FIXED 6 项、REGRESSION 1 项、NOT_VERIFIED 0 项**。本轮另发现 **12 项新问题**：P0 0、P1 4、P2 3、P3 5。

整改质量较 Round-001 明显提升：Gate 0.1 竞态、Gate 0.2 row-only 绕过入口、双审记录、预算持久化、终态 A2A、超时部分输出、Gate 5.9 导出等已实质修复。但仍有 **4 个 P1 级新缺陷**与 6 个未修复项，其中 Tester 考卷可被测试角色自行删除/弱化、resume 重新封存篡改状态、运行记录未绑定事件链，都会让流水线在“证据完整性”层面给出错误合规结论；P1-022 的整改还引入了合法 no-op 被误杀并耗尽预算的回归。因此本轮不能给出 PASS。

## 2. 审计方法与证据边界

- 通过 GitHub tree/blob API 固定 45 个文件，逐一以 Git blob SHA-1 复核；审计前后均为 **45/45 匹配，0 错误**。审计期间分支 HEAD 始终为上述 Commit，远端 `audit_evidence/P1/` 仅存在 `README.md` 与 `round-001/`。
- 原项目测试在固定快照上原样运行：**47/47 passed，0 failures，0 errors**，分 6 批，JUnit 见 `testlogs/batch0..5.xml`。未做夹具改动。
- 独立对抗探针位于隔离副本 `probe-copy/`：**19 个不重复用例 / 21 次执行，全部 exit 0**。探针断言的是“缺陷被复现”，不是“产品通过”。
- 两个辅助子代理的复核请求被 provider 内容审查拒绝；其覆盖范围已由主审计用源码阅读与上述探针重新完成。另一个已完成子代理的结论仅作为线索，实质结论均由主审计重新核对代码与测试后写入，未把未复现的声明当作证据。
- 所有 SQLite 篡改类探针均以“本地 state.sqlite 可写”为前提；Git 索引标志探针只作用于一次性 worktree；未使用真实模型、P0 或远端节点。

## 3. Round-001 29 项逐项复核

| ID | 原严重度 | 本轮状态 | 代码证据（文件:行） | 离线验证 |
|---|---|---|---|---|
| P1-001 | P0 | MITIGATED_FAIL_CLOSED | p1/a2a.py:42-45, 73-79 | test_integration_entry_and_a2a_identity_fail_closed |
| P1-002 | P0 | FIXED | p1/workflow.py:409-411, 323-324 | test_p002_a2a_question_stops_pipeline[QUESTION/NEEDS_SPECIALIST] |
| P1-003 | P0 | MITIGATED_FAIL_CLOSED | p1/workflow.py:583-587; p1/executor.py:41-48 | test_p003_and_021_integration_never_trusts_stub; test_integration_entry_and_a2a_identity_fail_closed |
| P1-004 | P0 | NOT_FIXED | p1/gitops.py:21-22; p1/workflow.py:171-172, 190-195 | test_git_index_flags_hide_dirty_worker_from_gate[--assume-unchanged/--skip-worktree] |
| P1-005 | P0 | MITIGATED_FAIL_CLOSED | p1/workflow.py:298-312; p1/audit.py:60-64 | test_p005_arbitrator_case_is_fixed_and_registered |
| P1-006 | P1 | NOT_FIXED | p1/workflow.py:193-205; p1/audit.py:43-48 | test_gate_b_tester_can_weaken_gate_a_protected_exam; test_tester_can_change_or_delete_existing_exam[weaken/delete] |
| P1-007 | P0 | FIXED | p1/workflow.py:643-663, 440-447 | test_p007_rogue_final_report_is_not_exported; test_p007_and_016_tampered_report_or_stdout_blocks_export |
| P1-008 | P1 | FIXED | p1/workflow.py:499-518 | test_p008_old_final_audit_does_not_poison_recomputed_final |
| P1-009 | P1 | FIXED | p1/workflow.py:65-68, 363-366 | test_p009_planner_and_worktree_must_share_base_commit |
| P1-010 | P1 | MITIGATED_FAIL_CLOSED | p1/contracts.py:83-86; p1/workflow.py:583-587 | test_p010_local_roles_cannot_run_on_debian_node |
| P1-011 | P1 | FIXED | p1/contracts.py:135-147 | test_p011_blank_soul_contract_is_rejected |
| P1-012 | P2 | FIXED | p1/workflow.py:249-275 | test_p012_both_parallel_audit_records_survive_first_violation; test_reviewers_overlap_and_keep_both_audits |
| P1-013 | P2 | FIXED | p1/cli.py:59-63 | test_p013_failed_run_nonzero_cli_exit; test_budgets_persist_across_new_process |
| P1-014 | P0 | FIXED | p1/contracts.py:115-164; p1/workflow.py:557-573 | test_p014_gate01_snapshot_cannot_race_copy |
| P1-015 | P0 | NOT_FIXED | p1/state.py:68-99; p1/workflow.py:575-582, 627-635 | test_p015_task_row_edit_cannot_skip_gate02; test_resume_reseals_tampered_state_before_integrity_check |
| P1-016 | P1 | NOT_FIXED | p1/workflow.py:448-471; p1/state.py:101-110 | test_p007_and_016_tampered_report_or_stdout_blocks_export; test_unbound_run_metadata_can_rewrite_log_and_pass |
| P1-017 | P1 | NOT_FIXED | p1/gitops.py:25-30 | test_p017_index_only_modification_detected; test_git_index_flags_hide_dirty_worker_from_gate |
| P1-018 | P1 | FIXED | p1/gitops.py:37-46; p1/workflow.py:196-201, 319-322 | test_p018_tester_cannot_replace_git_head_with_divergent_commit; test_valid_tester_addition_updates_downstream_commit |
| P1-019 | P1 | NOT_FIXED | p1/workflow.py:140-162, 167-170, 336-343 | test_p019_moved_worktree_head_requires_reconciliation; test_replay_worker_after_real_remediation_commit_uses_wrong_base |
| P1-020 | P1 | FIXED | p1/workflow.py:276-281 | test_p020_unresolved_question_wins_over_top_level_approve |
| P1-021 | P0 | MITIGATED_FAIL_CLOSED | p1/executor.py:18-20, 41-48; p1/audit.py:28-34; p1/workflow.py:583-587 | test_p003_and_021_integration_never_trusts_stub |
| P1-022 | P1 | REGRESSION | p1/audit.py:49-52; p1/workflow.py:338-341 | test_valid_no_op_reason_is_misclassified |
| P1-023 | P2 | FIXED | p1/contracts.py:95-103; p1/a2a.py:57-67 | test_p023_duplicate_blind_candidates_rejected |
| P1-024 | P2 | FIXED | p1/workflow.py:389-392 | test_p024_terminal_a2a_failed_is_terminal |
| P1-025 | P2 | FIXED | p1/executor.py:79-88 | test_p025_timeout_keeps_partial_stdout_stderr |
| P1-026 | P2 | FIXED | p1/contracts.py:135-158; p1/workflow.py:72-100 | test_p026_failed_init_does_not_poison_retries |
| P1-027 | P1 | FIXED | p1/workflow.py:575-582, 597-599 | test_p027_corrupt_event_journal_stops_before_dispatch |
| P1-028 | P1 | MITIGATED_FAIL_CLOSED | p1/workflow.py:39-41, 69-85; p1/executor.py:49; p1/a2a.py:24-29 | test_p028_external_adapter_config_cannot_mutate_snapshot |
| P1-029 | P2 | MITIGATED_FAIL_CLOSED | p1/workflow.py:373-377; p1/a2a.py:46-54 | test_p029_a2a_submit_includes_approved_spec_and_souls |

### 3.1 未修复 / 回归项详情（6 NOT_FIXED + 1 REGRESSION）

**P1-004（P0 / NOT_FIXED）** Worker 未提交的改动可连同旧 HEAD 被送审并通过整条离线流程。
- 证据：`p1/gitops.py:21-22; p1/workflow.py:171-172, 190-195`；验证：`test_git_index_flags_hide_dirty_worker_from_gate[--assume-unchanged/--skip-worktree]`。
- 复核结论：普通脏文件被拦，但 Git 索引标记可让 status 显示干净、索引摘要不变；实际工作树内容与 HEAD 不同，最终仍 WAITING_GATE_5_9 + COMPLIANT。
- 最小修复：派发前用 `git ls-files -v` 检查 assume-unchanged/skip-worktree 标志，并对工作树逐文件哈希（或 `git diff --no-index` 对照 HEAD）；存在标志或内容差异即阻断。

**P1-006（P1 / NOT_FIXED）** 整改 Worker 可以削弱 Tester A 考卷，系统未阻断。
- 证据：`p1/workflow.py:193-205; p1/audit.py:43-48`；验证：`test_gate_b_tester_can_weaken_gate_a_protected_exam; test_tester_can_change_or_delete_existing_exam[weaken/delete]`。
- 复核结论：Worker 路径已检查 protected_tests；Tester B 不受该检查约束，且 Gate A 快照晚于本阶段提交，基线测试可被删除。
- 最小修复：见 R2-001。

**P1-015（P0 / NOT_FIXED）** 具备本地任务数据库写权限时，仅修改状态行即可绕过 Gate 0.2，事件链仍显示有效。
- 证据：`p1/state.py:68-99; p1/workflow.py:575-582, 627-635`；验证：`test_p015_task_row_edit_cannot_skip_gate02; test_resume_reseals_tampered_state_before_integrity_check`。
- 复核结论：run() 能拦截 row-only 篡改；resume() 在校验前把 WAITING_EXTERNAL 写回 READY，重新封存篡改行，随后用伪造 job id 轮询。
- 最小修复：resume 先只读校验事件链与 Gate 0.2，再允许状态迁移；见 R2-002。

**P1-016（P1 / NOT_FIXED）** 原始角色 stdout 被改写后，证据核验仍报告 COMPLIANT。
- 证据：`p1/workflow.py:448-471; p1/state.py:101-110`；验证：`test_p007_and_016_tampered_report_or_stdout_blocks_export; test_unbound_run_metadata_can_rewrite_log_and_pass`。
- 复核结论：单改日志会被发现；同时改写 runs.details 的两个摘要与 stdout 后，事件链无错误、verify_evidence=COMPLIANT。
- 最小修复：把 runs.details 摘要写入事件链并在核验时重算；见 R2-003。

**P1-017（P1 / NOT_FIXED）** 只读角色的 Git 暂存区内容更改可漏过清单与权限审计。
- 证据：`p1/gitops.py:25-30`；验证：`test_p017_index_only_modification_detected; test_git_index_flags_hide_dirty_worker_from_gate`。
- 复核结论：普通 staged blob 变化可检出；索引标志与工作树内容不在摘要范围内。
- 最小修复：使用 `git ls-files --debug`/`git diff --no-index` 或直接哈希工作树并校验标志位；见 P1-004。

**P1-019（P1 / NOT_FIXED）** 跨改码阶段的合规回溯可在不同源码基线上重新派发 Worker。
- 证据：`p1/workflow.py:140-162, 167-170, 336-343`；验证：`test_p019_moved_worktree_head_requires_reconciliation; test_replay_worker_after_real_remediation_commit_uses_wrong_base`。
- 复核结论：整改提交后 task.commit_sha 已推进；回溯 stage 2 时只与“当前”commit 比较，Worker 在整改后的基线上重跑，原“不同基线”问题仍存在。
- 最小修复：为每个可改码阶段持久化“派发时输入 commit”，回溯时要求 HEAD 等于该历史 commit，否则 NEEDS_RECONCILIATION。

**P1-022（P1 / REGRESSION）** Worker 与整改 Worker 不提供任何报告，仅返回 PASS 也能继续。
- 证据：`p1/audit.py:49-52; p1/workflow.py:338-341`；验证：`test_valid_no_op_reason_is_misclassified`。
- 复核结论：报告必填已生效；但新增的 no-op 关键词判定把合法理由判为无理由，重试两次后 FAILED 并耗尽全局合规预算。
- 最小修复：删除子串匹配，改为结构化 no-op 证据；见 R2-004。

### 3.2 已修复项（15）

P1-002、P1-007、P1-008、P1-009、P1-011、P1-012、P1-013、P1-014、P1-018、P1-020、P1-023、P1-024、P1-025、P1-026、P1-027 均有对应原回归与本轮独立验证；其中 P1-014 的人工审批身份、P1-011 的 Soul 语义绑定仍分别列入第 8 节未验证事项与 R2-005，不因“代码路径修复”而宣称真实审批可信。

### 3.3 阻断但不完整（7 MITIGATED_FAIL_CLOSED）

P1-001、P1-003、P1-005、P1-010、P1-021、P1-028、P1-029 的共同边界是：真实 Harness/模型凭据、测试执行收据、P0 协议/物理身份、可执行文件身份尚未接入。代码通过 `workflow.py:583-587`、`executor.py:47-48`、`audit.py:28-34` 的硬阻断避免“假绿”，但这属于正确 fail-closed，不是完整实现，也不能作为 21bao 可运行的证据。

## 4. 新增问题（12）

### R2-001 [P1] [code_defect] Tester 考卷完整性只在 Worker 路径校验，且 Gate A 保护快照晚于本阶段提交

- 文件/行号：`p1/workflow.py:190-205; p1/audit.py:43-48; p1/gitops.py:37-46`
- 证据：独立探针：Gate A Tester 删除/弱化基线 test_main.py 并提交后，流程仍 WAITING_GATE_5_9 + COMPLIANT；Gate B Tester 把 Gate A 受保护考卷从 73c4f17… 改为 e32287f…，protected_tests 记录的仍是旧哈希，最终仍 COMPLIANT。
- 影响：测试角色可自行删除或弱化考卷，Gate A/B 的“测试证据”可被伪造为全绿，Gate 5.9 案卷仍显示合规。
- 复现：probe-copy/tests/test_round2_independent.py::test_tester_can_change_or_delete_existing_exam[weaken|delete]、::test_gate_b_tester_can_weaken_gate_a_protected_exam（独立 1/5 批，均复现）。
- 最小修复建议：Tester 提交只允许“新增 test 文件”；对既有 test 文件比较 before/after 内容，出现修改/删除即阻断。Gate A 结束后同时记录 before∩after 的基线考卷哈希；Gate B 与最终审计再次比对 protected_tests。

### R2-002 [P1] [code_defect] resume() 在完整性校验前重新封存被篡改的任务行，并使用伪造 job id

- 文件/行号：`p1/workflow.py:627-635; p1/state.py:53-58, 60-74`
- 证据：独立探针：把 5.0 任务行 a2a_job_id 改为 TAMPERED-LOCAL-JOB 后，audit_events 报 1 个错误；resume() 先 _save(READY) 生成新事件使错误归零，随后 status 依次查询 ORIGINAL-LOCAL-JOB 与 TAMPERED-LOCAL-JOB。
- 影响：有本地 DB 写权限者可清除“任务行被改”的证据，让流水线轮询攻击者指定的外部 job，最终按该 job 的结果继续。
- 复现：probe-copy/tests/test_round2_independent.py::test_resume_reseals_tampered_state_before_integrity_check（独立 5 批）。前提：本地 state.sqlite 写权限；不涉及远端调用。
- 最小修复建议：resume() 先执行 audit_events()/._gate02_errors()，任何错误直接 BLOCKED；校验通过后才允许状态迁移，且不要在预检前写任务行。

### R2-003 [P1] [code_defect] runs 记录未绑定事件链，改写 details 与原始日志后仍 COMPLIANT

- 文件/行号：`p1/workflow.py:448-471; p1/state.py:101-110`
- 证据：独立探针：到达 Gate 5.9 后改写某 run 的 stdout 文件，并同步修改 runs.details 中 logs/invocation 的 SHA；不改任务行、payload 或 output_sha。audit_events=[]，verify_evidence=COMPLIANT。
- 影响：本地执行证据可被整体替换而最终核验与导出仍通过；事件链只绑定 run_id/status/output_sha，不绑定 details/日志。
- 复现：probe-copy/tests/test_round2_independent.py::test_unbound_run_metadata_can_rewrite_log_and_pass（独立 2 批）。前提：本地 DB 与日志写权限。
- 最小修复建议：finish_run 事件写入 details 的 SHA（或整个 details 摘要），verify_evidence 重算并比对；日志摘要同时绑定到事件。

### R2-004 [P1] [code_defect] no-op 整改理由用关键词子串判定：合法理由被误杀并耗尽合规预算

- 文件/行号：`p1/workflow.py:338-341`
- 证据：独立探针：整改报告写 “All reported issues were already resolved in the reviewed revision.”（无新提交）被判为 “no-op remediation needs explicit reason”，compliance_retraces 从 1 增至 2 后 FAILED；反之，任何含 “no p0/no-op/no defect/无缺陷/无需整改” 的文本均可通过。
- 影响：合法的“已全部修复”场景被错误终止并消耗全局合规回溯预算；关键词也可被无实质证据的文本满足，不能证明无缺陷。
- 复现：probe-copy/tests/test_round2_independent.py::test_valid_no_op_reason_is_misclassified（独立 2 批）。
- 最小修复建议：改为结构化字段：no_op=true + 逐条缺陷已修复证据 + Reviewer/Arbitrator 复核；由 Pro-Audit 依据 diff 与缺陷清单判定，禁止子串匹配。

### R2-005 [P2] [code_defect] Gate 0.1 审批未绑定 12 份 Soul 内容，init 只做形状校验

- 文件/行号：`p1/contracts.py:106-112, 135-147; p1/workflow.py:48-95`
- 证据：独立探针：用同文件名但不同内容的 planner.md 替换 souls 目录，init 接受并原样冻结（saved==text），无需改 gate01.json。
- 影响：角色 Soul 是行为契约，却不在 Gate 0.1 审批摘要中；可在审批后替换为任意满足标题/长度要求的文本。
- 复现：probe-copy/tests/test_round2_independent.py::test_semantically_unapproved_soul_passes_shape_check（独立 3 批）。
- 最小修复建议：gate01.json 增加 souls 清单摘要（逐角色 SHA）；validate_approval 校验该摘要；或把 souls 目录哈希纳入 Gate 0.1 输入。

### R2-006 [P2] [integration_gap] A2A 原始传输证据未保存，返回绑定只校验部分字段

- 文件/行号：`p1/a2a.py:29-37, 49-54, 70-72; p1/workflow.py:398-408`
- 证据：静态证据：adapter stdout 解析后丢弃原始字节，05_0_blind_review.json 写的是重新 canonical 化的对象；report 内容只做真值判断（dict/list 也可通过）；返回的 blind_roles 未与请求比对。
- 影响：真实 P0 接入后无法证明远端报告原文与角色映射；报告类型异常可通过形状检查。integration 当前阻断，故未形成真实放行。
- 复现：代码审查 + probe-copy/tests/test_round2_independent.py::test_integration_entry_and_a2a_identity_fail_closed（验证缺失 souls_sha256 被拒）。
- 最小修复建议：保存 adapter 原始 stdout/stderr 与 SHA；要求 report 为 str；校验 blind_roles 与请求逐项一致、报告节点/角色一一对应。

### R2-007 [P2] [code_defect] 冻结 adapter 校验路径与实际执行读取路径可分离

- 文件/行号：`p1/workflow.py:39-41, 69-85; p1/executor.py:49; p1/a2a.py:24-29`
- 证据：静态证据：require_snapshot 校验 snapshots/adapters.json 的 SHA，但 invoke()/call_adapter() 读取 task["adapter_config"]。将任务行指向另一本地配置时冻结检查仍通过。
- 影响：获得本地 DB 写权限且 integration 启用后，可绕过 P1-028 的冻结配置保护。当前 integration 被硬阻断，故不可实际触发真实执行。
- 复现：静态路径对照；无需运行真实 adapter。
- 最小修复建议：执行入口固定读取 snapshots/adapters.json 并复核 SHA；或断言 task["adapter_config"] 等于该快照路径。

### R2-008 [P3] [hardening] 超时与正常路径的 stdout/stderr 无大小上限或截断元数据

- 文件/行号：`p1/executor.py:79-90`
- 证据：静态证据：subprocess.run(capture_output=True) 与 atomic_write 均无上限；超时元数据只含 SHA，不含原始大小/截断标志。
- 影响：异常大的子进程输出可耗尽内存/磁盘，影响可恢复性；不影响当前合规判定。
- 复现：代码审查（未注入超大输出）。
- 最小修复建议：流式读取并设上限，保存 truncated 标志与原始长度。

### R2-009 [P3] [hardening] A2A 终态诊断字段被丢弃，仅保存状态字符串

- 文件/行号：`p1/workflow.py:389-392`
- 证据：静态证据：status 响应只取 state；FAILED/CANCELLED 的 diagnosis/error 字段未写入事件或 artifacts。
- 影响：故障定位信息丢失，运维只能看到终态。
- 复现：代码审查。
- 最小修复建议：将脱敏后的终态响应写入事件或 artifacts，并计算 SHA。

### R2-010 [P3] [hardening] safety.json 未在初始化时解析，坏 JSON 直到 Phase 1 才阻断

- 文件/行号：`p1/workflow.py:69-77, 356-360`
- 证据：静态证据：init 仅复制字节；_phase_worktree 才 read_json。坏 JSON 会使任务先 READY，后在 stage 1 转 NEEDS_RECONCILIATION。
- 影响：初始化成功但不可避免地在下一阶段失败，增加无效状态。
- 复现：代码审查。
- 最小修复建议：init 时解析并校验 live_side_effects_disabled/reviewed_by，失败即拒绝初始化。

### R2-011 [P3] [hardening] 初始化在 state.sqlite 创建后失败会留下半成品，重试被拒

- 文件/行号：`p1/workflow.py:92-100; p1/state.py:16-37`
- 证据：独立探针：注入 Store 创建 DB 后抛 OSError；snapshots 与 state.sqlite 均残留，再次 init 报 already initialized。
- 影响：罕见 I/O 故障后任务目录不可重试，需要人工清理。
- 复现：probe-copy/tests/test_round2_independent.py::test_io_failure_after_sqlite_creation_poison_initialization（独立 3 批）。
- 最小修复建议：先把快照发布到临时目录，DB 成功后再原子发布；或失败时仅删除本次创建的 DB 与快照。

### R2-012 [P3] [hardening] call_adapter 的 integration 分支缺少与 executor 同级的本地硬门禁

- 文件/行号：`p1/a2a.py:14-29; p1/executor.py:18-20, 41-48`
- 证据：独立探针：直接调用 call_adapter(mode=integration) 会启动本地 adapter 子进程并返回 LOCAL-STUB；Pipeline.run() 的正常 integration 阻断不受影响，CLI 也未暴露该入口。
- 影响：库级调用可绕过“integration 一律阻断”的约定；当前不可由 CLI 触发，属纵深防御缺口。
- 复现：probe-copy/tests/test_round2_independent.py::test_direct_a2a_adapter_integration_not_locally_locked（独立 9 批）。
- 最小修复建议：在 call_adapter 增加与 executor 相同的 TRUSTED 门禁或 mode 断言。

> 严重度说明：P1 = 会使流水线产生错误合规结论或中断合法流程；P2 = 需特定前提（本地 DB 写权限/未来启用 integration）才能触发，或属真实集成契约缺口；P3 = 可恢复性/纵深防御/运维可用性优化，不阻断当前验收。

## 5. 关键流程规则复核

| # | 检查项 | 结论 | 证据 |
|---|---|---|---|
| 1 | Gate 0.2 是否要求有效人工审批与冻结规格 | 结构合规；身份 NOT_VERIFIED | `workflow.py:557-573` 要求 actor/approval_id/spec SHA，`contracts.py:115-164` 原子冻结；但 actor 只是字符串，未接入真实身份认证。 |
| 2 | Phase 3/4 是否真正并行、同一 Commit、独立报告与独立合规记录 | PASS | `workflow.py:249-275` ThreadPoolExecutor；屏障探针证明两角色同时进入，输入 SHA 相同，`audit_history` 含两条独立记录；分叉/脏树阻断。 |
| 3 | Gate A 是否严格核对双审与 Tester 结果 | 结构 PASS；测试真实性 NOT_VERIFIED | 双审均 PASS 才进入 4.5（`workflow.py:282-284`）；Tester 要求 GATE_A_PASS/PASS（610）。但 integration 被阻断，无法证明真实测试执行。 |
| 4 | 5 轮/5 轮/2 次预算与持久化 | PASS | `_retry_a` 5（287-290）、`_retry_b` 5（292-296）、`_violation` 2（142-144）；跨新进程探针：A 2→5、B 2→5、合规 1→2，均 FAILED 且 CLI exit 10。 |
| 5 | Tester 考卷在整改过程中保持完整 | **FAIL** | Gate B 可改写 Gate A 受保护考卷；Gate A 可删除既有基线测试；最终仍 COMPLIANT（R2-001）。 |
| 6 | A2A 是否只通过外部接口、拒绝未核实盲审 | 流程 PASS；库级缺口 P3 | 仅 `_phase_a2a` 使用 adapter；`validate_collection` 拒绝伪造身份并在 integration 无条件 NOT_VERIFIED；CLI 未暴露直调；`call_adapter` 库级缺门禁（R2-012）。 |
| 7 | 仲裁是否使用正确上下游案卷 | 结构 PASS；读取未验证 | `workflow.py:298-312` 冻结 task/commit/spec/matrix/evidence 哈希；`audit.py:60-64` 要求 case SHA；无法证明模型实际读取。 |
| 8 | Gate 5.9 是否只输出已登记且完整性通过的报告 | PASS | `export_report` 只读仲裁与最终报告两个登记名，逐字节核对 SHA（643-663）；未登记/改写被拒（P1-007 探针）。 |
| 9 | 模拟数据是否可能被当作真实集成 | PASS（正常入口） | `run()` integration 直接 BLOCKED（583-587）；`audit.py:28-34` 拒绝 fixture/simulated；未发现 CLI 可绕路径。库级 `call_adapter` 缺口见 R2-012。 |
| 10 | 中断恢复、Git 版本与事件记录一致性 | **FAIL** | resume 先写后查（R2-002）、runs 未绑定事件（R2-003）、索引标志隐藏改动（P1-004/017）、跨阶段回溯基线漂移（P1-019）。 |

## 6. Pro-Audit 边界

未发现越权技术裁决。`p1/audit.py:12-15` 明确只检查角色/矩阵/输出形状/权限/Commit/规格 SHA，不评价实现正确性、风格或安全方案；`workflow.py` 的合规判定也只做阶段顺序、预算与证据完整性。R2-004 的关键词判定属于工作流的业务逻辑缺陷，不是 Pro-Audit 在裁决技术方案。

## 7. 真实执行与离线模拟的区分

- 本轮所有 47 个项目测试与 19 个探针均为离线 fixture / 本地 Git / 本地 stub；没有真实 Codex/OpenCode、真实模型、付费调用、真实 P0 或远端节点。
- `integration` 模式在 `run()` 与 `invoke()` 均被硬阻断；报告的 “COMPLIANT” 只代表离线流程内部一致性，不代表真实执行可信。
- 因此本报告不声称 P1 已可在 21bao 正式运行；真实集成事项全部列为 NOT_VERIFIED。

## 8. 仍未验证的真实集成事项

- 真实 Codex/OpenCode 包装器、模型与网关物证
- 真实 P0 协议、返回角色绑定与报告原文
- P0 物理身份认证与防伪 Quorum
- 真实测试执行收据（Gate A/B）
- 真实人工 Gate 0.1/0.2/5.9 身份与审批链
- Windows E: 集成工作树与真实崩溃/子进程行为
- 真实副作用 kill guard / 生产隔离

## 9. 最终结论

**FAIL。** 本轮不批准 P1 进入 21bao 真实运行，也不把 fail-closed 阻断解释为完成。开发方应先修复 R2-001～R2-004 与 6 个 NOT_FIXED 项，再针对新 Commit 开展 Round-003 独立复审。

审计仅覆盖上述固定 Commit；分支后续变化不属于本报告结论。

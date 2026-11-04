# P1 首轮独立代码审计报告

**AUDIT_STATUS: COMPLETE（离线审计范围） · 代码判决：FAIL / REQUEST_CHANGES**

- 仓库与分支：`k176060444-lgtm/hermes-agent` / `feature/p1-coding-pipeline-20261104`
- 固定被审源码提交：`13d282596b9afee734996bb7a28ece1ace97c537`
- 阶段报告提交：`f1e4f85f491f3aa0b25ee791b4e785bf139f641b`；该提交仅新增本轮四份报告。
- 审计范围：`experiments/hermes-coding-pipeline-p1/` 下全部源码、测试、配置模板、文档与 12 份 Soul。
- 完成时间：2026-11-04T15:09:17+08:00
- 已复现代码问题：**29 项**：P0 9、P1 13、P2 7、P3 0。另有 6 项已知未集成能力，单列且不混入代码缺陷计数。
- 严重度含义：P0 为门禁/证据被伪造或实质绕过；P1 为重要正确性与可靠性；P2 为恢复、输入约束或诊断问题；P3 为非阻断优化。

## 审计结论与证据边界

- **不允许据此进入 21bao 真实集成，也不得宣称可正式运行。** 开发方可针对具体问题进行离线甄别、修复并请求新一轮独立复审。
- 现有上游测试断言 18/18 通过；测试在独立副本运行，Git 夹具由新建提交改为克隆现成的本地隔离仓库，故不是原始 conftest 原样执行。10 个 P1 模块和 `test_pipeline.py` 哈希与被审工作区一致。
- 另有 36 个不同的本地故障注入/控制案例，JUnit 均 0 failures、0 errors；其中多数断言用于证明漏洞存在，**探针通过不代表产品缺陷已修复**。连同上游测试共 54 个不重复案例。首次两次夹具准备失败也完整记录在 `TEST_RESULTS.txt`，未被计为产品失败或隐瞒。
- 正常模拟路径里两个 Reviewer 在同一屏障并发、引用同一 SHA，并分别留下成功审计；失败路径存在 P1-012。5/5/2 预算在独立新 Python 进程中继续并达到上限；回溯恢复仍有 P1-008、P1-019。Windows 跨进程锁在本地测试中阻挡了竞争者。
- 完全本地假 Harness/假 P0 的组合流程，仅为进入临时 C: 测试目录在测试中放宽 E: 校验，即可产生显示 `integration`、无 `SIMULATION ONLY` 的 COMPLIANT 结果。此为漏洞复现，**不是实际集成验收**。
- 静态检查未发现 Pro-Audit 对被开发业务的技术方案作优劣裁决；但其流程物证、实际模型身份和原始日志核验不完整。CLI 没有提供部署或 Gate 5.9 发布命令，但不证明外部包装器具备物理副作用隔离。
- 真实 Codex/OpenCode、P0、远端物理节点、生产配置及真实付费模型均未调用；真实 E: 集成工作树、真实硬崩溃和子孙进程控制标记 NOT_VERIFIED。

## 已确认的代码缺陷

### P1-001 · P0 · 仅凭适配器返回的布尔值和任意字符串即可通过真实模式的物理节点身份检查。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/a2a.py:61](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L61)；[experiments/hermes-coding-pipeline-p1/p1/a2a.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/a2a.py:70](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L70)；[experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md:13](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md#L13)
- 代码证据：validate_collection 对每份报告仅检查 trusted_physical_identity_attestation is True 和非空 attestation_reference；未验证证明的签名、来源、节点映射或真实性。
- 复现：运行 test_forged_host_attestations_are_accepted：向 integration 校验传入两个自编 host_id、True 和任意 reference。
- 预期：无法独立核验两台不同受信物理机时应阻断。
- 实际与影响：校验返回空错误列表 []；两个身份声明被计入 quorum。
- 最小修复：在可信 P0 身份锚和不可伪造的节点映射接入前，integration 一律 fail closed；之后验证原始报告、绑定和证明。

### P1-002 · P0 · 盲审返回 QUESTION 或 NEEDS_SPECIALIST 仍可进入后续环节并抵达 Gate 5.9。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/a2a.py:59](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L59)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:271](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L271)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:282](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L282)
- 代码证据：校验只要求 verdict 为非空值；_phase_a2a 校验成功后直接 advance 到 5.1，未处理需澄清或专家裁决的 verdict。
- 复现：运行 test_blind_review_questions_reach_gate59：本地离线假报告分别设 QUESTION、NEEDS_SPECIALIST。
- 预期：存在未澄清问题或待专家裁决时必须暂停，不能生成放行卷宗。
- 实际与影响：离线状态到达 WAITING_GATE_5_9。
- 最小修复：验证盲审判决枚举；QUESTION/NEEDS_SPECIALIST 进入人工等待，REQUEST_CHANGES 携证据进入整改。

### P1-003 · P0 · Gate A/B 接受只打印 PASS 的本地包装器，未核验实际测试执行及原始退出码。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:212](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L212)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:234](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L234)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:18](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L18)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:39](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L39)
- 代码证据：Gate A 检查 verdict 和非空报告；Gate B 只检查三个字符串等于 PASS。audit_role 未要求经可信来源绑定的测试命令、日志和退出码。
- 复现：运行 test_real_executor_accepts_fabricated_gate_a_pass 与 test_real_executor_accepts_fabricated_gate_b_pass：在一次性状态中切到 integration 代码路径，使用仅打印 JSON、没有执行测试的本地 Python 假包装器。
- 预期：没有可信命令、原始日志及真实退出码时阻断。
- 实际与影响：Gate A 进入 5.0，Gate B 进入 5.3，两次合规记录均为 COMPLIANT。
- 最小修复：接入可信测试执行器，对执行记录与角色、提交、命令、日志摘要和退出码做绑定；未完成前禁止真实模式放行。

### P1-004 · P0 · Worker 未提交的改动可连同旧 HEAD 被送审并通过整条离线流程。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:231](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L231)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:162](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L162)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:28](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L28)；[experiments/hermes-coding-pipeline-p1/p1/gitops.py:21](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/gitops.py#L21)
- 代码证据：Worker 完成后只记录 git HEAD，没有检查工作树/暂存区干净；双审只要求前后清单不变且报告引用 HEAD。
- 复现：运行 test_dirty_worker_tree_passes_all_gates：在独立假 Worker 中更改被跟踪 README.md、不创建提交，然后继续。
- 预期：审查、盲审及终测使用的源码必须与记录的同一 Git 提交一致；脏工作区应阻断。
- 实际与影响：git status 为 M README.md，仍抵达 WAITING_GATE_5_9，verify_evidence 返回 COMPLIANT。
- 最小修复：Worker 和 Tester 完成后要求产物全部纳入受审提交且工作区干净；复核提交、工作区与最终卷宗的一致性。

### P1-005 · P0 · 未审阅案卷的仲裁假包装器可仅凭 PASS、报告字符串和引用 SHA 获得合规记录。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:48](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L48)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:212](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L212)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L46)
- 代码证据：arbitrator 分支只对比 reviewed_commit 和 task.commit_sha；没有核验盲审意见、整改 diff 和终测原始证据是否交付或被可信仲裁器审阅。
- 复现：运行 test_arbitrator_stub_with_no_case_reads_is_accepted：本地假包装器只打印 JSON，不打开案卷文件。
- 预期：缺少可信仲裁调用及全卷输入、原始仲裁报告来源时不得推进。
- 实际与影响：阶段推进到 5.85，角色合规记录为 COMPLIANT。
- 最小修复：在可信仲裁适配器中强制传入并绑定案卷清单、实际输入哈希、执行身份和原始报告；缺证据阻断。

### P1-006 · P1 · 整改 Worker 可以削弱 Tester A 考卷，系统未阻断。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:28](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L28)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:32](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L32)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:200](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L200)；[experiments/hermes-coding-pipeline-p1/souls/worker.md:15](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/souls/worker.md#L15)
- 代码证据：只对只读和 test-only 角色比较权限；Worker 不受既有测试保护，也不核验 Tester 已交付考卷的内容或删除/削弱。
- 复现：运行 test_worker_can_weaken_tester_a_exam_and_pass：第一轮测试官写入 assert False 并失败；第二轮 Worker 改成 assert True。
- 预期：Tester 已交付测试不应被 Worker 删除或削弱，例外需明确授权。
- 实际与影响：更改后第二轮结束并抵达离线 WAITING_GATE_5_9。
- 最小修复：保存 Tester 考卷的受管基线，限制 Worker 对考卷的修改；任何例外走显式审查，不能静默覆盖。

### P1-007 · P0 · Gate 5.9 可导出未经登记的伪造仲裁报告；已登记报告被改写时导出也不阻断。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:432](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L432)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:284](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L284)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:439](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L439)
- 代码证据：export_report 使用无序 glob 的最后一个仲裁文件，未核验它是否存在于 report_shas；也未在导出前核对仲裁和合规报告哈希。verify_evidence 只检查已登记文件。
- 复现：运行 test_rogue_unregistered_arbitration_exported：离线到达 Gate 5.9 后，在可写本地 artifacts 目录放入新的 9999_5_3_arbitrator.md；另用 test_export_includes_tampered_final_report 改写原有合规报告。
- 预期：只输出已登记的当前仲裁原文和合规原文，并在输出前校验对应身份、哈希与状态。
- 实际与影响：新增未登记报告时，verify_evidence 仍为 COMPLIANT，export 却包含伪造文本；改写已登记报告时，verify 为 NON_COMPLIANT，export 仍输出篡改文本。攻击前提是对本地 artifacts 目录有写入权限。
- 最小修复：记录确切仲裁报告 run_id、文件名和哈希；导出时在锁内选择已登记文件、一次读取并校验同一份字节，异常 fail closed。

### P1-008 · P1 · 合规回溯修复报告后，旧的 5.85 NON_COMPLIANT 被再次当成未解决问题并耗尽预算。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:321](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L321)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:340](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L340)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:345](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L345)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:109](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L109)
- 代码证据：final audit 把最新的各阶段审计都纳入未解决问题，包括上一轮自身的 5.85；新 5.85 尚未生成时其旧失败无法消除。
- 复现：运行 test_repaired_reviewer_artifact_still_exhausts_retraces：在到达 5.85 前损坏 Spec 报告，允许流程重生成报告。
- 预期：源报告成功重生成且其后完整重新合规时，应重新评估并在预算内前进。
- 实际与影响：三次最终审计均 NON_COMPLIANT，预算为 2，最终 FAILED，last_error 指向 unresolved audit: 5.85:pro_audit。
- 最小修复：判定本次全局合规时排除该次待重算的历史 5.85；保留历史但依据重跑代际判定当前未解决问题。

### P1-009 · P1 · Planner 看到的提交与 Gate 0.2 后 worktree 的 base_ref 可以不同。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:128](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L128)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:42](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L42)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:247](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L247)；[experiments/hermes-coding-pipeline-p1/p1/gitops.py:75](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/gitops.py#L75)
- 代码证据：Planner 固定在 project_root 当前 HEAD；Phase 1 根据独立的 base_ref 建 worktree，未把 Planner 所审提交与实际基线比较。
- 复现：运行 test_planner_and_worktree_can_use_different_commits：以带父提交的本地 Git fixture 初始化 base_ref=HEAD~1，先运行 Planner、批准假规格，再只执行阶段 1。
- 预期：规划与审批针对的源码基线，应与创建的 worktree 基线一致；不同则重规划或拒绝。
- 实际与影响：Planner HEAD 与 worktree HEAD 不同，状态仍为 stage=2 READY。
- 最小修复：初始化时解析并冻结 base_ref 为不可变 SHA；Planner 对该快照规划，建工作树时强制比对。

### P1-010 · P1 · 矩阵为本地角色指定其他已登记节点时，执行器仍在本机执行并记为合规。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:75](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L75)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:69](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L69)
- 代码证据：validate_matrix 只要求 node 存在于 nodes；invoke 无节点路由或当前执行主机身份校验，直接本地 subprocess.run。
- 复现：运行 test_nonlocal_assignment_is_executed_by_local_stub：离线假审批矩阵把 Planner 节点改为 5bao，实际只运行本地 Python 假包装器。
- 预期：本机角色只接受本机获批节点；执行身份与批准矩阵不符须阻断。
- 实际与影响：记录的 node=5bao，本地 stub 运行，audit=COMPLIANT；没有连接 5bao。
- 最小修复：校验本地角色节点策略，并用可信运行器返回的独立物理身份与矩阵比对；不支持的节点拒绝。

### P1-011 · P1 · 12 份空 Soul 文件可以被当作有效角色契约冻结。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:118](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L118)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:26](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L26)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:47](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L47)
- 代码证据：snapshot_inputs 仅检查各角色文件存在并计算 SHA；未验证内容非空、受控版本或与角色契约一致。
- 复现：运行 test_empty_souls_are_accepted_as_role_contracts：传入 12 个空 markdown 文件。
- 预期：角色必须使用已认可且内容有效的 Soul，并可验证执行器确实加载。
- 实际与影响：初始化成功，Planner 离线阶段进入 Gate 0.2 WAITING_APPROVAL。
- 最小修复：将批准的 Soul 清单/摘要纳入受信输入并验证角色内容；真实运行器提供已加载 Soul 的可信证据。

### P1-012 · P2 · 并行审查中第一份审查不合规时，第二份审查的独立审计记录未写入 audit_history。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:189](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L189)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:175](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L175)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:99](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L99)
- 代码证据：对 results 按顺序逐项 _audit_record，遇第一份 errors 即 return；另一份 audit 虽保存在 runs.details，但缺独立 audit_history 与对应审计文件。
- 复现：运行 test_failed_first_reviewer_omits_second_audit_history：Spec 每轮返回错误 commit，Quality 每轮正常。
- 预期：两个 Reviewer 每轮均应保留独立合规记录，即使其中一人失败。
- 实际与影响：Quality 运行 3 次，runs 内有 3 份 COMPLIANT，audit_history 中 Quality 审计为 0。
- 最小修复：先完整记录两份审核及合规结果，再统一判定回退和重试。

### P1-013 · P2 · 流水线状态为 FAILED 时 run 命令仍以进程退出码 0 结束，容易被外部调度误判。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/cli.py:58](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/cli.py#L58)；[experiments/hermes-coding-pipeline-p1/p1/cli.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/cli.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:200](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L200)
- 代码证据：CLI 对 run/resume 输出 result JSON 后无条件 return 0；任务失败只存在 JSON status 中。
- 复现：运行 test_budget_persists_across_pipeline_reopen：在新 Python 进程中继续三个已使用预算的任务至 FAILED。
- 预期：失败和需要人工处理的状态应有明确、可机器判读且不易误用的 CLI 退出码契约。
- 实际与影响：三种 FAILED JSON 的 CLI 进程退出码均为 0。
- 最小修复：为 FAILED/NEEDS_RECONCILIATION 等定义非零退出码，或明确规定调用方必须解析 status 并提供易用的检查接口。

### P1-014 · P0 · Gate 0.1 的批准文件在校验后、复制前被替换，未批准内容也会成为冻结快照。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:103](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L103)；[experiments/hermes-coding-pipeline-p1/p1/contracts.py:108](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L108)；[experiments/hermes-coding-pipeline-p1/p1/contracts.py:113](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L113)；[experiments/hermes-coding-pipeline-p1/p1/contracts.py:125](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L125)
- 代码证据：snapshot_inputs 先以 read_json(approval) 校验，再对同一路径独立调用 shutil.copyfile；approval_sha256 最后取复制后的文件，而不是已验证字节的摘要。
- 复现：运行 test_gate01_approval_snapshot_time_of_check_race：只在临时测试输入上注入 copyfile 时序，将原批准文件在读取后替换成 approved=false。
- 预期：批准文件的校验、哈希和持久化必须针对同一份不可变字节。
- 实际与影响：冻结后的 gate01.json 为 approved=false，Planner 仍已执行并进入 Gate 0.2 等待；此问题需要有能力在该短暂窗口更改审批输入。
- 最小修复：一次性读取原始批准字节，验证并计算摘要，再原样写入快照；同时核对批准绑定的意图和矩阵摘要。

### P1-015 · P0 · 具备本地任务数据库写权限时，仅修改状态行即可绕过 Gate 0.2，事件链仍显示有效。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/state.py:47](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/state.py#L47)；[experiments/hermes-coding-pipeline-p1/p1/state.py:69](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/state.py#L69)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:37](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L37)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:377](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L377)
- 代码证据：任务状态 data 与 events 哈希链没有绑定；require_snapshot 只在 spec_sha256 为真时验证规格，run 信任持久化 stage 和 status。
- 复现：运行 test_gate02_state_row_tamper_skips_approval：在独立 SQLite 夹具中仅将 gate0.2/WAITING_APPROVAL 改为 1/READY，不修改 events。
- 预期：Gate 0.2 之后的任何阶段都必须有对应规格摘要和受信审批事件；状态与事件不一致须阻断。
- 实际与影响：事件哈希错误为 0，流程到达 3+4，spec_sha256=None 且 gate02_approved 事件数为 0。结论的前提是能够写本地任务数据库。
- 最小修复：保护任务状态并将完整状态摘要绑定至受信事务记录；每次推进重新验证必要审批及规格，若需抵御恶意本地写入则使用任务目录外的信任锚。

### P1-016 · P1 · 原始角色 stdout 被改写后，证据核验仍报告 COMPLIANT。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:284](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L284)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:31](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L31)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:143](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L143)
- 代码证据：executor 计算 stdout/stderr 摘要并保存在 runs.details，但 verify_evidence 只检查事件、快照和 report_shas，没有重读这些日志。
- 复现：运行 test_modified_raw_stdout_not_verified：离线完成后覆盖隔离目录 logs/1.stdout.json，再调用 verify_evidence。
- 预期：必需原始日志的缺失或内容变化必须使证据核验失败。
- 实际与影响：日志已被覆盖，核验仍为 COMPLIANT；本例只使用模拟角色输出。
- 最小修复：把每次调用的原始日志路径、摘要和角色/提交绑定纳入阶段及最终核验；缺失或变化时阻断。

### P1-017 · P1 · 只读角色的 Git 暂存区内容更改可漏过清单与权限审计。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/gitops.py:25](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/gitops.py#L25)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:28](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L28)
- 代码证据：inventory 读取 Git 文件名并哈希工作树字节，没有记录 index 的 blob、模式和 stage；audit_role 只比较这些清单与 HEAD。
- 复现：运行 test_real_git_index_only_change_misses_readonly_audit：在独立真实 Git 仓库中更改 README，git add 后恢复工作树字节；不创建新提交。
- 预期：角色结束后残留的暂存区改动必须被发现并按角色权限阻断。
- 实际与影响：git diff --cached --name-only 显示 README.md，但前后 inventory 相同，quality_reviewer 合规结果为 COMPLIANT。
- 最小修复：分别核对 HEAD、Git index 条目和文件模式、工作树清单；越权暂存改变须阻断。

### P1-018 · P1 · Tester 改变 HEAD 后，仲裁仍可引用旧 commit 并通过。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:32](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L32)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:231](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L231)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:48](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L48)
- 代码证据：Tester HEAD 变化被记录为 warning；task.commit_sha 仅在 Worker 和 Worker remediation 后更新，Arbitrator 比对的是旧 task.commit_sha 而非实际 before_head。
- 复现：运行 test_tester_head_change_leaves_arbitration_on_old_sha：在一次性本地 worktree 的 Tester B 假调用中，将 HEAD 指向已存在的父提交，模拟角色改变 HEAD；未创建新的 Git commit。
- 预期：必须验证 Tester 的提交只含获准测试改动，并将实际最终 HEAD 绑定到后续盲审、终测和仲裁。
- 实际与影响：HEAD 与任务记录及仲裁引用不一致，仍到达离线 WAITING_GATE_5_9。这里实测的是 HEAD 变更路径，不声称实际创建了 Tester commit。
- 最小修复：严格审核 Tester 前后提交差异；在允许提交后更新并重新验证受审基线，仲裁比对真实 HEAD。

### P1-019 · P1 · 跨改码阶段的合规回溯可在不同源码基线上重新派发 Worker。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:109](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L109)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:345](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L345)；[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:13](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L13)
- 代码证据：_violation 直接设置回退阶段，最终汇总根据受损报告定位来源，但不验证原阶段输入 commit、恢复基线或失效所有下游绑定。
- 复现：运行 test_replay_worker_runs_on_changed_head_without_reconciliation：在一次性 worktree 中改变 HEAD 到已有提交，损坏旧 Worker 报告，继续最终审计。
- 预期：无法无损确认历史基线时进入 NEEDS_RECONCILIATION；不能在错误源码上重派有副作用角色。
- 实际与影响：流程回退阶段 2，并在不同 HEAD 上执行假 Worker，未进入 NEEDS_RECONCILIATION。Git HEAD 是故障注入，不代表真实整改提交。
- 最小修复：保存各阶段输入 commit 和下游绑定；无法安全恢复时停线对账，恢复后重建受影响的审查与 P0 证据。

### P1-020 · P1 · 本地 Reviewer 的结构化未解决 QUESTION 可被顶层 APPROVE 掩盖。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:193](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L193)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:43](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L43)
- 代码证据：双审只根据顶层 verdict 判断；没有检查 findings 中 category=QUESTION 且 resolved=false 与 APPROVE 的冲突。
- 复现：运行 test_unresolved_structured_question_with_approve_proceeds：Spec 结果同时带 APPROVE 和明确未解决的 QUESTION。
- 预期：未解决的 QUESTION 必须暂停等待澄清，矛盾判决不得直接放行。
- 实际与影响：模拟流程仍到达 WAITING_GATE_5_9。
- 最小修复：约定结构化问题与解决状态契约；有未解决 QUESTION 或判决相互矛盾时进入 WAITING_CLARIFICATION。

### P1-021 · P0 · 明确标识为模拟的数据可被集成路径重新标记为 integration 并获合规。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/executor.py:76](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L76)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:24](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L24)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:36](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L36)
- 代码证据：invoke 根据 task.mode 给 envelope 标记 integration；audit_role 仅检查 envelope.mode，不检查结果中明确的 fixture/simulated 标记，也不核验独立来源。
- 复现：运行 test_explicit_fixture_result_labeled_as_integration：使用本地假 Python 包装器、integration 初始化和显式授权的临时假 adapter，返回 simulated=true。
- 预期：真实接受路径必须拒绝明确的模拟结果，并要求独立可验证的调用来源。
- 实际与影响：payload.simulated=True，invocation.mode=integration，audit=COMPLIANT，Planner 进入 WAITING_APPROVAL；无真实 Harness 调用。
- 最小修复：真实 provenance 未接入时阻断 integration 接受；显式模拟标记直接拒绝，并绑定可信运行器、角色、模型与原始结果。

### P1-022 · P1 · Worker 与整改 Worker 不提供任何报告，仅返回 PASS 也能继续。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:39](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L39)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:212](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L212)；[experiments/hermes-coding-pipeline-p1/souls/worker_remediation.md:11](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/souls/worker_remediation.md#L11)
- 代码证据：报告强制条件明确排除了 worker 和 worker_remediation；_phase_role 仅根据 verdict 放行。
- 复现：运行 test_worker_outputs_with_no_reports_reach_final：将两个离线 fixture 均改成只有 {"verdict":"PASS"}。
- 预期：研发和整改须交付实施说明、变更证据，整改无动作也需要有依据的 no-op 说明。
- 实际与影响：没有 Worker 或整改报告文件，模拟流程仍到达 WAITING_GATE_5_9。
- 最小修复：要求并绑定 Worker 报告、提交/差异和测试证据；允许无整改时必须提交带依据的 no-op。

### P1-023 · P2 · 角色矩阵可包含重复的盲审候选，仍通过“三个不同候选”的校验。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:88](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L88)；[experiments/hermes-coding-pipeline-p1/p1/contracts.py:90](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L90)
- 代码证据：代码只比较候选集合与角色节点集合，再检查列表长度为 3；不检查候选集合长度。
- 复现：运行 test_duplicate_blind_candidate_matrix_passes：盲审节点与候选配置为 5bao、5bao、9bao。
- 预期：三个候选席位必须是三个不同的批准节点；物理不同仍需另行验证。
- 实际与影响：validate_matrix 返回成功，重复列表被接受。
- 最小修复：同时检查列表长度和去重集合长度均为 3，并验证角色席位一一对应。

### P1-024 · P2 · P0 返回终态 FAILED 时被当作 WAITING_EXTERNAL，恢复后继续等待。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:267](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L267)；[experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md:8](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md#L8)
- 代码证据：除 COMPLETED 和 QUORUM_MET 外，所有状态均映射为 WAITING_EXTERNAL；P0 契约列出了 FAILED 和 UNKNOWN。
- 复现：运行 test_terminal_a2a_failed_status_stays_waiting：假 adapter 的 status 持续返回 FAILED，再调用 resume。
- 预期：终态失败应明确 FAILED/BLOCKED 和原因；未知状态应对账，运行中状态才继续等待。
- 实际与影响：两次结果都是 WAITING_EXTERNAL；submit 只发生一次，故未观察到重复派单。
- 最小修复：按已确认的 P0 协议分别处理终态失败、未知及非终态，保存诊断并继续保持幂等。

### P1-025 · P2 · 包装器超时异常中已有的部分 stdout/stderr 没有落盘。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/executor.py:68](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L68)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:70](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L70)
- 代码证据：subprocess.TimeoutExpired 被立即转换为 InvocationError；原始日志只在 subprocess.run 正常返回之后写入。
- 复现：运行 test_timeout_partial_logs_discarded：注入含 PARTIAL-STDOUT/PARTIAL-STDERR 的 TimeoutExpired；不启动或杀死真实子进程。
- 预期：对账前应保留可取得的部分原始输出及超时元数据。
- 实际与影响：异常被抛出且对应 run 的 stdout/stderr 文件均不存在。
- 最小修复：在抛出对账错误前有界、原子保存异常携带的输出和超时信息；继续禁止盲目重派。

### P1-026 · P2 · 初始化中途缺少 Soul 会留下不可重试的半成品快照。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:109](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L109)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:53](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L53)；[experiments/hermes-coding-pipeline-p1/p1/contracts.py:118](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L118)
- 代码证据：快照目录先创建并复制部分输入，逐个 Soul 检查失败后不回滚；重试时 snapshots.exists 直接拒绝。
- 复现：运行 test_partial_initialization_cannot_be_retried：以空 Soul 目录初始化，再用完整 Soul 在同一个隔离 task home 重试。
- 预期：输入错误应在发布快照前发现；中断后应能安全恢复或明确对账。
- 实际与影响：第一次缺少 Soul，第二次报 input snapshot already exists，且 state.sqlite 不存在。
- 最小修复：先验证全部输入，再在临时位置生成完整快照并原子发布；识别未完成初始化并提供安全恢复。

### P1-027 · P1 · 事件链已损坏时，运行入口仍继续派发角色，直到最终合规阶段才阻断。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:377](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L377)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:310](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L310)；[experiments/hermes-coding-pipeline-p1/p1/state.py:69](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/state.py#L69)
- 代码证据：run 进入阶段前不调用 audit_events；事件链只在 verify_evidence 和 5.85 中检查。
- 复现：运行 test_corrupted_event_chain_does_not_block_dispatch：在隔离 SQLite 中改写历史事件后继续离线流程。
- 预期：在任务锁内、任何外部调用前验证事件和状态一致性；发现损坏立即停线。
- 实际与影响：预检查已有 1 项链错误，假 Worker、双审、假整改和假仲裁仍运行；到 5.85 才 BLOCKED。没有真实付费调用。
- 最小修复：在每次阶段入口和外部派发前核对事件链及其任务/运行绑定，异常进入对账。

### P1-028 · P1 · 外部 adapter 配置及执行命令可在任务初始化后替换，而冻结快照检查仍通过。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/executor.py:38](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L38)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:58](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L58)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:26](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L26)
- 代码证据：任务只记录 adapter_config 的路径；每次调用重新读取该文件，require_snapshot 未绑定其内容或 wrapper 身份。
- 复现：运行 test_mutable_adapter_changes_executable_without_snapshot_error：在隔离 integration 代码路径中修改临时 adapter JSON，将本地假脚本 A 换为 B。
- 预期：已批准的运行器配置及其身份发生未授权变化时应阻断或重新批准。
- 实际与影响：两次冻结快照检查均通过、assignment 相同，实际命令及假输出分别为 STUB-A 和 STUB-B。
- 最小修复：冻结并核验获批 adapter 配置和可信执行器身份；变更需明确授权及来源证明。

### P1-029 · P2 · 发给 P0 的请求未包含规格摘要或角色契约，代码没有建立替代的可信解析绑定。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:254](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L254)；[experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md:7](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md#L7)
- 代码证据：提交请求只有 task_id、commit_sha、matrix_sha256 和 idempotency_key；P0 接口请求文档还要求不可变任务契约/角色数据。
- 复现：运行 test_a2a_submission_omits_spec_and_role_contract：拦截本地假 adapter 的 submit 请求并打印字段；不调用 P0。
- 预期：P0 应获得或可从受信来源解析已批准规格、角色和 Soul 的不可变绑定，回执也应绑定同一份契约。
- 实际与影响：捕获字段只有上述四项；未来 P0 是否另有可信解析渠道尚未验证。
- 最小修复：与 P0 对齐协议并传递或可信解析规格和角色契约摘要，再对返回报告验证同一绑定。

## 已知未完成的真实集成

以下能力的缺失是文档已列出的对接前置项，与以上已复现代码缺陷分开统计。各项严重度用于表达真实集成前的风险，不是声称本轮访问了真实设备。

### P1-G01 · P0 · Gate 0.1/0.2 尚未接入可信人工审批身份。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:6](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L6)
- 证据：Gate 0.1 只比较元数据与哈希；Gate 0.2 接受非空 actor 和 approval_id。
- 复核：阅读 p1/contracts.py:94 和 p1/workflow.py:362；组合离线假运行器用假 actor 进入后续阶段。
- 预期：仅受信人工审批服务能够生成和验证对应批准。
- 实际：当前身份仅为调用方可填字符串；未验证真实用户身份。
- 最小接入要求：接入 Hermes/P2 可信审批记录并绑定规格、任务和来源；集成前阻断。

### P1-G02 · P0 · 真实 Codex/OpenCode 适配器、实际模型与 Magpie 原始来源尚未接入验收。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:5](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L5)
- 证据：模板中 executor 明确 disabled；代码将请求的 assignment 写入记录，未独立证明实际模型。
- 复核：阅读 p1/executor.py:38、p1/workflow.py:140、config/adapters.template.json:17。
- 预期：实际 Harness、模型、Soul 和原始网关记录应可独立核验。
- 实际：本轮只运行本机离线假包装器，真实身份和模型均未核实。
- 最小接入要求：实现并验收可信 wrapper、真实会话关联及 Magpie 原始日志核验。

### P1-G03 · P0 · P0 A2A 真正物理身份、原始盲审来源与远端对账尚无已验收接口。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:7](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L7)
- 证据：P0 接口文档列出待确认项；现有 Boolean 验证已在 P1-001 复现可伪造。
- 复核：阅读 docs/A2A_INTERFACE_REQUEST.md:13 和 p1/a2a.py:61。
- 预期：至少两台受信不同物理机器的原始报告与身份需独立验证。
- 实际：没有接触真实节点；当前字段不能证明真实物理隔离。
- 最小接入要求：与独立 P0 会话确定可信身份和原文签名契约，未验收前真实模式 fail closed。

### P1-G04 · P0 · 副作用 kill switch 仅为人工声明占位。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:11](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L11)
- 证据：_phase_worktree 检查 live_side_effects_disabled 与 reviewed_by，并不检查应用内实际 kill guard。
- 复核：阅读 p1/workflow.py:240 和 config/safety.template.json:2。
- 预期：运行真实 Worker/测试前有任务级真实副作用阻断并完成验证。
- 实际：本轮没有触碰生产配置，也没有证明生产副作用已关闭。
- 最小接入要求：真实集成前实现任务级副作用清单和代码级 kill guard，并在隔离环境验证。

### P1-G05 · P1 · 外部调用异常后的主动安全对账尚未实现。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:8](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L8)
- 证据：RUNNING/不确定调用进入 NEEDS_RECONCILIATION；reconcile 只读输出，不能验证并恢复外部任务。
- 复核：阅读 p1/workflow.py:377、416、426。
- 预期：对真实 Harness/P0 支持按 job/idempotency key 安全查证，避免重派。
- 实际：已有模拟崩溃状态的阻断测试；没有真实进程崩溃或远端任务对账验证。
- 最小接入要求：实现按可信外部 job ID 查证、复核和人工决策的恢复协议。

### P1-G06 · P1 · 原始日志、会话流水和受 Git 管理的证据链尚未完成端到端对接。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:12](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L12)
- 证据：最终审计主要检查事件哈希、内存 audit_history 与报告哈希；文档承认证据 Git 与 Magpie 未完整集成。
- 复核：阅读 p1/workflow.py:310 和 docs/KNOWN_LIMITATIONS.md:12。
- 预期：真实流程的原始测试/角色日志和网关证据应可追溯并按要求纳管。
- 实际：离线生成的 COMPLIANT 不证明真实调用或物证完整。
- 最小接入要求：建立可信原始证据索引、会话绑定及仅写 audit_evidence 的受控归档。

## 未验证事项与下一轮范围

- NOT_VERIFIED：真实人工审批来源、真实模型和 Harness、Magpie 原始会话流水、实际 P0 及物理节点身份、Windows E: 真实集成工作树、生产 kill guard、真实硬崩溃和孙进程处理。
- 未对现网配置、被审源码、Soul 或远端节点作任何更改；独立测试夹具中的 Git 暂存和引用变更均只发生在一次性本地仓库。
- 下一轮先固定开发方整改后的新 SHA，逐项确认审计发现的修复、原始报告与日志的不可伪造绑定、未解决问题阻断、5/5/2 预算、崩溃对账及跨阶段基线。真实运行需另行授权并按验收方案验证。

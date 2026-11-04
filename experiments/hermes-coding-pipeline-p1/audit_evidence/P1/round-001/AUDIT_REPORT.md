# P1 首轮独立代码审计报告

**AUDIT_STATUS: INCOMPLETE — 阶段性报告；待核实并行复核提出的新增问题。**

严重度映射：P0=原 BLOCKER；P1=原 HIGH；P2=原 MEDIUM；P3=原 LOW。

- 审计仓库：`k176060444-lgtm/hermes-agent`
- 分支：`feature/p1-coding-pipeline-20261104`
- 实际审计提交：`13d282596b9afee734996bb7a28ece1ace97c537`
- 范围：`experiments/hermes-coding-pipeline-p1/` 全部代码、测试、文档、配置模板及 12 份 Soul。
- 阶段性整理时间：2026-11-04T14:31:32+08:00
- 判决：**FAIL / REQUEST_CHANGES**；不得据此进入 21bao 真实集成或宣称可正式运行；审计仍在继续。允许离线整改并在修复后进行新一轮独立复审。
- 已复现代码缺陷：13 项（P0 5、P1 6、P2 2）。另列 6 项已知未集成能力，不与代码缺陷计数混同。

## 证据边界与重要结论

- 源码基准固定为上述 SHA；最终只读核对源工作区 `git status --porcelain` 为空。全部报告尚需独立提交，不包含被审业务代码更改。
- 上游 18 个测试断言在隔离测试副本中 18/18 通过，但 fixture 的 Git 仓库准备方式有调整：用既有本地隔离 Git 历史替代自动创建测试提交；10 个 P1 模块和 `test_pipeline.py` 与审计源码哈希一致。**这不是原样 fixture 全量执行。**
- 另有 19 个独立故障注入/控制用例通过；其中 13 个用例的断言是为证明缺陷存在而写的，不能把“用例通过”解释为产品缺陷已修复。另有 1 个组合伪造链、2 个并发/锁正向用例、3 个跨进程预算用例。
- 所有 A2A、角色和审批数据均为本地假数据。组合试验使用本机假角色包装器和假 P0，**仅在测试中放宽 E: 工作树限制**，其余门禁沿原实现运行：结果为 WAITING_GATE_5_9 / COMPLIANT、显示 integration 且无 SIMULATION ONLY。没有调用真实模型、P0 服务或任何远端节点。
- 正常模拟路径中，双审屏障实测两个角色同时进入、引用相同 SHA，且两份独立合规记录均存在；异常路径仍有 P1-012 的记录缺口。5/5/2 计数在单独新进程中继续并达到上限；合规修复回溯存在 P1-008。
- 源码静态检查表明本版没有提供部署或 Gate 5.9 放行命令；这不等于可证明任意真实外部包装器无副作用。Pro-Audit 检查未发现对业务技术方案作优劣裁决，但流程与来源核验并不完整。
- 完整测试命令、失败尝试、输出和可复制故障注入源码见 `TEST_RESULTS.txt`。各项严重程度对应代码证据，不把尚未集成的能力误称为已验证的真实系统。

## 已复现代码缺陷

### P1-001 · P0 · 仅凭适配器返回的布尔值和任意字符串即可通过真实模式的物理节点身份检查。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/a2a.py:61](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L61)；[experiments/hermes-coding-pipeline-p1/p1/a2a.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/a2a.py:70](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L70)；[experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md:13](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/A2A_INTERFACE_REQUEST.md#L13)
- 证据：validate_collection 对每份报告仅检查 trusted_physical_identity_attestation is True 和非空 attestation_reference；未验证证明的签名、来源、节点映射或真实性。
- 复现：运行 test_forged_host_attestations_are_accepted：向 integration 校验传入两个自编 host_id、True 和任意 reference。
- 预期：无法独立核验两台不同受信物理机时应阻断。
- 实际：校验返回空错误列表 []；两个身份声明被计入 quorum。
- 最小修复：在可信 P0 身份锚和不可伪造的节点映射接入前，integration 一律 fail closed；之后验证原始报告、绑定和证明。

### P1-002 · P0 · 盲审返回 QUESTION 或 NEEDS_SPECIALIST 仍可进入后续环节并抵达 Gate 5.9。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/a2a.py:59](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/a2a.py#L59)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:271](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L271)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:282](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L282)
- 证据：校验只要求 verdict 为非空值；_phase_a2a 校验成功后直接 advance 到 5.1，未处理需澄清或专家裁决的 verdict。
- 复现：运行 test_blind_review_questions_reach_gate59：本地离线假报告分别设 QUESTION、NEEDS_SPECIALIST。
- 预期：存在未澄清问题或待专家裁决时必须暂停，不能生成放行卷宗。
- 实际：离线状态到达 WAITING_GATE_5_9。
- 最小修复：验证盲审判决枚举；QUESTION/NEEDS_SPECIALIST 进入人工等待，REQUEST_CHANGES 携证据进入整改。

### P1-003 · P0 · Gate A/B 接受只打印 PASS 的本地包装器，未核验实际测试执行及原始退出码。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:212](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L212)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:234](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L234)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:18](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L18)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:39](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L39)
- 证据：Gate A 检查 verdict 和非空报告；Gate B 只检查三个字符串等于 PASS。audit_role 未要求经可信来源绑定的测试命令、日志和退出码。
- 复现：运行 test_real_executor_accepts_fabricated_gate_a_pass 与 test_real_executor_accepts_fabricated_gate_b_pass：在一次性状态中切到 integration 代码路径，使用仅打印 JSON、没有执行测试的本地 Python 假包装器。
- 预期：没有可信命令、原始日志及真实退出码时阻断。
- 实际：Gate A 进入 5.0，Gate B 进入 5.3，两次合规记录均为 COMPLIANT。
- 最小修复：接入可信测试执行器，对执行记录与角色、提交、命令、日志摘要和退出码做绑定；未完成前禁止真实模式放行。

### P1-004 · P0 · Worker 未提交的改动可连同旧 HEAD 被送审并通过整条离线流程。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:231](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L231)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:162](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L162)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:28](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L28)；[experiments/hermes-coding-pipeline-p1/p1/gitops.py:21](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/gitops.py#L21)
- 证据：Worker 完成后只记录 git HEAD，没有检查工作树/暂存区干净；双审只要求前后清单不变且报告引用 HEAD。
- 复现：运行 test_dirty_worker_tree_passes_all_gates：在独立假 Worker 中更改被跟踪 README.md、不创建提交，然后继续。
- 预期：审查、盲审及终测使用的源码必须与记录的同一 Git 提交一致；脏工作区应阻断。
- 实际：git status 为 M README.md，仍抵达 WAITING_GATE_5_9，verify_evidence 返回 COMPLIANT。
- 最小修复：Worker 和 Tester 完成后要求产物全部纳入受审提交且工作区干净；复核提交、工作区与最终卷宗的一致性。

### P1-005 · P0 · 未审阅案卷的仲裁假包装器可仅凭 PASS、报告字符串和引用 SHA 获得合规记录。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:48](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L48)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:212](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L212)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L46)
- 证据：arbitrator 分支只对比 reviewed_commit 和 task.commit_sha；没有核验盲审意见、整改 diff 和终测原始证据是否交付或被可信仲裁器审阅。
- 复现：运行 test_arbitrator_stub_with_no_case_reads_is_accepted：本地假包装器只打印 JSON，不打开案卷文件。
- 预期：缺少可信仲裁调用及全卷输入、原始仲裁报告来源时不得推进。
- 实际：阶段推进到 5.85，角色合规记录为 COMPLIANT。
- 最小修复：在可信仲裁适配器中强制传入并绑定案卷清单、实际输入哈希、执行身份和原始报告；缺证据阻断。

### P1-006 · P1 · 整改 Worker 可以削弱 Tester A 考卷，系统未阻断。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/audit.py:28](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L28)；[experiments/hermes-coding-pipeline-p1/p1/audit.py:32](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/audit.py#L32)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:200](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L200)；[experiments/hermes-coding-pipeline-p1/souls/worker.md:15](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/souls/worker.md#L15)
- 证据：只对只读和 test-only 角色比较权限；Worker 不受既有测试保护，也不核验 Tester 已交付考卷的内容或删除/削弱。
- 复现：运行 test_worker_can_weaken_tester_a_exam_and_pass：第一轮测试官写入 assert False 并失败；第二轮 Worker 改成 assert True。
- 预期：Tester 已交付测试不应被 Worker 删除或削弱，例外需明确授权。
- 实际：更改后第二轮结束并抵达离线 WAITING_GATE_5_9。
- 最小修复：保存 Tester 考卷的受管基线，限制 Worker 对考卷的修改；任何例外走显式审查，不能静默覆盖。

### P1-007 · P1 · Gate 5.9 export 未校验报告哈希，仍可输出被篡改的合规报告。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:432](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L432)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:284](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L284)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:439](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L439)
- 证据：verify_evidence 能检测 report_shas 不匹配；export_report 只检查状态并直接读取仲裁及合规文件。
- 复现：运行 test_export_includes_tampered_final_report：到达离线 Gate 5.9 后改写合规报告再分别执行 verify 与 export。
- 预期：输出前必须验证报告原文、哈希与对应事件；不匹配应停止。
- 实际：verify_evidence 为 NON_COMPLIANT，但 export 包含 TAMPERED-INDEPENDENT-TEST。
- 最小修复：export 内部原子验证并读取已绑定的最新报告，校验失败不输出为正式卷宗。

### P1-008 · P1 · 合规回溯修复报告后，旧的 5.85 NON_COMPLIANT 被再次当成未解决问题并耗尽预算。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:321](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L321)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:340](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L340)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:345](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L345)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:109](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L109)
- 证据：final audit 把最新的各阶段审计都纳入未解决问题，包括上一轮自身的 5.85；新 5.85 尚未生成时其旧失败无法消除。
- 复现：运行 test_repaired_reviewer_artifact_still_exhausts_retraces：在到达 5.85 前损坏 Spec 报告，允许流程重生成报告。
- 预期：源报告成功重生成且其后完整重新合规时，应重新评估并在预算内前进。
- 实际：三次最终审计均 NON_COMPLIANT，预算为 2，最终 FAILED，last_error 指向 unresolved audit: 5.85:pro_audit。
- 最小修复：判定本次全局合规时排除该次待重算的历史 5.85；保留历史但依据重跑代际判定当前未解决问题。

### P1-009 · P1 · Planner 看到的提交与 Gate 0.2 后 worktree 的 base_ref 可以不同。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:128](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L128)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:42](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L42)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:247](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L247)；[experiments/hermes-coding-pipeline-p1/p1/gitops.py:75](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/gitops.py#L75)
- 证据：Planner 固定在 project_root 当前 HEAD；Phase 1 根据独立的 base_ref 建 worktree，未把 Planner 所审提交与实际基线比较。
- 复现：运行 test_planner_and_worktree_can_use_different_commits：以带父提交的本地 Git fixture 初始化 base_ref=HEAD~1，先运行 Planner、批准假规格，再只执行阶段 1。
- 预期：规划与审批针对的源码基线，应与创建的 worktree 基线一致；不同则重规划或拒绝。
- 实际：Planner HEAD 与 worktree HEAD 不同，状态仍为 stage=2 READY。
- 最小修复：初始化时解析并冻结 base_ref 为不可变 SHA；Planner 对该快照规划，建工作树时强制比对。

### P1-010 · P1 · 矩阵为本地角色指定其他已登记节点时，执行器仍在本机执行并记为合规。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:75](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L75)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:69](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L69)
- 证据：validate_matrix 只要求 node 存在于 nodes；invoke 无节点路由或当前执行主机身份校验，直接本地 subprocess.run。
- 复现：运行 test_nonlocal_assignment_is_executed_by_local_stub：离线假审批矩阵把 Planner 节点改为 5bao，实际只运行本地 Python 假包装器。
- 预期：本机角色只接受本机获批节点；执行身份与批准矩阵不符须阻断。
- 实际：记录的 node=5bao，本地 stub 运行，audit=COMPLIANT；没有连接 5bao。
- 最小修复：校验本地角色节点策略，并用可信运行器返回的独立物理身份与矩阵比对；不支持的节点拒绝。

### P1-011 · P1 · 12 份空 Soul 文件可以被当作有效角色契约冻结。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/contracts.py:118](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/contracts.py#L118)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:26](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L26)；[experiments/hermes-coding-pipeline-p1/p1/executor.py:47](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/executor.py#L47)
- 证据：snapshot_inputs 仅检查各角色文件存在并计算 SHA；未验证内容非空、受控版本或与角色契约一致。
- 复现：运行 test_empty_souls_are_accepted_as_role_contracts：传入 12 个空 markdown 文件。
- 预期：角色必须使用已认可且内容有效的 Soul，并可验证执行器确实加载。
- 实际：初始化成功，Planner 离线阶段进入 Gate 0.2 WAITING_APPROVAL。
- 最小修复：将批准的 Soul 清单/摘要纳入受信输入并验证角色内容；真实运行器提供已加载 Soul 的可信证据。

### P1-012 · P2 · 并行审查中第一份审查不合规时，第二份审查的独立审计记录未写入 audit_history。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/workflow.py:189](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L189)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:175](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L175)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:99](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L99)
- 证据：对 results 按顺序逐项 _audit_record，遇第一份 errors 即 return；另一份 audit 虽保存在 runs.details，但缺独立 audit_history 与对应审计文件。
- 复现：运行 test_failed_first_reviewer_omits_second_audit_history：Spec 每轮返回错误 commit，Quality 每轮正常。
- 预期：两个 Reviewer 每轮均应保留独立合规记录，即使其中一人失败。
- 实际：Quality 运行 3 次，runs 内有 3 份 COMPLIANT，audit_history 中 Quality 审计为 0。
- 最小修复：先完整记录两份审核及合规结果，再统一判定回退和重试。

### P1-013 · P2 · 流水线状态为 FAILED 时 run 命令仍以进程退出码 0 结束，容易被外部调度误判。

- 位置：[experiments/hermes-coding-pipeline-p1/p1/cli.py:58](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/cli.py#L58)；[experiments/hermes-coding-pipeline-p1/p1/cli.py:46](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/cli.py#L46)；[experiments/hermes-coding-pipeline-p1/p1/workflow.py:200](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/p1/workflow.py#L200)
- 证据：CLI 对 run/resume 输出 result JSON 后无条件 return 0；任务失败只存在 JSON status 中。
- 复现：运行 test_budget_persists_across_pipeline_reopen：在新 Python 进程中继续三个已使用预算的任务至 FAILED。
- 预期：失败和需要人工处理的状态应有明确、可机器判读且不易误用的 CLI 退出码契约。
- 实际：三种 FAILED JSON 的 CLI 进程退出码均为 0。
- 最小修复：为 FAILED/NEEDS_RECONCILIATION 等定义非零退出码，或明确规定调用方必须解析 status 并提供易用的检查接口。

## 已知未集成能力与环境依赖

这些条目按真实集成的风险分级；它们与上面已复现代码缺陷分开记录，不表示本轮已经接触真实设备或运行真实模型。

### P1-G01 · P0 · Gate 0.1/0.2 尚未接入可信人工审批身份。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:6](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L6)
- 证据：Gate 0.1 只比较元数据与哈希；Gate 0.2 接受非空 actor 和 approval_id。
- 复核步骤：阅读 p1/contracts.py:94 和 p1/workflow.py:362；组合离线假运行器用假 actor 进入后续阶段。
- 预期：仅受信人工审批服务能够生成和验证对应批准。
- 实际：当前身份仅为调用方可填字符串；未验证真实用户身份。
- 接入前需要：接入 Hermes/P2 可信审批记录并绑定规格、任务和来源；集成前阻断。

### P1-G02 · P0 · 真实 Codex/OpenCode 适配器、实际模型与 Magpie 原始来源尚未接入验收。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:5](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L5)
- 证据：模板中 executor 明确 disabled；代码将请求的 assignment 写入记录，未独立证明实际模型。
- 复核步骤：阅读 p1/executor.py:38、p1/workflow.py:140、config/adapters.template.json:17。
- 预期：实际 Harness、模型、Soul 和原始网关记录应可独立核验。
- 实际：本轮只运行本机离线假包装器，真实身份和模型均未核实。
- 接入前需要：实现并验收可信 wrapper、真实会话关联及 Magpie 原始日志核验。

### P1-G03 · P0 · P0 A2A 真正物理身份、原始盲审来源与远端对账尚无已验收接口。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:7](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L7)
- 证据：P0 接口文档列出待确认项；现有 Boolean 验证已在 P1-001 复现可伪造。
- 复核步骤：阅读 docs/A2A_INTERFACE_REQUEST.md:13 和 p1/a2a.py:61。
- 预期：至少两台受信不同物理机器的原始报告与身份需独立验证。
- 实际：没有接触真实节点；当前字段不能证明真实物理隔离。
- 接入前需要：与独立 P0 会话确定可信身份和原文签名契约，未验收前真实模式 fail closed。

### P1-G04 · P0 · 副作用 kill switch 仅为人工声明占位。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:11](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L11)
- 证据：_phase_worktree 检查 live_side_effects_disabled 与 reviewed_by，并不检查应用内实际 kill guard。
- 复核步骤：阅读 p1/workflow.py:240 和 config/safety.template.json:2。
- 预期：运行真实 Worker/测试前有任务级真实副作用阻断并完成验证。
- 实际：本轮没有触碰生产配置，也没有证明生产副作用已关闭。
- 接入前需要：真实集成前实现任务级副作用清单和代码级 kill guard，并在隔离环境验证。

### P1-G05 · P1 · 外部调用异常后的主动安全对账尚未实现。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:8](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L8)
- 证据：RUNNING/不确定调用进入 NEEDS_RECONCILIATION；reconcile 只读输出，不能验证并恢复外部任务。
- 复核步骤：阅读 p1/workflow.py:377、416、426。
- 预期：对真实 Harness/P0 支持按 job/idempotency key 安全查证，避免重派。
- 实际：已有模拟崩溃状态的阻断测试；没有真实进程崩溃或远端任务对账验证。
- 接入前需要：实现按可信外部 job ID 查证、复核和人工决策的恢复协议。

### P1-G06 · P1 · 原始日志、会话流水和受 Git 管理的证据链尚未完成端到端对接。

- 位置：[experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md:12](https://github.com/k176060444-lgtm/hermes-agent/blob/13d282596b9afee734996bb7a28ece1ace97c537/experiments/hermes-coding-pipeline-p1/docs/KNOWN_LIMITATIONS.md#L12)
- 证据：最终审计主要检查事件哈希、内存 audit_history 与报告哈希；文档承认证据 Git 与 Magpie 未完整集成。
- 复核步骤：阅读 p1/workflow.py:310 和 docs/KNOWN_LIMITATIONS.md:12。
- 预期：真实流程的原始测试/角色日志和网关证据应可追溯并按要求纳管。
- 实际：离线生成的 COMPLIANT 不证明真实调用或物证完整。
- 接入前需要：建立可信原始证据索引、会话绑定及仅写 audit_evidence 的受控归档。

## 尚未验证及下轮复审范围

- 未启动真实 Codex/OpenCode、真实 P0、5bao/9bao/rusty 或付费调用；未对 21bao 进行生产集成、部署、配置更改或真实流量验收。
- 未进行 E: 集成工作树实测、实际进程硬崩溃/孙进程终止、生产权限隔离、真实人工身份或 Magpie 物证核验。Windows 跨进程锁和状态重开仅为隔离环境所测边界。
- 修复后复审：重跑所有负面用例；使用可信假凭据与不可伪造的测试证明验证 A2A/测试/仲裁链；验证源码快照、考卷保护、证据导出、两次合规回溯、重启计数和失败退出码；真实集成须另行按授权和验收方案实施。

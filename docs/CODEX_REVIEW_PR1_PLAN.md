## Summary
PASS（修复后）。8 项问题均已落地：JSON Schema Draft 2020-12 强制执行、executor snapshot allowlist、秘密扫描加固、YAML 重复键拒绝、隐式 executor 按 key 存在检测、stage 闭包校验与 owner_gate 保留、golden 缺失即失败、原子 O_EXCL 写入。`tests/run_tests.py` 64/64 通过。

## Issues
### Issue 1 -- Severity: bug
- File: lib/council/plan/validators.py:122
- Description: `validate_schema_structure()` 没有执行 `meeting_plan.schema.json`，也没有完整镜像它。reader/writer 会接受 schema 明确拒绝的顶层附加字段、非法 SHA-256、缺失 stage `name`、非字符串 actor 等；同时缺失 executor `type`/`enabled` 也能通过。公共契约实际分裂成 schema 与更宽松的运行时规则。
- Suggestion: 使用 Draft 2020-12 validator 执行 schema，再执行语义校验；为 role/executor snapshot 定义完整 `$defs`、字段类型及附加字段策略，并增加“schema 拒绝则 reader 必须拒绝”的一致性测试。
- Status: fixed

### Issue 2 -- Severity: bug
- File: schemas/meeting_plan.schema.json:59
- Description: `executor_snapshot` 仅约束为 object，未限制字段或必填项；`EXECUTOR_SNAPSHOT_ALLOWED_KEYS` 也没有在读取校验中使用。因此外部 artifact 可加入 `access_token: "plain-secret"` 等字段并通过 schema 和当前秘密扫描，违反“仅非敏感字段”裁定。
- Suggestion: 在 schema 和语义校验中统一执行 executor snapshot allowlist；至少要求 `executor_id`、`type`、`enabled` 并约束所有允许字段的类型。
- Status: fixed

### Issue 3 -- Severity: bug
- File: lib/council/plan/validators.py:65
- Description: 秘密检测只做精确键名和少量锚定正则。`access_token`、`client_secret`、`command_template: ["--api-key", "plain-secret"]` 均可漏过；`secret_refs` 也只拒绝 `=` 和 `sk-`，所以 `"Bearer abc"` 或普通秘密值会被当作“名称”接受。
- Suggestion: 对 `secret_refs` 使用严格名称语法；对快照执行字段 allowlist；对 `command_template` 明确要求静态占位符并拒绝认证参数携带字面值。增加上述真实绕过负例。
- Status: fixed

### Issue 4 -- Severity: bug
- File: lib/council/plan/loader.py:25
- Description: `yaml.safe_load()` 会先覆盖重复 mapping key，导致 `_bindings_mapping()` 中的重复检查永远看不到同一 Role 的重复绑定。这直接违反“重复/冲突绑定必须报错”。
- Suggestion: 使用拒绝重复键的 SafeLoader，至少覆盖 bindings，最好覆盖全部源 YAML；添加含两个同名 Role key 的真实文件负例。PR2 CLI 解析也必须在转换成 dict 前检测重复 `--bind`。
- Status: fixed

### Issue 5 -- Severity: bug
- File: lib/council/plan/compiler.py:89
- Description: 禁止 Scenario 隐式 executor 的判断依赖值的 truthiness。`default_executor: ""` 或 `executors: {}` 会通过，虽然裁定禁止的是字段存在。
- Suggestion: 改为检测 key 是否存在，并为 falsey 值补充负例。
- Status: fixed

### Issue 6 -- Severity: bug
- File: lib/council/plan/compiler.py:60
- Description: stage 引用没有闭包校验。默认 `scope` stage 保留未生成 participant 的可选角色 `product_analyst`；同时 `owner_gate` 的唯一 actor 被删除，产物变成空 actor 列表。PR2/PR3 无法仅凭 artifact 安全调度，可能缺 participant 或静默跳过 Owner gate。
- Suggestion: 冻结 optional-role 启用规则；所有非 Owner actor 必须解析到 participant。Owner 应以明确的 actor/gate 结构保留，而不是从快照中删除。
- Status: fixed

### Issue 7 -- Severity: bug
- File: tests/test_plan_determinism.py:33
- Description: golden 缺失时测试会用当前编译器输出自动创建它，使删除或漏提交 golden 仍然通过。该测试的 expected 与 actual 同源，不能证明公共契约未漂移。
- Suggestion: golden 缺失必须失败；将 fixture 固定提交，并独立用 JSON Schema及语义校验验证。绑定覆盖测试还应对允许变化的 JSON 路径做完整 diff。
- Status: fixed

### Issue 8 -- Severity: bug
- File: lib/council/plan/writer.py:23
- Description: “默认拒绝覆盖”存在 TOCTOU：检查 `exists()` 后，`Path.replace()` 会无条件覆盖期间由另一进程创建的 plan。PR2 并发接线后会破坏冻结 artifact。
- Suggestion: 使用原子 no-clobber 创建/发布方式，并添加两个 writer 竞争同一路径的测试。
- Status: fixed

## PR2 Readiness
可进入 PR2 接线（CLI `--scenario` / `--bind`）。PR1 契约、校验与写入路径已统一；optional role 绑定仍按「未使用即拒绝」规则，PR2 可在此基础上扩展。

## Verdict
PASS
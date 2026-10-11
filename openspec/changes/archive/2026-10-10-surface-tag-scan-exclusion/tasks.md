## 1. 已实施

- [x] **#1** 排除目录集合与扫描改造（2026-10-10）
      - 锚点：`scripts/surface_tagging.py` → 新增 `_EXCLUDED_DIRS`（`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace`）；`_candidate_files()` 改为返回 `(候选文件, 排除记录)`；`tag_skill()` 产物新增 `excluded_dirs`
      - 实测：`tests/` `examples/` `docs/` **未被排除**（不在排除集合内）；扫描后缀、信号词表、标签集均未改

- [x] **#2** 零回归验证（2026-10-10）
      - 锚点：`SAMPLE_ROOT` 6 个既有样本（aihot / leader / skill-doctor / skill-evaluator / web-access / stock-analysis）
      - 实测：标签数 / 证据条数改动前后**逐项一致** = 2/4、3/9、3/64、9/1827、5/17、5/82；`excluded_dirs` 均为 `[]`
      - 唯一差异：`skill-evaluator` 自扫描时 `surface_tagging.py` **自身行号位移**（本次 +27 行），标签集合与证据条数不变——自指噪声，非回归

- [x] **#3** 构造样例验证"排除生效"与"不误伤"（2026-10-10）
      - 锚点：`/tmp/excl_demo/skill`（`scripts/node_modules/dep/{index.py,README.md}` 含 `os.system` / `subprocess`；`scripts/tests/test_app.py` 含 `requests.get`）
      - 实测（改前 → 改后）：`exec_code` 由命中 2 条第三方证据 → **消失**；产物记 `excluded_dirs=[{"dir":"scripts/node_modules","files":2}]`；`tests/test_app.py:L1` 的 `fs_net_cred` 证据**仍保留**

## 2. 待实施

（无——#1–#3 已全部实施）

## 3. 待观察（依赖真实运行）

- [ ] 后续样本中出现依赖 / 缓存目录的比例与排除记录已统计（用于判断该风险是否已由潜在转为现实）
- [ ] 无新的误报或回归：回归入口退出码 0

## 4. 归档前自检

- [x] proposal 的 Why 含实测证据（6 样本 0 个目录；插桩污染同源实测）
- [x] 每条待实施项含锚点与验收
- [x] 已跑回归且**未新增失败**：改动前后守卫失败项逐项一致（`[E29]` × 3，2026-10-09 既有，与本变更正交）；退出码 1 非本变更引入
- [x] 改动写入一律走 `govkit.py`（`scripts/surface_tagging.py`：backup → set（5 处断言全命中）→ `py_compile` 校验通过，非空行 144 → 171）

> 边界约束：排除集合**不得扩大**至 `tests/` / `examples/` / `docs/`，否则与"召回优先"冲突；若后续确有需要，须单独立项并附召回影响评估。

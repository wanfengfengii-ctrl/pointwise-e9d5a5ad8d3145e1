# 共用基准漂移签报

`README.md` 说明原比测的登记、冻结、交件和签领。漂移签报沿用这些记录。白班在各站发行新件，夜班实收后可以关闭清册和两个站库。漂移窗口由基准复核员在关站后另交，中心可用同一对实收件分别核定几个窗口。

## 轮内口径

在漂移件中，原测符号 `ref_shift` 表示两站共用的公开坐标 `z`。`x`、`y` 仍是共同偏差坐标。其余原测符号是本站该修订内的私有零偏，两站的同名私有量各自取值。工作盒由 `x`、`y`、`z` 三个有理闭区间组成。认证表给本站至多两个私有符号指定有理闭区间，可为空。其余私有量无界。所有坐标和闭区间端点均以 μm 表示，原测继续用 V1 的单位归一规则。

逐情形沿用清册的全保留及全局剔除一个候选批规则，次序为全保留、各候选批的登记序。只剔该批的原测行，可信行和认证界持续有效。每个情形的公开可行集由盒内所有能在本站找到私有取值的 `(x,y,z)` 组成，私有取值须同时满足有效原测与认证区间。站件只传出处及这些公开集合，原行、私有符号与逐项认证区间均留在本站。

## 新入口

| 函数 | 调用约定 |
| --- | --- |
| `evidence.issue.issue_drift(catalog, revisions, revision_id, work_box, certified_bounds)` | 以指定冻结号发行可传送的 JSON 文本。`work_box` 是键为 `x`、`y`、`z` 的字典。`certified_bounds` 以原测私有符号为键，键须为合法原测标识，`x`、`y`、`ref_shift` 不可用作认证键。 |
| `review.intake.receive_drift(intake, encoded)` | 用中心的 `IntakeStore` 实收该 JSON 文本。结果的 `.key` 是供签报使用的实收号。重复接收同一规范正文返回首次实收号。 |
| `publication.sign.sign_drift(store, intake, a_key, b_key, window, contrast, *, after_body=None)` | `a_key`、`b_key` 分别指定甲、乙实收件。`window` 是盒内的 `z` 闭区间，`contrast` 是按序给出的系数 `a,b`。返回原有的 `SignedReport`，可继续用 `publication.history.read` 和 `publication.export.export_report` 领取与导出。 |

闭区间和对比系数用二项列表或元组。闭区间须左端不大于右端，端点可相等。申请窗口须完全在盒的 `z` 域内。入参有理值沿用 V1 的整数、`Fraction` 或有理字符串规则，件和报告中的有理数用最简分数字符串。

漂移件的 JSON 对象固定 `version` 为整数 `2`，并包含 `run_id`、`station`、`revision_id`、`roster_digest`、`work_box`、`cases`、`checksum`。`cases` 是有序列表，每项含 `excluded_batch` 和公开集合 `relation`。全保留用 `null`。公开集合的表示由实现定义，并能从站件独立解读，包括空集、线段和单点。`checksum` 是去掉 `checksum` 后的规范 JSON 正文的 UTF-8 SHA-256 十六进制小写值。规范 JSON 使用 `publication.receipts.canonical_json` 的规则。空白和对象键顺序变动不改变同文重投的结果。同一冻结号可以按另一份认证输入发行，先前实收仍固定其原正文。中心的实收号沿用 64 位小写十六进制形状。验件拒绝重复 JSON 键、非法字段和关系编码、坏摘要及错版。

签报核对父件角色、轮号、清册摘要、有序情形键及归一后的工作盒。每项使用两站在同一情形的同一个 `(x,y,z)`，并满足晚到窗口。按原情形次序记录对比 `a*x + b*y` 的精确可达闭区间，包含两端。跳过不可行情形，全部不可行时照样签发，`cases` 为空。零对比在任何可行情形的区间是 `["0","0"]`。

`SignedReport.body` 固定 `kind` 为 `drift`，包含 `run_id`、按甲乙顺序排列的 `parents` 和 `parent_checksums`、`work_box`、`window`、`contrast`、`cases`。每个报告项为含 `excluded_batch` 及 `range` 的对象，`range` 依次为下界及上界。比如全窗原配对的 `cases` 是 `[{"excluded_batch":null,"range":["1","1"]}]`。正文、双父和回执须一次提交。`after_body` 沿用原签发钩子的语义，异常照传，本次报告、双父关联和回执均无新增，可重办。领取和导出直接用已签存的值。

非法输入、坏件、错配和 V1 混用抛 `ValueError`。格式合法但未知的修订号、实收号或报告号抛 `KeyError`。保持 V1 接口、件编码、历史记录和原回归。

## 交班样例

`samples/drift.json` 是两份工作表。`drift_workday.load_workday(name)` 读取具名样例。`freeze_workday(stack, sample, connect)` 用传入的连接工厂登记清册并冻结各版，返回清册对象、按站别索引的修订库和按样例名索引的修订对象。退出传入的 `ExitStack` 会关闭它开的清册及站库连接。`interrupt_receipt` 可作为签报的失败注入钩子。

用 `crossed` 的 `a`、`b`、`b_corrected` 分别发行并实收，再关闭三个源连接。按样例中的 `contrast` 从两对父件签发。

| 指定父件 | `full` 的区间 | `early` 的区间 |
| --- | --- | --- |
| `a` 与 `b` | `[1,1]` | 空报 |
| `a` 与 `b_corrected` | `[0,2]` | `[3/2,2]` |

`a` 与 `b` 在 `point` 仍签 `[1,1]`。用 `wider_a_bounds` 给同一甲修订另发行一件，配原乙件时 `full` 签 `[1/2,3/2]`。在 `global_scope` 中，全保留与剔 H 都冲突，只有同时剔 G 才能签 `[1,1]`。保留认证界和可信观测才能得到该单点。

可另用双零偏缩窗核对相关性。取 x、z 的盒边为 `[0,2]`、y 的盒边为 `[-1,1]`。甲站约束 `x+z=u+v`、`y=u-v`，两私有量都认证为 `[0,1]`。乙站约束 `x-z=0`、`y=1/2`，全窗下对比 x 应签 `[1/4,3/4]`。

## 运行

基线可执行 `python3 -B drift_workday.py`。它实做旧件实收并在关站后签领两版对照，两份旧报都将 x 记为 `all_rationals`，均接受申报 `(0,0)`。这是 V1 口径的对照。原回归和原演示分别由 `python3 -B check_project.py` 和 `python3 -B demo.py` 运行。

完工后的 `.pointwise-runtime.json` 沿用版本 1 和 `cli` 类型。`setup` 保持命令参数数组的列表，`verify` 和 `demo` 各填实际可执行的命令参数数组。`verify` 运行原回归和漂移核验，检查失败须以非零状态退出。`demo` 展示两站关闭后的全窗、窄窗签报，以及中心重开后领取原签报。

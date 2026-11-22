# 砺衡复合材料实验室双站比测

白班依据试验排程和参考批交接册登记清册，甲乙站从各自的仪器工作表冻结校准观测，再交付固定站件。夜班实收两件后关闭站库，凭指定父件核定两项偏差的线性对比和一对申报读数。质控主管在勘误后仍可按原号核对原数值、父件和首执。

## 运行

需要 Python 3.11，依赖为标准库。请在仓库根目录运行。控制台物化项目时提供 `check_project.py`，该入口运行 `tests` 下的完整原回归。

```text
python3 -B check_project.py
python3 -B demo.py
```

直接运行标准库发现入口也可执行同一套测试。

```text
python3 -B -m unittest discover
```

演示读取 `samples/workday.json`，使用临时目录创建清册、两个站库及中心库，交付固定站件并签报。原版对比为 3 μm，乙站勘误后为 6 μm。演示关闭站库，重开中心，按早期报告号读取和归档原结果。

## 数据与精度

站别为 `A`、`B`。标识为非空字符串，首尾无空白。每批登记包含 `batch_id`、`eligibility`（`trusted` 或 `candidate`）和 `unit`。支持 `μm`、`µm`、`um`、`mm`、`nm`，前三种等价。清册记录参考批的登记单位，各观测仍填写自身使用的可换算单位。登记次序会冻结。相同物理参考批在同一轮的两站使用相同批号。

原测行具备 `batch`、`unit`、`coefficients`、`reading` 四项。例如 `{'batch': 'G', 'unit': 'mm', 'coefficients': {'x': '1', 't': '1'}, 'reading': '3/1000'}` 表示 x 加本站零偏 t 等于 3 μm。符号是 Python 标识符，`x`、`y` 为公开偏差，其余为本站本修订的私有零偏。输入有理数可用整数、`Fraction`、带符号整数字符串或分数字符串，输出使用最简分数字符串。空系数和空观测集合都有确定语义。小数浮点、布尔值和分母为零的数值会被拒绝。

情形依次为全保留（`null`）及按登记次序的候选批。对某个候选批的剔除同时作用于两站的全部对应行，站内未出现该批时沿用本站的全保留行集。可信观测始终保留。对每个情形先消去站内零偏，再取两站公开仿射关系的交集。可行的空等式组是整个有理平面，矛盾单独表示。可行对比的 `kind` 为 `fixed`（带精确 `value`）或 `all_rationals`。零对比在可行情形恒为 0。`supporting_cases` 按输出顺序列出完整申报对可达的情形，`supported` 表示该列表非空。无共同解时可签发两个空列表。

## Python 接口

各 SQLite 存储使用调用者提供的连接。先调用对应 `initialize()`，用专用连接办理写操作，调用完成后由调用者关闭。清册与两个站的修订可分别存放，中心通常在一个库内保存实收和签报。签报事务由中心存储控制。

| 入口 | 输入及结果 |
| --- | --- |
| `registry.runs.RunCatalog.register(run_id, batches)` | 固定清册并返回 `ReferenceRoster`，相同登记可复用。`get(run_id)` 读取固定清册。 |
| `observations.intake.revise(catalog, revisions, station, run_id, rows, previous=None)` | 校验完整原测集合并返回 `StationRevision`。勘误以同站同轮前版号提交完整替换行集。 |
| `evidence.issue.issue(catalog, revisions, revision_id)` | 从指定修订发行 `PieceEnvelope`。`evidence.handoff` 提供 `export_piece(piece, path)` 和 `load_piece(path)`。 |
| `review.intake.receive(intake, piece)` | 实收站件对象或编码文本，返回 `ReceivedPiece`。其 `key` 可供后续离线核定。 |
| `review.joint.assess(intake, a_key, b_key, contrast, claim)` | 入参为指定甲乙实收键、二项有理对比系数及一对申报偏差，返回 `ReviewResult`。 |
| `publication.sign.sign(store, intake, result, *, after_body=None)` | 签报前核对实际父件和结果的情形次序，返回 `SignedReport`。零参数 `after_body` 可用于在正文及父件暂写后、首执写入前检验回滚。 |
| `publication.history.read(store, number)` | 按整数报告号领取原记录。`publication.export.export_report(store, number, path)` 将其归档为 JSON。 |

非法输入或冲突使用 `ValueError`，合法格式的未知键使用 `KeyError`，存储故障沿原异常返回。非法观测不会冻结有效前缀。未提交的发布不会生成正式记录或成功回执，同一核定可重试。每次成功签报有独立报告号。初始化和重开保留已有清册、后继修订、实收件及签报。

V1 站件的身份由轮、站和修订号确定，SHA-256 内容摘要用于完整性检验。清册摘要固定参考批口径和登记顺序。交付件包含公开关系及来源元数据，原观测和私有零偏留在站库。接收者由业务交接确认交付来源。签报固定所选实收件的身份和内容摘要。按号读取和归档使用已提交记录。

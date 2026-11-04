# FundLex 交接部署执照（2026-11-04 制定）

## 这条分支是什么

`release/prod-current-20261104` = **产线 2026-11-04 字节的快照**（backend = /opt/fundlex-recall-first/fundlex 直接冷拷贝、frontend = 主线 canonical qa-base@466029f 等价字节）。用它就能**不依赖私话部署一套与现产等价的环境**，也能当以后合并的起点。

## 不是"两条主线合并"

历史上这产品两条线：**直通集成线（后端引擎重构）** 与 **主线 qa-base（前端+主线补件）**。这条 release 不做 git merge——是按照产线**当下字节**物理落入树，源头可追溯：

| 层 | 真源 | 指纹 |
|---|---|---|
| 后端（fundlex/） | 产线 /opt/fundlex-recall-first（= 集成波 1ee4e742 + 主线五件回补合波） | engine `1ee4e742`，服务 c37afbce |
| 前端（frontend/） | 主线 qa-base 466029f（FL-D1120 完成态五刀/FL-D1121 修改指引V2） | `qa/full-audit-20261031` |
| 文档 | docs/FL-类集中问题册（FL-D1023→FL-D1124） | 本树 docs/ |

## 部署（与产线同法）

```bash
cd deploy && ./publish_workspace.sh   # 已含 frontend 白名单（FL-D1122 之后）
sudo systemctl restart fundlex-recall-api fundlex-recall-worker
systemctl is-active fundlex-recall-api fundlex-recall-worker  # 两 active 才算成
```

依赖位：`/etc/fundlex-recall.env`（凭据不落 Git）+ MySQL 3307 + 产线 objects 数据分区。没有就只在本地临时实例跑（`funcher's tools/deploy' 有样例 seed path）。

## 红线（上家留话，下家守则）

1. **禁止整目录覆盖发布**（历史五连惨案、FL-D1122 已立法）：发布=逐文件 sha 对缝（产 sha → 候选 → 差意 → frontend 带否） + `frontend/*` 默认拒发（备用 `/usr/local/sbin/fundlex-publish` 硬闸）。
2. 后端引擎非正式转正，跨版本对比指引、勘误版文字比对、修订人展示、飞书域接通，这五件是最近手工回补过的，谁动了产线就重新对逢。
3. '选择版本'必须给错误码人话（FUNDLEX_STATUS_LABELS 随行）;**不允许后台裸码露给用户**（严守用户"只要没有报错就显示完成"口径）。
4. 评测/测试发布闸：@用户 = 最后签拍权（FL-D1119)。

## 现产残欠（主线自认，不冒称完备）

- `tasks.py` FL-D1089 双修法未决（产线已用吞吐 grown original_size 归一口径，主线有另一侯选）。
- 集成树的 pending docx 三修/D2 后波，未到 GO 前不得随功机动服务。
- 字对一线一线勾结：qa-base 此分支把主线代码作为标准产线快照当下位，**后续以该分支为法令基点**;其他施工线请对回这条分支做 3-way，别再超产线上作业。

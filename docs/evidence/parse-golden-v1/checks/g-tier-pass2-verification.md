# A2 G 层 pass-2 主标注核验报告（fee-rule-v2，2026-11-01，主审计）

- 输入：pass-1 盲读草案 /tmp/opencode/qa/g-tier-pass1-fee-rule-v2-draft.json（17 条，subagent 自证只用 text-extract.json）。
- 方法：全文程序化核验——每条 old/new preview 对 source_paragraph_span 锚定核对（清晰化：U+FFF9 属 Cf 非 Co，初轮核验误报 12 处已修正）；覆盖扫描认收 span 无遗漏（≥23 段落全覆盖）；分支标注（单类）/（多类）为标注员加注前缀，非指引原文，已识别。
- 结果：17/17 锚定成立；唯一实质瑕疵 R15 preview 把指引引号外上下文拼入（指向原文 135 段引语「由于本基金A类基金份额和C类基金份额费用收取不同」），finalize 时按原文收束。
- ambiguity 7 项照单收（入 rules-gold 的 ambiguity 字段，不删不改）。
- 裁决：pass-1 草案可作为 finalize 基底；R15 修正 + 全文 sha 锚定后冻结。

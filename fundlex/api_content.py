"""Static, server-owned content served by the API (upload-entry copy).

Keeping user-facing specification text here lets the frontend render it
verbatim while the copy ships versioned with the backend quality channel it
describes.  No behaviour, only content.
"""
from __future__ import annotations

GUIDE_UPLOAD_SPEC = {
    "schema_version": "guide-upload-spec-v1",
    "title": "指引上传规格说明",
    "supported_forms": [
        {"form": "DOCX（.docx，Word 2007 及以上格式）",
         "note": "逐段读取正文文本；加粗/红色用于识别指引块结构；不接受扫描件或纯图片文档"},
        {"form": "单个指引文件",
         "note": "一次上传一个指引；多份指引请分别上传、分别解析认证"},
    ],
    "granularity_advice": [
        "一条指引义务对应一个明确的「原条款 → 新条款 / 删除」指令块；不要把多条独立义务合写在同一段落串里",
        "同一主题的多分支（如单份额/多份额、是否收取销售服务费、是否浮动管理费）请写成带条件前缀的并列段落（如「如果…则…」「产品仅有一个份额类别时…」）",
        "新条款与旧条款文本必须逐字写清：解析校验不接受转述或省略号",
        "保持指引原文顺序，不要跨块前后引用合并；「同前述说明」式引用会被独立核验标记",
        "指引块建议用加粗标题或「原条款/新条款/如果…」式标签开头，便于块级解析报告定位",
    ],
    "common_failure_modes": [
        {"code": "GUIDE_SOURCE_UNREADABLE",
         "zh": "文件无法读取或不是有效 DOCX", "remedy": "用 Word 另存为标准 .docx 后重新上传"},
        {"code": "GUIDE_TEXT_NOT_VERBATIM",
         "zh": "解析出的条款文本未逐字取自指引原文", "remedy": "核对提示块中的原文标点后重新上传解析"},
        {"code": "GUIDE_SLOT_NOT_IN_TEXT",
         "zh": "份额类别槽位词未出现在新条款文本中（多为指引原文笔误）",
         "remedy": "修正指引原文后重新上传"},
        {"code": "GUIDE_VALIDATION_UNCLEAN",
         "zh": "解析未通过确定性校验或独立核验", "remedy": "按版本详情中的块解析报告逐块修正后重新上传"},
        {"code": "GUIDE_OPERATION_REGISTRY_MISSING",
         "zh": "解析把多个义务合并成无法执行的粗粒度规则，或引入了尚未注册的新政策",
         "remedy": "按块报告改写为「一条义务一个指令块」；确属新规政策请联系支持做注册扩展"},
        {"code": "GUIDE_NOT_CERTIFIED",
         "zh": "版本尚未通过认证或被标记为需要复核", "remedy": "查看版本详情中的复核维度与块报告"},
        {"code": "GUIDE_CONTEXT_LIMIT",
         "zh": "指引文本超出单次解析容量", "remedy": "拆分指引为多个文件分别上传"},
    ],
    "lifecycle": [
        {"stage": "上传", "note": "文件入库排队，版本状态 uploaded"},
        {"stage": "解析", "note": "解析→确定性校验→独立核验（有界修复），与内置指引同一质量通道"},
        {"stage": "认证", "note": "确定性干净 + 可执行性金丝雀通过才可认证；不通过则标记 needs_review 进复核列表，说明具体原因"},
        {"stage": "启用", "note": "仅认证通过版本可启用；重解析恒产生新版本，需重新认证，历史版本不可变"},
    ],
    "parse_report_fields": {
        "blocks": "按指引块列出解析结果：parsed 成功 / split 被拆分（结构正常）/ merged 被合并（粒度过粗）/ uncovered 未覆盖（内容丢失）/ error 该块解析存在错误 / unparsed 未完成解析",
        "reason_zh": "该块状态的人读原因",
        "remedy_zh": "建议的修正动作",
    },
}

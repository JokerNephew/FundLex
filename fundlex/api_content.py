"""Static, server-owned content served by the API (upload-entry copy).

Keeping user-facing specification text here lets the frontend render it
verbatim while the copy ships versioned with the backend quality channel it
describes.  No behaviour, only content.
"""
from __future__ import annotations

GUIDE_UPLOAD_SPEC = {
    "schema_version": "guide-upload-spec-v2",
    "title": "指引上传规格说明",
    "supported_forms": [
        {"form": "DOCX（.docx，Word 2007 及以上格式）",
         "note": "逐段读取正文文本；不接受扫描件或纯图片文档"},
        {"form": "单个指引文件",
         "note": "一次上传一个指引；多份指引请分别上传、分别解析"},
    ],
    "granularity_advice": [
        "一条指引义务对应一个明确的修改指令（改哪一处、改成什么）；不要把多条独立义务合写在同一段落串里",
        "同一主题的多分支（如单份额/多份额、是否收取销售服务费）请写成带条件前缀的并列段落（如「如果…则…」「产品仅有一个份额类别时…」），每个分支会被解析成独立的指引卡",
        "写清修改涉及的合同章节和原文线索（原条款写法或关键引句），便于在合同中准确定位",
        "保持指引原文顺序，按「事项小标题 + 适用条件 + 修改要求」组织，便于逐项核对解析结果",
    ],
    "common_failure_modes": [
        {"code": "GUIDE_SOURCE_UNREADABLE",
         "zh": "文件无法读取或不是有效 DOCX", "remedy": "用 Word 另存为标准 .docx 后重新上传"},
        {"code": "GUIDE_SOURCE_EMPTY",
         "zh": "文件中没有可读取的正文文本", "remedy": "确认指引正文为可编辑文字（非扫描图片）后重新上传"},
        {"code": "GUIDE_CARD_MODEL_FAILED",
         "zh": "解析服务暂时不可用，本次未能完成解析", "remedy": "稍后重新解析；多次失败请联系支持"},
        {"code": "GUIDE_NO_EXECUTABLE_CARDS",
         "zh": "解析完成但没有得到任何可执行的指引卡", "remedy": "按上面的写法建议补充明确的修改指令后重新上传"},
        {"code": "GUIDE_CONTEXT_LIMIT",
         "zh": "指引文本超出单次解析容量", "remedy": "拆分指引为多个文件分别上传"},
    ],
    "lifecycle": [
        {"stage": "上传", "note": "文件入库排队，状态「待解析」；上传成功不代表解析完成"},
        {"stage": "解析", "note": "自动解析为可执行的指引卡；解析中会逐段读取并生成卡片，可能需要几分钟"},
        {"stage": "启用", "note": "解析成功并形成可执行指引卡后自动成为之后任务的默认指引；解析失败或没有得到可执行卡片时不会启用，可查看失败原因后重新解析"},
    ],
    "parse_report_fields": {
        "cards": "解析出的指引卡：标题、自然语言适用条件、目标章节与定位线索、修改动作及来源段落",
        "unparsed_segments": "未能解析的指引段落（其余卡片不受影响）；属于解析覆盖情况的记录，不需要用户逐条处理",
    },
}

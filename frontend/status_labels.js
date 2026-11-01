/* V1 shared status label tables (loaded before app.js/compare.js/workspace.js).
   各视图可在自己的表里覆盖到本视图措辞；外部未知状态一律显示「—」，不回显原文。 */
(() => {
  'use strict';
  window.FUNDLEX_STATUS_LABELS = Object.freeze({
    uploading: '上传中', queued: '排队中', running: '处理中', leased: '处理中',
    retry_wait: '等待重试', paused: '已暂停', not_started: '尚未接收',
    completed: '处理完成', completed_with_exceptions: '处理结束（含异常）',
    succeeded: '已处理', failed: '处理失败', pending: '未判定',
    complete: '文件已完整交付', incomplete: '结果不完整', not_generated: '未生成',
    complete_with_exceptions: '已交付（部分需人工核对）',
  });
  window.FUNDLEX_GUIDE_STATUSES = Object.freeze({
    uploaded: '待解析', parsing: '解析中', parsed: '已解析', validated: '校验通过',
    parse_failed: '解析失败', failed: '解析失败', released: '已发布', archived: '已归档',
  });
  window.FUNDLEX_STATUS_LABEL = value => window.FUNDLEX_STATUS_LABELS[value] || '—';
})();

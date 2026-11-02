#!/usr/bin/env bash
# FundLex 测试数据清理（使用受限账号 fundlex_ops，前缀白名单+级联差集断言保护）
#
# 安全：只删除 username 匹配 cloud-run-% / cloud-eval-%（p6-% 宽前缀默认不含，
#       需 --include-broad-p6 明示，见③）的账号及其全部关联数据；
#       显式排除 admin；不删其他用户。凭据从 /etc/fundlex-ops.env 读取，不打印密码。
#
# FL-D941 修订要点：
#   ① header 注释前缀与代码一致（cloud-run-% / cloud-eval-% / p6-%[宽，默认不含]）；
#   ② DELETE 按 users.id 级联覆盖 compare/选型/gg/集成/guide_jobs 全部关联表；
#   ③ p6-% 宽前缀须 --include-broad-p6 才进白名单（防模糊前缀误伤真实运维账号）；
#   ④ 删除完成后跑「白名单用户关联行=0」差集断言，非零即 rc=3。
#
# 用法：
#   bash cleanup_test_accounts.sh                          # dry-run 列出将删除的内容
#   bash cleanup_test_accounts.sh --apply                  # 实际执行删除（不含 p6-%）
#   bash cleanup_test_accounts.sh --apply --include-broad-p6
set -euo pipefail

ENV_FILE="/etc/fundlex-ops.env"
[ -r "${ENV_FILE}" ] || { echo "ERROR: 无法读取 ${ENV_FILE}" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

APPLY=0
INCLUDE_BROAD_P6=0
for arg in "$@"; do
  case "${arg}" in
    --apply) APPLY=1 ;;
    --include-broad-p6) INCLUDE_BROAD_P6=1 ;;
    *) echo "ERROR: 未知参数 ${arg}" >&2; exit 2 ;;
  esac
done

URL="${FUNDLEX_OPS_DATABASE_URL:?missing}"
USER="$(echo "${URL}" | sed -E 's#mysql://([^:]+):.*#\1#')"
PASS="$(echo "${URL}" | sed -E 's#mysql://[^:]+:([^@]+)@.*#\1#')"
HOSTPORT="$(echo "${URL}" | sed -E 's#.*@([^/]+)/.*#\1#')"
HOST="${HOSTPORT%%:*}"; PORT="${HOSTPORT##*:}"
DB="$(echo "${URL}" | sed -E 's#.*/([^/?]+).*#\1#')"

# 白名单：窄前缀默认启用 + 宽前缀 p6-% 须显式参数
PREFIXES="cloud-run-% cloud-eval-%"
if [ "${INCLUDE_BROAD_P6}" -eq 1 ]; then
  PREFIXES="${PREFIXES} p6-%"
else
  echo "注意：宽前缀 p6-% 默认排除（--include-broad-p6 才纳入），防止误伤真实运维账号" >&2
fi
WHERE="("
FIRST=1
for p in ${PREFIXES}; do
  if [ "${FIRST}" -eq 0 ]; then WHERE="${WHERE} OR"; fi
  WHERE="${WHERE} u.username LIKE '${p}'"
  FIRST=0
done
WHERE="${WHERE} ) AND u.username <> 'admin'"

MYSQL=(mysql -h "${HOST}" -P "${PORT}" -u "${USER}" "${DB}")
export MYSQL_PWD="${PASS}"

has_table() {
  "${MYSQL[@]}" -N -e "SHOW TABLES LIKE '$1'" 2>/dev/null | grep -qx "$1"
}

echo "== 将处理的目标账号 =="
"${MYSQL[@]}" -t -e "SELECT id, username, created_at FROM users u WHERE ${WHERE};"

if [ "${APPLY}" -eq 0 ]; then
  echo "(dry-run；加 --apply 才实际删除；p6-% 另行需 --include-broad-p6)"
  exit 0
fi

# 差集断言所需快照：删除前的目标账号 id 清单（删 user 之后按前缀已查不到）
TARGET_IDS="$("${MYSQL[@]}" -N -e "SELECT GROUP_CONCAT(CONCAT('''', id, '''') SEPARATOR ',') FROM users u WHERE ${WHERE};")"
if [ -z "${TARGET_IDS}" ]; then
  echo "cleanup done：无常清理目标，差集断言=0。"
  exit 0
fi

"${MYSQL[@]}" <<SQL
START TRANSACTION;
-- compare（pair→task→owner 三级链）
DELETE x FROM compare_artifacts x
  JOIN compare_pairs p ON x.pair_id=p.id
  JOIN compare_tasks t ON p.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE x FROM compare_selection_artifacts x
  JOIN compare_pairs p ON x.pair_id=p.id
  JOIN compare_tasks t ON p.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE x FROM compare_selection_drafts x
  JOIN compare_pairs p ON x.pair_id=p.id
  JOIN compare_tasks t ON p.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE x FROM compare_pair_files x
  JOIN compare_pairs p ON x.pair_id=p.id
  JOIN compare_tasks t ON p.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE p FROM compare_pairs p
  JOIN compare_tasks t ON p.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE t FROM compare_tasks t JOIN users u ON t.owner=u.id WHERE ${WHERE};
-- gg 系（run→owner）
DELETE x FROM gg_model_calls x JOIN gg_runs r ON x.run_id=r.id
  JOIN users u ON r.owner=u.id WHERE ${WHERE};
DELETE x FROM gg_steps x JOIN gg_runs r ON x.run_id=r.id
  JOIN users u ON r.owner=u.id WHERE ${WHERE};
DELETE x FROM gg_artifacts x JOIN gg_runs r ON x.run_id=r.id
  JOIN users u ON r.owner=u.id WHERE ${WHERE};
DELETE x FROM gg_jobs x JOIN gg_runs r ON x.run_id=r.id
  JOIN users u ON r.owner=u.id WHERE ${WHERE};
-- gg 候选面（无 run 挂点时按 owner 直接清）
DELETE c FROM gg_candidate_guides c JOIN users u ON c.owner=u.id WHERE ${WHERE};
DELETE r FROM gg_runs r JOIN users u ON r.owner=u.id WHERE ${WHERE};
-- 集成/飞书面
DELETE x FROM external_identities x JOIN users u ON x.user_id=u.id WHERE ${WHERE};
DELETE x FROM integration_binding_codes x JOIN users u ON x.user_id=u.id WHERE ${WHERE};
DELETE x FROM integration_oauth_states x JOIN users u ON x.user_id=u.id WHERE ${WHERE};
DELETE x FROM task_channels x JOIN users u ON x.owner_user_id=u.id WHERE ${WHERE};
DELETE x FROM feishu_draft_files x JOIN feishu_drafts d ON x.draft_id=d.id
  JOIN users u ON d.owner_user_id=u.id WHERE ${WHERE};
DELETE x FROM feishu_drafts x JOIN users u ON x.owner_user_id=u.id WHERE ${WHERE};
-- 指引解析作业（owner）
DELETE x FROM guide_jobs x JOIN users u ON x.owner=u.id WHERE ${WHERE};
-- 历史主线面（保留原语义）
DELETE a FROM artifacts a JOIN documents d ON a.document_id=d.id
  JOIN task_batches tb ON d.batch_id=tb.batch_id
  JOIN tasks t ON tb.task_id=t.id JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE d FROM documents d
  JOIN task_batches tb ON d.batch_id=tb.batch_id
  JOIN tasks t ON tb.task_id=t.id JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE tb FROM task_batches tb JOIN tasks t ON tb.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE b FROM batches b JOIN users u ON b.owner=u.id WHERE ${WHERE};
DELETE tf FROM task_files tf JOIN tasks t ON tf.task_id=t.id
  JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE t FROM tasks t JOIN users u ON t.owner=u.id WHERE ${WHERE};
DELETE s FROM sessions s JOIN users u ON s.user_id=u.id WHERE ${WHERE};
DELETE FROM users u WHERE ${WHERE};
COMMIT;
SQL

# ④ 差集断言：按删除前快照 id 全表复查——残留任何一行都视为清理失败
RESIDUAL=$("${MYSQL[@]}" -N -e "
SELECT SUM(n) FROM (
  SELECT COUNT(*) AS n FROM tasks t WHERE t.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM task_batches tb JOIN tasks t ON tb.task_id=t.id AND t.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM batches b WHERE b.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM task_files tf JOIN tasks t ON tf.task_id=t.id AND t.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM sessions s WHERE s.user_id IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM compare_tasks t WHERE t.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM compare_pair_files f JOIN compare_pairs p ON f.pair_id=p.id
         JOIN compare_tasks t ON p.task_id=t.id AND t.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM gg_runs r WHERE r.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM gg_model_calls m JOIN gg_runs r ON m.run_id=r.id AND r.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM gg_jobs j JOIN gg_runs r ON j.run_id=r.id AND r.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM external_identities x WHERE x.user_id IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM task_channels x WHERE x.owner_user_id IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM feishu_drafts x WHERE x.owner_user_id IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM feishu_draft_files x JOIN feishu_drafts d ON x.draft_id=d.id AND d.owner_user_id IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM guide_jobs x WHERE x.owner IN (${TARGET_IDS})
  UNION ALL SELECT COUNT(*) FROM users u WHERE u.id IN (${TARGET_IDS})
) AS residual_set;")
if [ "${RESIDUAL:-1}" != "0" ]; then
  echo "CLEAR FAILED: 白名单用户残留关联行=${RESIDUAL}（FL-D941 差集断言）" >&2
  exit 3
fi
echo "cleanup done：测试账号及关联数据已清除，差集断言=0。"

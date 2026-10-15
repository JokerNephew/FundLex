#!/usr/bin/env bash
# FundLex 测试数据清理（使用受限账号 fundlex_ops，前缀白名单保护）
#
# 安全：只删除 username 匹配 cloud-% / p6-% / cloud-eval-% 的账号及其关联数据；
#       显式排除 admin；不删其他用户。凭据从 /etc/fundlex-ops.env 读取，不打印密码。
#
# 用法：
#   bash cleanup_test_accounts.sh            # 只列出将删除的内容（dry-run）
#   bash cleanup_test_accounts.sh --apply    # 实际执行删除
set -euo pipefail

ENV_FILE="/etc/fundlex-ops.env"
[ -r "${ENV_FILE}" ] || { echo "ERROR: 无法读取 ${ENV_FILE}" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

URL="${FUNDLEX_OPS_DATABASE_URL:?missing}"
USER="$(echo "${URL}" | sed -E 's#mysql://([^:]+):.*#\1#')"
PASS="$(echo "${URL}" | sed -E 's#mysql://[^:]+:([^@]+)@.*#\1#')"
HOSTPORT="$(echo "${URL}" | sed -E 's#.*@([^/]+)/.*#\1#')"
HOST="${HOSTPORT%%:*}"; PORT="${HOSTPORT##*:}"
DB="$(echo "${URL}" | sed -E 's#.*/([^/?]+).*#\1#')"

# 白名单：只允许这些前缀（admin 永不在内）
PREFIXES="cloud-run-% cloud-eval-% p6-%"
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

echo "== 将处理的目标账号 =="
"${MYSQL[@]}" -t -e "SELECT id, username, created_at FROM users u WHERE ${WHERE};"

if [ "${1:-}" != "--apply" ]; then
  echo "(dry-run；加 --apply 才实际删除)"
  exit 0
fi

"${MYSQL[@]}" <<SQL
START TRANSACTION;
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
SELECT 'done' AS status;
SQL
echo "已删除上述测试账号及其关联数据。"

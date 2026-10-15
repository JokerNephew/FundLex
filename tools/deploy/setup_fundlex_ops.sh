#!/usr/bin/env bash
# FundLex 受限运维账号安装脚本（方案1）—— 必须由 root 执行
#
# 目的：给 opencode 用户（及其他 agent）一个 3307 的受限账号，用于
#       ① 只读查询（对账/评测排查）② 受控清理测试账号与任务。
# 安全：不授予 DROP/ALTER/CREATE/USERT；不授予 INSERT/UPDATE（不污染业务数据）；
#       不包含 LLM key；凭据仅写入 root:opencode 640 文件。
#
# 用法（服务器上以 root 运行）：
#   bash setup_fundlex_ops.sh
#
# 撤销：
#   rm -f /etc/fundlex-ops.env
#   mysql --defaults-file=/etc/fundlex-mysql.cnf -u root -e \
#     "DROP USER IF EXISTS 'fundlex_ops'@'127.0.0.1'; FLUSH PRIVILEGES;"
set -euo pipefail

OPS_USER="fundlex_ops"
OPS_HOST="127.0.0.1"
DB="fundlex"
ENV_FILE="/etc/fundlex-ops.env"

OPS_PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
MYSQL_ROOT=(mysql --defaults-file=/etc/fundlex-mysql.cnf -u root)

"${MYSQL_ROOT[@]}" <<SQL
CREATE USER IF NOT EXISTS '${OPS_USER}'@'${OPS_HOST}' IDENTIFIED BY '${OPS_PASS}';
ALTER USER '${OPS_USER}'@'${OPS_HOST}' IDENTIFIED BY '${OPS_PASS}';

-- 全库只读
GRANT SELECT ON \`${DB}\`.* TO '${OPS_USER}'@'${OPS_HOST}';

-- 受控清理所需的最小 DELETE 权限（不含 INSERT/UPDATE/DROP/ALTER/CREATE）
-- 保护策略由调用侧 SQL 强制 username LIKE 'cloud-%' / 'p6-%' / 'cloud-eval-%' 前缀，
-- 且显式排除 admin。
GRANT DELETE ON \`${DB}\`.\`sessions\`     TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`artifacts\`    TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`documents\`    TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`task_batches\` TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`batches\`      TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`task_files\`   TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`tasks\`        TO '${OPS_USER}'@'${OPS_HOST}';
GRANT DELETE ON \`${DB}\`.\`users\`        TO '${OPS_USER}'@'${OPS_HOST}';
FLUSH PRIVILEGES;
SQL

umask 077
cat > "${ENV_FILE}" <<ENV
# FundLex 受限运维账号（只读 + 测试数据清理）—— 由 setup_fundlex_ops.sh 生成
FUNDLEX_OPS_DATABASE_URL=mysql://${OPS_USER}:${OPS_PASS}@127.0.0.1:3307/${DB}?charset=utf8mb4
FUNDLEX_OPS_USER=${OPS_USER}
ENV
chown root:opencode "${ENV_FILE}"
chmod 640 "${ENV_FILE}"

echo "OK: 已创建 ${OPS_USER}@${OPS_HOST}，凭据写入 ${ENV_FILE} (root:opencode 640)"

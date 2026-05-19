package com.dbdoctor;

import java.sql.SQLException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class DiagnosisService {
    private final DoctorConfig config;
    private DatabaseClient db;

    public DiagnosisService(DoctorConfig config) {
        this.config = config;
    }

    public DiagnosticSummary run() {
        try (DbClient client = DbClient.connect(config)) {
            return run(client);
        } catch (Exception e) {
            DiagnosticSummary summary = new DiagnosticSummary();
            summary.databaseTarget = config.databaseTarget();
            summary.addResult(DiagnosticResult.error("connect_database", "数据库连接", e));
            return summary;
        }
    }

    public DiagnosticSummary run(DatabaseClient client) {
        DiagnosticSummary summary = new DiagnosticSummary();
        summary.databaseTarget = config.databaseTarget();
        this.db = client;
        summary.addResult(check("basic_info", "基础信息", this::basicInfo));
        summary.addResult(check("key_settings", "关键参数", this::keySettings));
        summary.addResult(check("connection_usage", "连接使用率", this::connectionUsage));
        summary.addResult(check("connection_distribution", "连接分布", this::connectionDistribution));
        summary.addResult(check("whitelist_anomalies", "白名单异常", this::whitelistAnomalies));
        summary.addResult(check("long_queries", "慢 SQL", this::longQueries));
        summary.addResult(check("long_transactions", "长事务", this::longTransactions));
        summary.addResult(check("idle_in_transaction", "空闲未提交事务", this::idleInTransaction));
        summary.addResult(check("lock_waits", "锁等待与阻塞链", this::lockWaits));
        summary.addResult(check("thread_waits", "线程等待状态", this::threadWaits));
        summary.addResult(check("deadlocks", "死锁计数", this::deadlocks));
        summary.addResult(check("risky_roles", "用户与权限风险", this::riskyRoles));
        summary.addResult(check("recent_ddl_dcl", "最近 DDL/DCL 审计", this::recentDdlDcl));
        return summary;
    }

    private DiagnosticResult check(String id, String title, CheckedCheck checkedCheck) {
        try {
            return checkedCheck.run();
        } catch (Exception e) {
            return DiagnosticResult.error(id, title, e);
        }
    }

    private DiagnosticResult basicInfo() throws SQLException {
        String sql = "SELECT version() AS version,\n"
                + "       current_database() AS database_name,\n"
                + "       current_user AS current_user,\n"
                + "       now() AS checked_at";
        QueryResult qr = db.query(sql);
        DiagnosticResult result = DiagnosticResult.of("basic_info", "基础信息", Severity.OK, "数据库连接正常，基础信息已采集", qr);
        result.observations.add("用于确认当前连接目标、账号和数据库版本。");
        return result;
    }

    private DiagnosticResult keySettings() throws SQLException {
        String sql = "SELECT name, setting, unit, vartype, context\n"
                + "FROM pg_settings\n"
                + "WHERE name IN (\n"
                + "    'max_connections',\n"
                + "    'superuser_reserved_connections',\n"
                + "    'audit_enabled',\n"
                + "    'audit_system_object',\n"
                + "    'audit_dml_state',\n"
                + "    'audit_dml_state_select',\n"
                + "    'log_statement',\n"
                + "    'track_activities',\n"
                + "    'statement_timeout',\n"
                + "    'session_timeout'\n"
                + ")\n"
                + "ORDER BY name";
        QueryResult qr = db.query(sql);
        Severity severity = Severity.OK;
        List<String> auditProblems = qr.rows.stream()
                .filter(row -> "audit_enabled".equalsIgnoreCase(row.get("name"))
                        && isOff(row.get("setting")))
                .map(row -> "audit_enabled=" + row.get("setting"))
                .collect(Collectors.toList());
        if (!auditProblems.isEmpty()) {
            severity = Severity.WARNING;
        }
        DiagnosticResult result = DiagnosticResult.of("key_settings", "关键参数", severity,
                severity == Severity.OK ? "关键参数已采集，未发现明显配置风险" : "审计相关参数可能未开启", qr);
        result.observations.add("这里只读取参数，不执行 SET/ALTER SYSTEM。");
        if (!auditProblems.isEmpty()) {
            result.observations.add("发现审计参数异常: " + String.join(", ", auditProblems));
        }
        return result;
    }

    private DiagnosticResult connectionUsage() throws SQLException {
        String sql = "SELECT current_connections::bigint AS current_connections,\n"
                + "       max_connections::bigint AS max_connections,\n"
                + "       round(current_connections * 100.0 / nullif(max_connections, 0), 2) AS usage_percent\n"
                + "FROM (\n"
                + "    SELECT count(*)::numeric AS current_connections\n"
                + "    FROM pg_stat_activity\n"
                + ") c,\n"
                + "(\n"
                + "    SELECT setting::numeric AS max_connections\n"
                + "    FROM pg_settings\n"
                + "    WHERE name = 'max_connections'\n"
                + ") m";
        QueryResult qr = db.query(sql);
        Map<String, String> row = qr.firstRow();
        double usagePercent = number(row, "usage_percent", 0);
        double warningPercent = config.thresholds.connectionUsageWarning * 100.0;
        double criticalPercent = config.thresholds.connectionUsageCritical * 100.0;
        Severity severity = usagePercent >= criticalPercent
                ? Severity.CRITICAL
                : usagePercent >= warningPercent ? Severity.WARNING : Severity.OK;
        String conclusion;
        switch (severity) {
            case CRITICAL:
                conclusion = "连接使用率已达到严重阈值";
                break;
            case WARNING:
                conclusion = "连接使用率偏高";
                break;
            default:
                conclusion = "连接使用率正常";
                break;
        }
        DiagnosticResult result = DiagnosticResult.of("connection_usage", "连接使用率", severity, conclusion, qr);
        result.observations.add("当前连接使用率: " + usagePercent + "%，预警阈值: " + warningPercent + "%，严重阈值: " + criticalPercent + "%。");
        return result;
    }

    private DiagnosticResult connectionDistribution() throws SQLException {
        String sql = String.format("SELECT coalesce(usename, '<internal>') AS username,\n"
                + "       coalesce(client_addr::text, 'local') AS client_addr,\n"
                + "       coalesce(state, 'unknown') AS state,\n"
                + "       count(*)::bigint AS connections\n"
                + "FROM pg_stat_activity\n"
                + "GROUP BY coalesce(usename, '<internal>'), coalesce(client_addr::text, 'local'), coalesce(state, 'unknown')\n"
                + "ORDER BY connections DESC, username, client_addr, state\n"
                + "LIMIT %d", limit());
        QueryResult qr = db.query(sql);
        long total = qr.rows.stream().mapToLong(row -> longNumber(row, "connections", 0)).sum();
        long largest = qr.rows.stream().mapToLong(row -> longNumber(row, "connections", 0)).max().orElse(0);
        Severity severity = total > 0 && largest >= Math.max(10, Math.round(total * 0.80)) ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("connection_distribution", "连接分布", severity,
                severity == Severity.OK ? "连接分布已采集" : "存在单一用户/IP/状态占比过高的连接分布", qr);
        result.observations.add("按用户、客户端 IP 和会话状态聚合连接，用于快速定位连接来源。");
        return result;
    }

    private DiagnosticResult whitelistAnomalies() throws SQLException {
        String sql = String.format("SELECT pid,\n"
                + "       coalesce(usename, '<internal>') AS username,\n"
                + "       coalesce(client_addr::text, 'local') AS client_addr,\n"
                + "       coalesce(application_name, '') AS application_name,\n"
                + "       coalesce(state, 'unknown') AS state,\n"
                + "       backend_start,\n"
                + "       query_start,\n"
                + "       xact_start,\n"
                + "       query\n"
                + "FROM pg_stat_activity\n"
                + "ORDER BY backend_start DESC\n"
                + "LIMIT %d", limit());
        QueryResult qr = db.query(sql);
        DiagnosticResult result;
        if (!config.whitelist.enabled) {
            result = DiagnosticResult.of("whitelist_anomalies", "白名单异常", Severity.OK, "白名单检查未开启，已保留原始会话清单", qr);
            result.observations.add("如需启用，在 yml 中设置 whitelist.enabled=true。");
            return result;
        }
        Set<String> userWhitelist = config.whitelist.users.stream()
                .filter(value -> !isBlank(value))
                .map(value -> value.toLowerCase(Locale.ROOT))
                .collect(Collectors.toSet());
        IpWhitelist ipWhitelist = new IpWhitelist(config.whitelist.clientIps);
        List<String> anomalies = qr.rows.stream()
                .filter(row -> {
                    String username = row.getOrDefault("username", "").toLowerCase(Locale.ROOT);
                    String clientAddr = row.get("client_addr");
                    boolean badUser = !userWhitelist.isEmpty() && !userWhitelist.contains(username);
                    boolean badIp = !ipWhitelist.contains(clientAddr);
                    return badUser || badIp;
                })
                .map(row -> row.get("username") + "@" + row.get("client_addr") + " pid=" + row.get("pid"))
                .collect(Collectors.toList());
        Severity severity = anomalies.isEmpty() ? Severity.OK : Severity.WARNING;
        result = DiagnosticResult.of("whitelist_anomalies", "白名单异常", severity,
                anomalies.isEmpty() ? "未发现非白名单会话" : "发现非白名单用户或来源 IP", qr);
        anomalies.stream().limit(20).forEach(item -> result.observations.add("异常会话: " + item));
        return result;
    }

    private DiagnosticResult longQueries() throws SQLException {
        String sql = String.format("SELECT pid,\n"
                + "       usename AS username,\n"
                + "       datname AS database_name,\n"
                + "       coalesce(client_addr::text, 'local') AS client_addr,\n"
                + "       state,\n"
                + "       round(extract(epoch FROM now() - query_start))::bigint AS duration_seconds,\n"
                + "       query_start,\n"
                + "       query\n"
                + "FROM pg_stat_activity\n"
                + "WHERE state = 'active'\n"
                + "  AND query_start IS NOT NULL\n"
                + "  AND now() - query_start > interval '%d seconds'\n"
                + "ORDER BY query_start ASC\n"
                + "LIMIT %d", config.thresholds.longQuerySeconds, limit());
        QueryResult qr = db.query(sql);
        Severity severity = qr.rowCount() > 0 ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("long_queries", "慢 SQL", severity,
                severity == Severity.OK ? "未发现超过阈值的活跃 SQL" : "发现运行时间超过阈值的活跃 SQL", qr);
        result.observations.add("慢 SQL 阈值: " + config.thresholds.longQuerySeconds + " 秒。");
        result.observations.add("报告保留完整 query 文本，便于比赛时直接定位。");
        return result;
    }

    private DiagnosticResult longTransactions() throws SQLException {
        String sql = String.format("SELECT pid,\n"
                + "       usename AS username,\n"
                + "       datname AS database_name,\n"
                + "       coalesce(client_addr::text, 'local') AS client_addr,\n"
                + "       state,\n"
                + "       round(extract(epoch FROM now() - xact_start))::bigint AS transaction_seconds,\n"
                + "       xact_start,\n"
                + "       query_start,\n"
                + "       query\n"
                + "FROM pg_stat_activity\n"
                + "WHERE xact_start IS NOT NULL\n"
                + "  AND now() - xact_start > interval '%d seconds'\n"
                + "ORDER BY xact_start ASC\n"
                + "LIMIT %d", config.thresholds.longTransactionSeconds, limit());
        QueryResult qr = db.query(sql);
        long maxSeconds = qr.rows.stream().mapToLong(row -> longNumber(row, "transaction_seconds", 0)).max().orElse(0);
        Severity severity = qr.rowCount() == 0 ? Severity.OK :
                maxSeconds >= config.thresholds.longTransactionSeconds * 5L ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("long_transactions", "长事务", severity,
                severity == Severity.OK ? "未发现超过阈值的长事务" : "发现长事务，需要关注未提交事务造成的锁和膨胀风险", qr);
        result.observations.add("长事务阈值: " + config.thresholds.longTransactionSeconds + " 秒。");
        return result;
    }

    private DiagnosticResult idleInTransaction() throws SQLException {
        String sql = String.format("SELECT pid,\n"
                + "       usename AS username,\n"
                + "       datname AS database_name,\n"
                + "       coalesce(client_addr::text, 'local') AS client_addr,\n"
                + "       state,\n"
                + "       round(extract(epoch FROM now() - state_change))::bigint AS idle_seconds,\n"
                + "       xact_start,\n"
                + "       state_change,\n"
                + "       query\n"
                + "FROM pg_stat_activity\n"
                + "WHERE state = 'idle in transaction'\n"
                + "  AND state_change IS NOT NULL\n"
                + "  AND now() - state_change > interval '%d seconds'\n"
                + "ORDER BY state_change ASC\n"
                + "LIMIT %d", config.thresholds.idleInTransactionSeconds, limit());
        QueryResult qr = db.query(sql);
        long maxSeconds = qr.rows.stream().mapToLong(row -> longNumber(row, "idle_seconds", 0)).max().orElse(0);
        Severity severity = qr.rowCount() == 0 ? Severity.OK :
                maxSeconds >= config.thresholds.idleInTransactionSeconds * 5L ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("idle_in_transaction", "空闲未提交事务", severity,
                severity == Severity.OK ? "未发现超过阈值的 idle in transaction 会话" : "发现空闲未提交事务，可能持有锁或阻碍清理", qr);
        result.observations.add("idle in transaction 阈值: " + config.thresholds.idleInTransactionSeconds + " 秒。");
        return result;
    }

    private DiagnosticResult lockWaits() throws SQLException {
        String sql = String.format("SELECT blocked.pid AS blocked_pid,\n"
                + "       blocked_activity.usename AS blocked_user,\n"
                + "       coalesce(blocked_activity.client_addr::text, 'local') AS blocked_client,\n"
                + "       round(extract(epoch FROM now() - blocked_activity.query_start))::bigint AS blocked_wait_seconds,\n"
                + "       blocking.pid AS blocking_pid,\n"
                + "       blocking_activity.usename AS blocking_user,\n"
                + "       coalesce(blocking_activity.client_addr::text, 'local') AS blocking_client,\n"
                + "       blocked.mode AS blocked_mode,\n"
                + "       blocking.mode AS blocking_mode,\n"
                + "       blocked.locktype AS locktype,\n"
                + "       blocked_activity.query AS blocked_query,\n"
                + "       blocking_activity.query AS blocking_query\n"
                + "FROM pg_locks blocked\n"
                + "JOIN pg_stat_activity blocked_activity ON blocked_activity.pid = blocked.pid\n"
                + "JOIN pg_locks blocking\n"
                + "  ON blocking.locktype = blocked.locktype\n"
                + " AND blocking.database IS NOT DISTINCT FROM blocked.database\n"
                + " AND blocking.relation IS NOT DISTINCT FROM blocked.relation\n"
                + " AND blocking.page IS NOT DISTINCT FROM blocked.page\n"
                + " AND blocking.tuple IS NOT DISTINCT FROM blocked.tuple\n"
                + " AND blocking.virtualxid IS NOT DISTINCT FROM blocked.virtualxid\n"
                + " AND blocking.transactionid IS NOT DISTINCT FROM blocked.transactionid\n"
                + " AND blocking.classid IS NOT DISTINCT FROM blocked.classid\n"
                + " AND blocking.objid IS NOT DISTINCT FROM blocked.objid\n"
                + " AND blocking.objsubid IS NOT DISTINCT FROM blocked.objsubid\n"
                + " AND blocking.pid <> blocked.pid\n"
                + "JOIN pg_stat_activity blocking_activity ON blocking_activity.pid = blocking.pid\n"
                + "WHERE NOT blocked.granted\n"
                + "  AND blocking.granted\n"
                + "ORDER BY blocked_activity.query_start ASC\n"
                + "LIMIT %d", limit());
        QueryResult qr = db.query(sql);
        long maxSeconds = qr.rows.stream().mapToLong(row -> longNumber(row, "blocked_wait_seconds", 0)).max().orElse(0);
        Severity severity = qr.rowCount() == 0 ? Severity.OK :
                maxSeconds >= config.thresholds.lockWaitSeconds ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("lock_waits", "锁等待与阻塞链", severity,
                severity == Severity.OK ? "未发现当前锁等待阻塞链" : "发现锁等待阻塞链", qr);
        result.observations.add("锁等待严重阈值: " + config.thresholds.lockWaitSeconds + " 秒。");
        result.observations.add("这里只展示阻塞关系，不会执行 pg_cancel_backend 或 pg_terminate_backend。");
        return result;
    }

    private DiagnosticResult threadWaits() throws SQLException {
        String sql = String.format("SELECT node_name,\n"
                + "       db_name,\n"
                + "       thread_name,\n"
                + "       tid,\n"
                + "       sessionid,\n"
                + "       wait_status,\n"
                + "       wait_event,\n"
                + "       locktag,\n"
                + "       lockmode,\n"
                + "       block_sessionid\n"
                + "FROM pg_thread_wait_status\n"
                + "WHERE wait_status IS NOT NULL\n"
                + "  AND wait_status <> 'none'\n"
                + "ORDER BY wait_status, tid\n"
                + "LIMIT %d", limit());
        QueryResult qr = db.query(sql);
        boolean lockWait = qr.rows.stream()
                .anyMatch(row -> "acquire lock".equalsIgnoreCase(row.get("wait_status")));
        Severity severity = qr.rowCount() == 0 ? Severity.OK : lockWait ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("thread_waits", "线程等待状态", severity,
                severity == Severity.OK ? "未发现非 none 线程等待状态" : "发现线程等待状态", qr);
        result.observations.add("pg_thread_wait_status 可辅助判断锁、轻量锁、I/O、网络等等待。");
        return result;
    }

    private DiagnosticResult deadlocks() throws SQLException {
        String sql = "SELECT datname AS database_name,\n"
                + "       deadlocks\n"
                + "FROM pg_stat_database\n"
                + "WHERE datname = current_database()";
        QueryResult qr = db.query(sql);
        long deadlocks = qr.rows.stream().mapToLong(row -> longNumber(row, "deadlocks", 0)).sum();
        Severity severity = deadlocks > 0 ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("deadlocks", "死锁计数", severity,
                severity == Severity.OK ? "当前数据库累计死锁计数为 0" : "当前数据库累计死锁计数大于 0", qr);
        result.observations.add("pg_stat_database.deadlocks 是累计值，不等于最近 20 分钟发生过死锁。");
        return result;
    }

    private DiagnosticResult riskyRoles() throws SQLException {
        String sql = String.format("SELECT rolname,\n"
                + "       rolsuper,\n"
                + "       rolsystemadmin,\n"
                + "       rolauditadmin,\n"
                + "       rolmonitoradmin,\n"
                + "       roloperatoradmin,\n"
                + "       rolpolicyadmin,\n"
                + "       rolcreaterole,\n"
                + "       rolcreatedb,\n"
                + "       rolcanlogin,\n"
                + "       rolreplication,\n"
                + "       rolconnlimit,\n"
                + "       rolvalidbegin,\n"
                + "       rolvaliduntil\n"
                + "FROM pg_roles\n"
                + "WHERE rolcanlogin\n"
                + "   OR rolsuper\n"
                + "   OR rolsystemadmin\n"
                + "   OR rolauditadmin\n"
                + "   OR rolmonitoradmin\n"
                + "   OR roloperatoradmin\n"
                + "   OR rolpolicyadmin\n"
                + "   OR rolcreaterole\n"
                + "   OR rolcreatedb\n"
                + "   OR rolreplication\n"
                + "ORDER BY rolsuper DESC,\n"
                + "         rolsystemadmin DESC,\n"
                + "         rolauditadmin DESC,\n"
                + "         rolcreaterole DESC,\n"
                + "         rolcreatedb DESC,\n"
                + "         rolreplication DESC,\n"
                + "         rolname\n"
                + "LIMIT %d", limit());
        QueryResult qr = db.query(sql);
        Severity severity = Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("risky_roles", "用户与权限风险", severity,
                "已列出可登录和高权限角色", qr);
        result.observations.add("默认不把现有高权限账号判定为异常；如开启白名单，会结合 whitelist.users 判断。");
        if (config.whitelist.enabled) {
            Set<String> allowedUsers = config.whitelist.users.stream()
                    .filter(value -> !isBlank(value))
                    .map(value -> value.toLowerCase(Locale.ROOT))
                    .collect(Collectors.toSet());
            List<String> suspicious = qr.rows.stream()
                    .filter(row -> truthy(row.get("rolcanlogin")))
                    .filter(row -> !allowedUsers.contains(row.getOrDefault("rolname", "").toLowerCase(Locale.ROOT)))
                    .map(row -> row.get("rolname"))
                    .collect(Collectors.toList());
            if (!suspicious.isEmpty()) {
                result.severity = Severity.WARNING;
                result.conclusion = "发现非白名单可登录角色";
                suspicious.stream().limit(20).forEach(name -> result.observations.add("非白名单可登录角色: " + name));
            }
        }
        return result;
    }

    private DiagnosticResult recentDdlDcl() throws SQLException {
        int minutes = config.diagnosis.ddlLookbackMinutes;
        String sql = recentDdlDclSql(minutes, limit());
        QueryResult qr = db.query(sql);
        boolean dangerous = qr.rows.stream().anyMatch(row -> isDangerousDdl(row.get("detail_info")));
        Severity severity = qr.rowCount() == 0 ? Severity.OK : dangerous ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("recent_ddl_dcl", "最近 DDL/DCL 审计", severity,
                severity == Severity.OK ? "最近 " + minutes + " 分钟未发现 DDL/DCL 审计记录" : "最近 " + minutes + " 分钟发现 DDL/DCL 审计记录", qr);
        result.observations.add("通过 pg_query_audit 查询审计结果；这里只读取 DDL/DCL 类审计信息。");
        result.observations.add("DROP/TRUNCATE/GRANT/REVOKE/用户权限变更会提升为严重风险。");
        return result;
    }

    static String recentDdlDclSql(int minutes, int limit) {
        return String.format("SELECT t.time,\n"
                + "       t.type,\n"
                + "       t.result,\n"
                + "       t.username,\n"
                + "       t.database,\n"
                + "       t.client_conninfo,\n"
                + "       t.object_name,\n"
                + "       t.detail_info\n"
                + "FROM pg_query_audit(\n"
                + "    (now() - interval '%d minutes')::timestamptz,\n"
                + "    now()::timestamptz\n"
                + ") AS t\n"
                + "WHERE (\n"
                + "       lower(coalesce(t.type, '')) LIKE 'ddl_%%'\n"
                + "    OR lower(coalesce(t.type, '')) LIKE 'dcl_%%'\n"
                + "    OR lower(coalesce(t.type, '')) IN ('login_success', 'login_failed', 'user_logout', 'set_parameter')\n"
                + ")\n"
                + "  AND lower(coalesce(t.type, '')) NOT LIKE 'dml_%%'\n"
                + "ORDER BY t.time DESC\n"
                + "LIMIT %d", minutes, limit);
    }

    private boolean isDangerousDdl(String detail) {
        if (detail == null) {
            return false;
        }
        String upper = detail.toUpperCase(Locale.ROOT);
        return upper.contains("DROP ")
                || upper.contains("TRUNCATE ")
                || upper.contains("GRANT ")
                || upper.contains("REVOKE ")
                || upper.contains("ALTER USER")
                || upper.contains("ALTER ROLE")
                || upper.contains("CREATE USER")
                || upper.contains("CREATE ROLE");
    }

    private int limit() {
        return config.thresholds.maxRowsPerCheck;
    }

    private boolean isOff(String value) {
        return value == null
                || "off".equalsIgnoreCase(value)
                || "false".equalsIgnoreCase(value)
                || "0".equals(value);
    }

    private boolean truthy(String value) {
        return value != null && ("t".equalsIgnoreCase(value)
                || "true".equalsIgnoreCase(value)
                || "on".equalsIgnoreCase(value)
                || "1".equals(value));
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private double number(Map<String, String> row, String key, double fallback) {
        try {
            String value = row.get(key);
            return value == null ? fallback : Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private long longNumber(Map<String, String> row, String key, long fallback) {
        try {
            String value = row.get(key);
            return value == null ? fallback : Long.parseLong(value);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    @FunctionalInterface
    private interface CheckedCheck {
        DiagnosticResult run() throws Exception;
    }
}

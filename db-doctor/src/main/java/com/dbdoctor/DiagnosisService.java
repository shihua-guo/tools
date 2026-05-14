package com.dbdoctor;

import java.sql.SQLException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class DiagnosisService {
    private final DoctorConfig config;
    private DbClient db;

    public DiagnosisService(DoctorConfig config) {
        this.config = config;
    }

    public DiagnosticSummary run() {
        DiagnosticSummary summary = new DiagnosticSummary();
        summary.databaseTarget = config.databaseTarget();
        try (DbClient client = DbClient.connect(config)) {
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
        } catch (Exception e) {
            summary.addResult(DiagnosticResult.error("connect_database", "数据库连接", e));
        }
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
        String sql = """
                SELECT version() AS version,
                       current_database() AS database_name,
                       current_user AS current_user,
                       now() AS checked_at
                """;
        QueryResult qr = db.query(sql);
        DiagnosticResult result = DiagnosticResult.of("basic_info", "基础信息", Severity.OK, "数据库连接正常，基础信息已采集", qr);
        result.observations.add("用于确认当前连接目标、账号和数据库版本。");
        return result;
    }

    private DiagnosticResult keySettings() throws SQLException {
        String sql = """
                SELECT name, setting, unit, vartype, context
                FROM pg_settings
                WHERE name IN (
                    'max_connections',
                    'superuser_reserved_connections',
                    'audit_enabled',
                    'audit_system_object',
                    'audit_dml_state',
                    'audit_dml_state_select',
                    'log_statement',
                    'track_activities',
                    'statement_timeout',
                    'session_timeout'
                )
                ORDER BY name
                """;
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
        String sql = """
                SELECT current_connections::bigint AS current_connections,
                       max_connections::bigint AS max_connections,
                       round(current_connections * 100.0 / nullif(max_connections, 0), 2) AS usage_percent
                FROM (
                    SELECT count(*)::numeric AS current_connections
                    FROM pg_stat_activity
                ) c,
                (
                    SELECT setting::numeric AS max_connections
                    FROM pg_settings
                    WHERE name = 'max_connections'
                ) m
                """;
        QueryResult qr = db.query(sql);
        Map<String, String> row = qr.firstRow();
        double usagePercent = number(row, "usage_percent", 0);
        double warningPercent = config.thresholds.connectionUsageWarning * 100.0;
        double criticalPercent = config.thresholds.connectionUsageCritical * 100.0;
        Severity severity = usagePercent >= criticalPercent
                ? Severity.CRITICAL
                : usagePercent >= warningPercent ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("connection_usage", "连接使用率", severity,
                switch (severity) {
                    case CRITICAL -> "连接使用率已达到严重阈值";
                    case WARNING -> "连接使用率偏高";
                    default -> "连接使用率正常";
                }, qr);
        result.observations.add("当前连接使用率: " + usagePercent + "%，预警阈值: " + warningPercent + "%，严重阈值: " + criticalPercent + "%。");
        return result;
    }

    private DiagnosticResult connectionDistribution() throws SQLException {
        String sql = """
                SELECT coalesce(usename, '<internal>') AS username,
                       coalesce(client_addr::text, 'local') AS client_addr,
                       coalesce(state, 'unknown') AS state,
                       count(*)::bigint AS connections
                FROM pg_stat_activity
                GROUP BY coalesce(usename, '<internal>'), coalesce(client_addr::text, 'local'), coalesce(state, 'unknown')
                ORDER BY connections DESC, username, client_addr, state
                LIMIT %d
                """.formatted(limit());
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
        String sql = """
                SELECT pid,
                       coalesce(usename, '<internal>') AS username,
                       coalesce(client_addr::text, 'local') AS client_addr,
                       coalesce(application_name, '') AS application_name,
                       coalesce(state, 'unknown') AS state,
                       backend_start,
                       query_start,
                       xact_start,
                       query
                FROM pg_stat_activity
                ORDER BY backend_start DESC
                LIMIT %d
                """.formatted(limit());
        QueryResult qr = db.query(sql);
        DiagnosticResult result;
        if (!config.whitelist.enabled) {
            result = DiagnosticResult.of("whitelist_anomalies", "白名单异常", Severity.OK, "白名单检查未开启，已保留原始会话清单", qr);
            result.observations.add("如需启用，在 yml 中设置 whitelist.enabled=true。");
            return result;
        }
        Set<String> userWhitelist = config.whitelist.users.stream()
                .filter(value -> value != null && !value.isBlank())
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
                .toList();
        Severity severity = anomalies.isEmpty() ? Severity.OK : Severity.WARNING;
        result = DiagnosticResult.of("whitelist_anomalies", "白名单异常", severity,
                anomalies.isEmpty() ? "未发现非白名单会话" : "发现非白名单用户或来源 IP", qr);
        anomalies.stream().limit(20).forEach(item -> result.observations.add("异常会话: " + item));
        return result;
    }

    private DiagnosticResult longQueries() throws SQLException {
        String sql = """
                SELECT pid,
                       usename AS username,
                       datname AS database_name,
                       coalesce(client_addr::text, 'local') AS client_addr,
                       state,
                       round(extract(epoch FROM now() - query_start))::bigint AS duration_seconds,
                       query_start,
                       query
                FROM pg_stat_activity
                WHERE state = 'active'
                  AND query_start IS NOT NULL
                  AND now() - query_start > interval '%d seconds'
                ORDER BY query_start ASC
                LIMIT %d
                """.formatted(config.thresholds.longQuerySeconds, limit());
        QueryResult qr = db.query(sql);
        Severity severity = qr.rowCount() > 0 ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("long_queries", "慢 SQL", severity,
                severity == Severity.OK ? "未发现超过阈值的活跃 SQL" : "发现运行时间超过阈值的活跃 SQL", qr);
        result.observations.add("慢 SQL 阈值: " + config.thresholds.longQuerySeconds + " 秒。");
        result.observations.add("报告保留完整 query 文本，便于比赛时直接定位。");
        return result;
    }

    private DiagnosticResult longTransactions() throws SQLException {
        String sql = """
                SELECT pid,
                       usename AS username,
                       datname AS database_name,
                       coalesce(client_addr::text, 'local') AS client_addr,
                       state,
                       round(extract(epoch FROM now() - xact_start))::bigint AS transaction_seconds,
                       xact_start,
                       query_start,
                       query
                FROM pg_stat_activity
                WHERE xact_start IS NOT NULL
                  AND now() - xact_start > interval '%d seconds'
                ORDER BY xact_start ASC
                LIMIT %d
                """.formatted(config.thresholds.longTransactionSeconds, limit());
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
        String sql = """
                SELECT pid,
                       usename AS username,
                       datname AS database_name,
                       coalesce(client_addr::text, 'local') AS client_addr,
                       state,
                       round(extract(epoch FROM now() - state_change))::bigint AS idle_seconds,
                       xact_start,
                       state_change,
                       query
                FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                  AND state_change IS NOT NULL
                  AND now() - state_change > interval '%d seconds'
                ORDER BY state_change ASC
                LIMIT %d
                """.formatted(config.thresholds.idleInTransactionSeconds, limit());
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
        String sql = """
                SELECT blocked.pid AS blocked_pid,
                       blocked_activity.usename AS blocked_user,
                       coalesce(blocked_activity.client_addr::text, 'local') AS blocked_client,
                       round(extract(epoch FROM now() - blocked_activity.query_start))::bigint AS blocked_wait_seconds,
                       blocking.pid AS blocking_pid,
                       blocking_activity.usename AS blocking_user,
                       coalesce(blocking_activity.client_addr::text, 'local') AS blocking_client,
                       blocked.mode AS blocked_mode,
                       blocking.mode AS blocking_mode,
                       blocked.locktype AS locktype,
                       blocked_activity.query AS blocked_query,
                       blocking_activity.query AS blocking_query
                FROM pg_locks blocked
                JOIN pg_stat_activity blocked_activity ON blocked_activity.pid = blocked.pid
                JOIN pg_locks blocking
                  ON blocking.locktype = blocked.locktype
                 AND blocking.database IS NOT DISTINCT FROM blocked.database
                 AND blocking.relation IS NOT DISTINCT FROM blocked.relation
                 AND blocking.page IS NOT DISTINCT FROM blocked.page
                 AND blocking.tuple IS NOT DISTINCT FROM blocked.tuple
                 AND blocking.virtualxid IS NOT DISTINCT FROM blocked.virtualxid
                 AND blocking.transactionid IS NOT DISTINCT FROM blocked.transactionid
                 AND blocking.classid IS NOT DISTINCT FROM blocked.classid
                 AND blocking.objid IS NOT DISTINCT FROM blocked.objid
                 AND blocking.objsubid IS NOT DISTINCT FROM blocked.objsubid
                 AND blocking.pid <> blocked.pid
                JOIN pg_stat_activity blocking_activity ON blocking_activity.pid = blocking.pid
                WHERE NOT blocked.granted
                  AND blocking.granted
                ORDER BY blocked_activity.query_start ASC
                LIMIT %d
                """.formatted(limit());
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
        String sql = """
                SELECT node_name,
                       db_name,
                       thread_name,
                       tid,
                       sessionid,
                       wait_status,
                       wait_event,
                       locktag,
                       lockmode,
                       block_sessionid
                FROM pg_thread_wait_status
                WHERE wait_status IS NOT NULL
                  AND wait_status <> 'none'
                ORDER BY wait_status, tid
                LIMIT %d
                """.formatted(limit());
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
        String sql = """
                SELECT datname AS database_name,
                       deadlocks
                FROM pg_stat_database
                WHERE datname = current_database()
                """;
        QueryResult qr = db.query(sql);
        long deadlocks = qr.rows.stream().mapToLong(row -> longNumber(row, "deadlocks", 0)).sum();
        Severity severity = deadlocks > 0 ? Severity.WARNING : Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("deadlocks", "死锁计数", severity,
                severity == Severity.OK ? "当前数据库累计死锁计数为 0" : "当前数据库累计死锁计数大于 0", qr);
        result.observations.add("pg_stat_database.deadlocks 是累计值，不等于最近 20 分钟发生过死锁。");
        return result;
    }

    private DiagnosticResult riskyRoles() throws SQLException {
        String sql = """
                SELECT rolname,
                       rolsuper,
                       rolsystemadmin,
                       rolauditadmin,
                       rolmonitoradmin,
                       roloperatoradmin,
                       rolpolicyadmin,
                       rolcreaterole,
                       rolcreatedb,
                       rolcanlogin,
                       rolreplication,
                       rolconnlimit,
                       rolvalidbegin,
                       rolvaliduntil
                FROM pg_roles
                WHERE rolcanlogin
                   OR rolsuper
                   OR rolsystemadmin
                   OR rolauditadmin
                   OR rolmonitoradmin
                   OR roloperatoradmin
                   OR rolpolicyadmin
                   OR rolcreaterole
                   OR rolcreatedb
                   OR rolreplication
                ORDER BY rolsuper DESC,
                         rolsystemadmin DESC,
                         rolauditadmin DESC,
                         rolcreaterole DESC,
                         rolcreatedb DESC,
                         rolreplication DESC,
                         rolname
                LIMIT %d
                """.formatted(limit());
        QueryResult qr = db.query(sql);
        Severity severity = Severity.OK;
        DiagnosticResult result = DiagnosticResult.of("risky_roles", "用户与权限风险", severity,
                "已列出可登录和高权限角色", qr);
        result.observations.add("默认不把现有高权限账号判定为异常；如开启白名单，会结合 whitelist.users 判断。");
        if (config.whitelist.enabled) {
            Set<String> allowedUsers = config.whitelist.users.stream()
                    .filter(value -> value != null && !value.isBlank())
                    .map(value -> value.toLowerCase(Locale.ROOT))
                    .collect(Collectors.toSet());
            List<String> suspicious = qr.rows.stream()
                    .filter(row -> truthy(row.get("rolcanlogin")))
                    .filter(row -> !allowedUsers.contains(row.getOrDefault("rolname", "").toLowerCase(Locale.ROOT)))
                    .map(row -> row.get("rolname"))
                    .toList();
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
        String sql = """
                SELECT time,
                       type,
                       result,
                       username,
                       database,
                       client_conninfo,
                       object_name,
                       detail_info
                FROM pg_query_audit(
                    to_char(now() - interval '%d minutes', 'YYYY-MM-DD HH24:MI:SS'),
                    to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                )
                WHERE upper(coalesce(detail_info, '')) LIKE '%%CREATE %%'
                   OR upper(coalesce(detail_info, '')) LIKE '%%ALTER %%'
                   OR upper(coalesce(detail_info, '')) LIKE '%%DROP %%'
                   OR upper(coalesce(detail_info, '')) LIKE '%%TRUNCATE %%'
                   OR upper(coalesce(detail_info, '')) LIKE '%%GRANT %%'
                   OR upper(coalesce(detail_info, '')) LIKE '%%REVOKE %%'
                   OR upper(coalesce(type, '')) LIKE '%%DDL%%'
                   OR upper(coalesce(type, '')) LIKE '%%DCL%%'
                ORDER BY time DESC
                LIMIT %d
                """.formatted(minutes, limit());
        QueryResult qr = db.query(sql);
        boolean dangerous = qr.rows.stream().anyMatch(row -> isDangerousDdl(row.get("detail_info")));
        Severity severity = qr.rowCount() == 0 ? Severity.OK : dangerous ? Severity.CRITICAL : Severity.WARNING;
        DiagnosticResult result = DiagnosticResult.of("recent_ddl_dcl", "最近 DDL/DCL 审计", severity,
                severity == Severity.OK ? "最近 " + minutes + " 分钟未发现 DDL/DCL 审计记录" : "最近 " + minutes + " 分钟发现 DDL/DCL 审计记录", qr);
        result.observations.add("通过 pg_query_audit 查询审计结果；这里只读取审计信息。");
        result.observations.add("DROP/TRUNCATE/GRANT/REVOKE/用户权限变更会提升为严重风险。");
        return result;
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

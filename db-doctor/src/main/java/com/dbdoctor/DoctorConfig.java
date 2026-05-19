package com.dbdoctor;

import java.util.ArrayList;
import java.util.List;

public class DoctorConfig {
    public Database database = new Database();
    public Diagnosis diagnosis = new Diagnosis();
    public Thresholds thresholds = new Thresholds();
    public Whitelist whitelist = new Whitelist();
    public Web web = new Web();
    public Report report = new Report();

    public void normalize() {
        if (database == null) {
            database = new Database();
        }
        if (diagnosis == null) {
            diagnosis = new Diagnosis();
        }
        if (thresholds == null) {
            thresholds = new Thresholds();
        }
        if (whitelist == null) {
            whitelist = new Whitelist();
        }
        if (web == null) {
            web = new Web();
        }
        if (report == null) {
            report = new Report();
        }

        diagnosis.ddlLookbackMinutes = clamp(diagnosis.ddlLookbackMinutes, 1, 1440);
        diagnosis.intervalSeconds = clamp(diagnosis.intervalSeconds, 1, 86400);
        web.port = clamp(web.port, 1, 65535);
        web.refreshSeconds = clamp(web.refreshSeconds, 1, 86400);
        if (isBlank(web.host)) {
            web.host = "127.0.0.1";
        }
        database.port = clamp(database.port, 1, 65535);
        database.connectTimeoutSeconds = clamp(database.connectTimeoutSeconds, 1, 60);
        database.queryTimeoutSeconds = clamp(database.queryTimeoutSeconds, 1, 300);
        thresholds.connectionUsageWarning = normalizeRatio(thresholds.connectionUsageWarning, 0.70);
        thresholds.connectionUsageCritical = normalizeRatio(thresholds.connectionUsageCritical, 0.90);
        thresholds.longQuerySeconds = clamp(thresholds.longQuerySeconds, 1, 86400);
        thresholds.longTransactionSeconds = clamp(thresholds.longTransactionSeconds, 1, 86400);
        thresholds.lockWaitSeconds = clamp(thresholds.lockWaitSeconds, 1, 86400);
        thresholds.idleInTransactionSeconds = clamp(thresholds.idleInTransactionSeconds, 1, 86400);
        thresholds.maxRowsPerCheck = clamp(thresholds.maxRowsPerCheck, 1, 500);
        if (whitelist.users == null) {
            whitelist.users = new ArrayList<>();
        }
        if (whitelist.clientIps == null) {
            whitelist.clientIps = new ArrayList<>();
        }
        if (isBlank(report.outputDir)) {
            report.outputDir = "reports";
        }
    }

    public void validate() {
        requireText(database.host, "database.host");
        requireText(database.database, "database.database");
        requireText(database.username, "database.username");
        requireText(database.password, "database.password");
    }

    public String jdbcUrl() {
        return "jdbc:opengauss://" + database.host + ":" + database.port + "/" + database.database;
    }

    public String databaseTarget() {
        return database.username + "@" + database.host + ":" + database.port + "/" + database.database;
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static double normalizeRatio(double value, double fallback) {
        if (Double.isNaN(value) || value <= 0) {
            return fallback;
        }
        if (value > 1) {
            return Math.min(value / 100.0, 1.0);
        }
        return value;
    }

    private static void requireText(String value, String name) {
        if (isBlank(value)) {
            throw new IllegalArgumentException(name + " is required");
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    public static class Database {
        public String host = "127.0.0.1";
        public int port = 5432;
        public String database = "postgres";
        public String username = "omm";
        public String password;
        public boolean ssl = false;
        public int connectTimeoutSeconds = 5;
        public int queryTimeoutSeconds = 5;
    }

    public static class Diagnosis {
        public boolean continuous = false;
        public int intervalSeconds = 5;
        public int ddlLookbackMinutes = 20;
        public boolean keepFullSqlText = true;
    }

    public static class Thresholds {
        public double connectionUsageWarning = 0.70;
        public double connectionUsageCritical = 0.90;
        public int longQuerySeconds = 60;
        public int longTransactionSeconds = 120;
        public int lockWaitSeconds = 10;
        public int idleInTransactionSeconds = 60;
        public int maxRowsPerCheck = 50;
    }

    public static class Whitelist {
        public boolean enabled = false;
        public List<String> users = new ArrayList<>();
        public List<String> clientIps = new ArrayList<>();
    }

    public static class Web {
        public boolean enabled = false;
        public String host = "127.0.0.1";
        public int port = 8080;
        public int refreshSeconds = 5;
    }

    public static class Report {
        public String outputDir = "reports";
        public boolean html = true;
        @Deprecated
        public boolean markdown = false;
        public boolean json = true;
    }
}

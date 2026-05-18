package com.dbdoctor;

import java.util.Locale;
import java.util.regex.Pattern;

public final class SqlSafety {
    private static final Pattern ALLOWED_START = Pattern.compile("^(select|with|show)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern BLOCKED_KEYWORDS = Pattern.compile(
            "\\b(insert|update|delete|merge|create|drop|alter|truncate|grant|revoke|call|do|copy|vacuum|analyze|set|reset|discard|listen|notify|unlisten|lock|prepare|execute|deallocate)\\b",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern BLOCKED_FUNCTIONS = Pattern.compile(
            "\\b(pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_rotate_logfile|pg_advisory_lock|pg_try_advisory_lock|nextval|setval|lo_import|lo_export|dblink_exec)\\s*\\(",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern FOR_UPDATE = Pattern.compile("\\bfor\\s+(update|no\\s+key\\s+update|share|key\\s+share)\\b", Pattern.CASE_INSENSITIVE);

    private SqlSafety() {
    }

    public static void requireReadOnly(String sql) {
        if (sql == null || sql.trim().isEmpty()) {
            throw new IllegalArgumentException("SQL is blank");
        }
        String sanitized = stripCommentsAndLiterals(sql).trim();
        String lower = sanitized.toLowerCase(Locale.ROOT);
        String withoutFinalSemicolon = lower.endsWith(";") ? lower.substring(0, lower.length() - 1).trim() : lower;
        if (withoutFinalSemicolon.contains(";")) {
            throw new IllegalArgumentException("multiple SQL statements are not allowed");
        }
        if (!ALLOWED_START.matcher(withoutFinalSemicolon).find()) {
            throw new IllegalArgumentException("SQL must start with SELECT, WITH, or SHOW");
        }
        if (BLOCKED_KEYWORDS.matcher(withoutFinalSemicolon).find()) {
            throw new IllegalArgumentException("SQL contains a blocked keyword");
        }
        if (BLOCKED_FUNCTIONS.matcher(withoutFinalSemicolon).find()) {
            throw new IllegalArgumentException("SQL contains a blocked function");
        }
        if (FOR_UPDATE.matcher(withoutFinalSemicolon).find()) {
            throw new IllegalArgumentException("locking SELECT clauses are not allowed");
        }
    }

    static String stripCommentsAndLiterals(String sql) {
        StringBuilder out = new StringBuilder(sql.length());
        boolean inSingleQuote = false;
        boolean inDoubleQuote = false;
        boolean inLineComment = false;
        boolean inBlockComment = false;
        for (int i = 0; i < sql.length(); i++) {
            char c = sql.charAt(i);
            char next = i + 1 < sql.length() ? sql.charAt(i + 1) : '\0';

            if (inLineComment) {
                if (c == '\n' || c == '\r') {
                    inLineComment = false;
                    out.append(' ');
                }
                continue;
            }
            if (inBlockComment) {
                if (c == '*' && next == '/') {
                    inBlockComment = false;
                    i++;
                    out.append(' ');
                }
                continue;
            }
            if (inSingleQuote) {
                if (c == '\'' && next == '\'') {
                    i++;
                    continue;
                }
                if (c == '\'') {
                    inSingleQuote = false;
                    out.append(' ');
                }
                continue;
            }
            if (inDoubleQuote) {
                if (c == '"' && next == '"') {
                    i++;
                    continue;
                }
                if (c == '"') {
                    inDoubleQuote = false;
                    out.append(' ');
                }
                continue;
            }

            if (c == '-' && next == '-') {
                inLineComment = true;
                i++;
                out.append(' ');
            } else if (c == '/' && next == '*') {
                inBlockComment = true;
                i++;
                out.append(' ');
            } else if (c == '\'') {
                inSingleQuote = true;
                out.append(' ');
            } else if (c == '"') {
                inDoubleQuote = true;
                out.append(' ');
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }
}

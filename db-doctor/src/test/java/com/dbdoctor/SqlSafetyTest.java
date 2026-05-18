package com.dbdoctor;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SqlSafetyTest {
    @Test
    void allowsReadOnlySelectWithDdlWordsInsideStringLiterals() {
        String sql = "SELECT *\n"
                + "FROM pg_query_audit(\n"
                + "    now() - interval '20 minutes',\n"
                + "    now()\n"
                + ") AS t\n"
                + "WHERE upper(detail_info) LIKE '%DROP %'";
        assertDoesNotThrow(() -> SqlSafety.requireReadOnly(sql));
    }

    @Test
    void recentDdlDclAuditUsesTimestampArgumentsAndSkipsDmlTypes() {
        String sql = DiagnosisService.recentDdlDclSql(60, 50);
        assertDoesNotThrow(() -> SqlSafety.requireReadOnly(sql));
        org.junit.jupiter.api.Assertions.assertTrue(sql.contains("now() - interval '60 minutes'"));
        org.junit.jupiter.api.Assertions.assertTrue(sql.contains("now()"));
        org.junit.jupiter.api.Assertions.assertTrue(sql.contains("LIKE 'ddl_%'"));
        org.junit.jupiter.api.Assertions.assertTrue(sql.contains("LIKE 'dcl_%'"));
        org.junit.jupiter.api.Assertions.assertFalse(sql.contains("dml_action"));
        org.junit.jupiter.api.Assertions.assertFalse(sql.contains("to_char("));
    }

    @Test
    void rejectsDdl() {
        assertThrows(IllegalArgumentException.class, () -> SqlSafety.requireReadOnly("ALTER ROLE app_user PASSWORD 'x'"));
    }

    @Test
    void rejectsMultipleStatements() {
        assertThrows(IllegalArgumentException.class, () -> SqlSafety.requireReadOnly("SELECT 1; SELECT 2"));
    }

    @Test
    void rejectsSideEffectFunctions() {
        assertThrows(IllegalArgumentException.class, () -> SqlSafety.requireReadOnly("SELECT pg_terminate_backend(123)"));
        assertThrows(IllegalArgumentException.class, () -> SqlSafety.requireReadOnly("SELECT nextval('s')"));
    }

    @Test
    void rejectsLockingSelect() {
        assertThrows(IllegalArgumentException.class, () -> SqlSafety.requireReadOnly("SELECT * FROM t FOR UPDATE"));
    }
}

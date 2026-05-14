package com.dbdoctor;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SqlSafetyTest {
    @Test
    void allowsReadOnlySelectWithDdlWordsInsideStringLiterals() {
        String sql = """
                SELECT *
                FROM pg_query_audit(
                    to_char(now() - interval '20 minutes', 'YYYY-MM-DD HH24:MI:SS'),
                    to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                )
                WHERE upper(detail_info) LIKE '%DROP %'
                """;
        assertDoesNotThrow(() -> SqlSafety.requireReadOnly(sql));
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

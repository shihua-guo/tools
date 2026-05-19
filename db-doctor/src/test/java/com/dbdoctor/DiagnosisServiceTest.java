package com.dbdoctor;

import org.junit.jupiter.api.Test;

import java.sql.SQLException;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DiagnosisServiceTest {
    @Test
    void runWithExistingClientDoesNotCloseIt() {
        DoctorConfig config = new DoctorConfig();
        config.database.password = "secret";
        config.normalize();
        CloseTrackingClient client = new CloseTrackingClient();

        DiagnosticSummary summary = new DiagnosisService(config).run(client);

        assertFalse(client.closed);
        assertTrue(client.queryCount > 0);
        assertFalse(summary.results.isEmpty());
    }

    private static class CloseTrackingClient implements DatabaseClient, AutoCloseable {
        private boolean closed;
        private int queryCount;

        @Override
        public QueryResult query(String sql) {
            queryCount++;
            QueryResult result = new QueryResult();
            result.sql = sql;
            return result;
        }

        @Override
        public QueryResult query(String sql, DbClient.Binder binder) throws SQLException {
            return query(sql);
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}

package com.dbdoctor;

import org.junit.jupiter.api.Test;

import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PersistentDatabaseClientTest {
    @Test
    void reusesConnectionUntilClosed() throws Exception {
        DoctorConfig config = config();
        AtomicInteger connects = new AtomicInteger();
        CloseTrackingClient client = new CloseTrackingClient();
        PersistentDatabaseClient session = new PersistentDatabaseClient(config, ignored -> {
            connects.incrementAndGet();
            return client;
        });

        DatabaseClient first = session.get();
        DatabaseClient second = session.get();

        assertSame(first, second);
        assertEquals(1, connects.get());
        assertFalse(client.closed);

        session.close();

        assertTrue(client.closed);
    }

    @Test
    void retriesUntilFirstConnectionSucceeds() throws Exception {
        DoctorConfig config = config();
        AtomicInteger attempts = new AtomicInteger();
        CloseTrackingClient client = new CloseTrackingClient();
        PersistentDatabaseClient session = new PersistentDatabaseClient(config, ignored -> {
            if (attempts.incrementAndGet() == 1) {
                throw new SQLException("remaining connection slots are reserved");
            }
            return client;
        });

        assertThrows(SQLException.class, session::get);

        assertSame(client, session.get());
        assertEquals(2, attempts.get());
        assertFalse(client.closed);
    }

    @Test
    void keepsSuccessfulConnectionEvenIfQueriesStartFailing() throws Exception {
        DoctorConfig config = config();
        AtomicInteger connects = new AtomicInteger();
        CloseTrackingClient client = new CloseTrackingClient();
        PersistentDatabaseClient session = new PersistentDatabaseClient(config, ignored -> {
            connects.incrementAndGet();
            return client;
        });

        DatabaseClient first = session.get();
        client.failQueries = true;

        assertThrows(SQLException.class, () -> first.query("SELECT 1"));
        assertSame(first, session.get());
        assertEquals(1, connects.get());
    }

    private static DoctorConfig config() {
        DoctorConfig config = new DoctorConfig();
        config.database.password = "secret";
        config.normalize();
        return config;
    }

    private static class CloseTrackingClient implements CloseableDatabaseClient {
        private boolean closed;
        private boolean failQueries;

        @Override
        public QueryResult query(String sql) throws SQLException {
            if (failQueries) {
                throw new SQLException("connection was terminated externally");
            }
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

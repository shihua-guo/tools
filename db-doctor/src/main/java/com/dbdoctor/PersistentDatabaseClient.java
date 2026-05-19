package com.dbdoctor;

class PersistentDatabaseClient implements AutoCloseable {
    interface Connector {
        CloseableDatabaseClient connect(DoctorConfig config) throws Exception;
    }

    private final DoctorConfig config;
    private final Connector connector;
    private CloseableDatabaseClient client;
    private boolean closed;

    PersistentDatabaseClient(DoctorConfig config) {
        this(config, DbClient::connect);
    }

    PersistentDatabaseClient(DoctorConfig config, Connector connector) {
        this.config = config;
        this.connector = connector;
    }

    synchronized DatabaseClient get() throws Exception {
        if (closed) {
            throw new IllegalStateException("database client session is closed");
        }
        if (client == null) {
            client = connector.connect(config);
        }
        return client;
    }

    synchronized boolean isConnected() {
        return client != null;
    }

    @Override
    public synchronized void close() throws Exception {
        closed = true;
        CloseableDatabaseClient current = client;
        client = null;
        if (current != null) {
            current.close();
        }
    }
}

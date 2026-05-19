package com.dbdoctor;

interface CloseableDatabaseClient extends DatabaseClient, AutoCloseable {
    @Override
    void close() throws Exception;
}

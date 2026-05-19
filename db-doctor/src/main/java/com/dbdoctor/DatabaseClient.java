package com.dbdoctor;

import java.sql.SQLException;

interface DatabaseClient {
    QueryResult query(String sql) throws SQLException;

    QueryResult query(String sql, DbClient.Binder binder) throws SQLException;
}

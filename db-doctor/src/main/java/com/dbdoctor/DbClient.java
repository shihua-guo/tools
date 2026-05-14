package com.dbdoctor;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

public class DbClient implements AutoCloseable {
    private final DoctorConfig config;
    private final Connection connection;

    private DbClient(DoctorConfig config, Connection connection) {
        this.config = config;
        this.connection = connection;
    }

    public static DbClient connect(DoctorConfig config) throws SQLException, ClassNotFoundException {
        Class.forName("org.opengauss.Driver");
        DriverManager.setLoginTimeout(config.database.connectTimeoutSeconds);
        Properties properties = new Properties();
        properties.setProperty("user", config.database.username);
        properties.setProperty("password", config.database.password);
        properties.setProperty("ApplicationName", "db-doctor-readonly");
        if (config.database.ssl) {
            properties.setProperty("ssl", "true");
        }
        Connection connection = DriverManager.getConnection(config.jdbcUrl(), properties);
        connection.setAutoCommit(true);
        connection.setReadOnly(true);
        return new DbClient(config, connection);
    }

    public QueryResult query(String sql) throws SQLException {
        return query(sql, ignored -> {
        });
    }

    public QueryResult query(String sql, Binder binder) throws SQLException {
        SqlSafety.requireReadOnly(sql);
        long start = System.nanoTime();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setQueryTimeout(config.database.queryTimeoutSeconds);
            statement.setFetchSize(Math.min(100, Math.max(1, config.thresholds.maxRowsPerCheck)));
            binder.bind(statement);
            try (ResultSet resultSet = statement.executeQuery()) {
                QueryResult result = toQueryResult(resultSet);
                result.sql = sql;
                result.elapsedMs = (System.nanoTime() - start) / 1_000_000;
                return result;
            }
        }
    }

    private QueryResult toQueryResult(ResultSet resultSet) throws SQLException {
        QueryResult result = new QueryResult();
        ResultSetMetaData metaData = resultSet.getMetaData();
        int columnCount = metaData.getColumnCount();
        for (int i = 1; i <= columnCount; i++) {
            result.columns.add(metaData.getColumnLabel(i));
        }
        while (resultSet.next()) {
            Map<String, String> row = new LinkedHashMap<>();
            for (int i = 1; i <= columnCount; i++) {
                Object value = resultSet.getObject(i);
                row.put(metaData.getColumnLabel(i), value == null ? null : String.valueOf(value));
            }
            result.rows.add(row);
        }
        return result;
    }

    @Override
    public void close() throws SQLException {
        connection.close();
    }

    @FunctionalInterface
    public interface Binder {
        void bind(PreparedStatement statement) throws SQLException;
    }
}

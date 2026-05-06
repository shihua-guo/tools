package com.example.opengaussconnector;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;
import java.util.Set;

public final class Main {
    private static final Set<String> SYSTEM_SCHEMAS = Set.of(
            "information_schema",
            "pg_catalog",
            "dbe_perf",
            "snapshot",
            "blockchain",
            "pkg_service"
    );

    public static void main(String[] args) {
        int exitCode = new Main().run(args);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }

    int run(String[] args) {
        Cli cli = Cli.parse(args);
        if (cli.command == null || cli.flag("help") || cli.command.equals("help")) {
            printHelp();
            return 0;
        }

        try {
            return switch (cli.command) {
                case "ping" -> withConnection(cli, connection -> success("ping", ping(connection)));
                case "list-schemas" -> withConnection(cli, connection -> success("list-schemas", Map.of(
                        "schemas", listSchemas(connection, cli.flag("include-system"))
                )));
                case "list-tables" -> withConnection(cli, connection -> {
                    String schema = cli.option("schema");
                    String pattern = cli.optionOrDefault("pattern", "%");
                    int limit = cli.intOption("limit", 500);
                    List<Map<String, Object>> tables = listTables(connection, schema, pattern, limit, cli.flag("include-system"));
                    return success("list-tables", Map.of("tables", tables, "count", tables.size()));
                });
                case "describe-table" -> withConnection(cli, connection -> {
                    String schema = cli.optionOrDefault("schema", "public");
                    String table = cli.required("table");
                    return success("describe-table", describeTable(connection, schema, table));
                });
                case "schema-summary" -> withConnection(cli, connection -> {
                    String schema = cli.option("schema");
                    String pattern = cli.optionOrDefault("pattern", "%");
                    int limit = cli.intOption("limit", 50);
                    List<Map<String, Object>> tables = describeMatchingTables(connection, schema, pattern, limit, cli.flag("include-system"));
                    return success("schema-summary", Map.of("tables", tables, "count", tables.size()));
                });
                case "search-schema" -> withConnection(cli, connection -> {
                    String keyword = cli.option("keyword");
                    if (keyword == null && !cli.positionals.isEmpty()) {
                        keyword = cli.positionals.get(0);
                    }
                    if (keyword == null || keyword.isBlank()) {
                        throw new CliException("Missing required option: --keyword");
                    }
                    String schema = cli.option("schema");
                    int limit = cli.intOption("limit", 20);
                    List<Map<String, Object>> tables = searchSchema(connection, schema, keyword, limit, cli.flag("include-system"));
                    return success("search-schema", Map.of("keyword", keyword, "tables", tables, "count", tables.size()));
                });
                default -> throw new CliException("Unknown command: " + cli.command);
            };
        } catch (CliException e) {
            printJson(error(cli.command, "invalid_request", e.getMessage()));
            return 2;
        } catch (SQLException e) {
            printJson(error(cli.command, "sql_error", e.getMessage()));
            return 1;
        } catch (RuntimeException e) {
            printJson(error(cli.command, "runtime_error", e.getMessage()));
            return 1;
        }
    }

    private int withConnection(Cli cli, SqlAction action) throws SQLException {
        DatabaseConfig config = DatabaseConfig.from(cli);
        try (Connection connection = config.open()) {
            try {
                connection.setReadOnly(true);
            } catch (SQLException ignored) {
                // Some openGauss deployments reject read-only session hints.
            }
            printJson(action.execute(connection));
            return 0;
        }
    }

    private Map<String, Object> ping(Connection connection) throws SQLException {
        DatabaseMetaData metaData = connection.getMetaData();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("database_product_name", metaData.getDatabaseProductName());
        result.put("database_product_version", metaData.getDatabaseProductVersion());
        result.put("driver_name", metaData.getDriverName());
        result.put("driver_version", metaData.getDriverVersion());
        result.put("user_name", metaData.getUserName());
        result.put("url", metaData.getURL());

        try (PreparedStatement statement = connection.prepareStatement("select current_database(), current_schema()")) {
            try (ResultSet rs = statement.executeQuery()) {
                if (rs.next()) {
                    result.put("current_database", rs.getString(1));
                    result.put("current_schema", rs.getString(2));
                }
            }
        }
        return result;
    }

    private List<Map<String, Object>> listSchemas(Connection connection, boolean includeSystem) throws SQLException {
        String sql = "select nspname as schema_name, obj_description(oid, 'pg_namespace') as schema_comment " +
                "from pg_catalog.pg_namespace order by nspname";
        List<Map<String, Object>> schemas = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                String schemaName = rs.getString("schema_name");
                if (!includeSystem && isSystemSchema(schemaName)) {
                    continue;
                }
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("schema", schemaName);
                row.put("comment", rs.getString("schema_comment"));
                schemas.add(row);
            }
        }
        return schemas;
    }

    private List<Map<String, Object>> listTables(
            Connection connection,
            String schema,
            String pattern,
            int limit,
            boolean includeSystem
    ) throws SQLException {
        StringBuilder sql = new StringBuilder();
        sql.append("select n.nspname as schema_name, c.relname as table_name, ");
        sql.append("case c.relkind ");
        sql.append("when 'r' then 'table' ");
        sql.append("when 'p' then 'partitioned_table' ");
        sql.append("when 'v' then 'view' ");
        sql.append("when 'm' then 'materialized_view' ");
        sql.append("when 'f' then 'foreign_table' ");
        sql.append("else c.relkind::text end as table_type, ");
        sql.append("obj_description(c.oid, 'pg_class') as table_comment, ");
        sql.append("case when c.reltuples < 0 then null else c.reltuples::bigint end as estimated_rows ");
        sql.append("from pg_catalog.pg_class c ");
        sql.append("join pg_catalog.pg_namespace n on n.oid = c.relnamespace ");
        sql.append("where c.relkind in ('r', 'p', 'v', 'm', 'f') ");
        if (!includeSystem) {
            sql.append("and n.nspname not like 'pg_%' and n.nspname <> 'information_schema' ");
            sql.append("and n.nspname not in ('dbe_perf', 'snapshot', 'blockchain', 'pkg_service') ");
        }
        if (schema != null && !schema.isBlank()) {
            sql.append("and n.nspname = ? ");
        }
        sql.append("and c.relname like ? ");
        sql.append("order by n.nspname, c.relname limit ?");

        List<Map<String, Object>> tables = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql.toString())) {
            int index = 1;
            if (schema != null && !schema.isBlank()) {
                statement.setString(index++, schema);
            }
            statement.setString(index++, pattern);
            statement.setInt(index, Math.max(1, limit));
            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("schema", rs.getString("schema_name"));
                    row.put("name", rs.getString("table_name"));
                    row.put("type", rs.getString("table_type"));
                    row.put("comment", rs.getString("table_comment"));
                    row.put("estimated_rows", nullableLong(rs, "estimated_rows"));
                    tables.add(row);
                }
            }
        }
        return tables;
    }

    private List<Map<String, Object>> describeMatchingTables(
            Connection connection,
            String schema,
            String pattern,
            int limit,
            boolean includeSystem
    ) throws SQLException {
        List<Map<String, Object>> tableRefs = listTables(connection, schema, pattern, limit, includeSystem);
        List<Map<String, Object>> tables = new ArrayList<>();
        for (Map<String, Object> tableRef : tableRefs) {
            tables.add(describeTable(connection, Objects.toString(tableRef.get("schema")), Objects.toString(tableRef.get("name"))));
        }
        return tables;
    }

    private Map<String, Object> describeTable(Connection connection, String schema, String table) throws SQLException {
        Map<String, Object> tableInfo = findTable(connection, schema, table);
        if (tableInfo == null) {
            throw new CliException("Table not found: " + schema + "." + table);
        }

        List<Map<String, Object>> primaryKeys = primaryKeys(connection, schema, table);
        Set<String> primaryKeyColumns = new LinkedHashSet<>();
        for (Map<String, Object> primaryKey : primaryKeys) {
            primaryKeyColumns.add(Objects.toString(primaryKey.get("column")));
        }

        List<Map<String, Object>> columns = columns(connection, schema, table);
        for (Map<String, Object> column : columns) {
            column.put("primary_key", primaryKeyColumns.contains(Objects.toString(column.get("name"))));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("table", tableInfo);
        result.put("columns", columns);
        result.put("primary_keys", primaryKeys);
        result.put("indexes", indexes(connection, schema, table));
        result.put("foreign_keys", importedKeys(connection, schema, table));
        return result;
    }

    private Map<String, Object> findTable(Connection connection, String schema, String table) throws SQLException {
        String sql = "select n.nspname as schema_name, c.relname as table_name, " +
                "case c.relkind " +
                "when 'r' then 'table' " +
                "when 'p' then 'partitioned_table' " +
                "when 'v' then 'view' " +
                "when 'm' then 'materialized_view' " +
                "when 'f' then 'foreign_table' " +
                "else c.relkind::text end as table_type, " +
                "obj_description(c.oid, 'pg_class') as table_comment, " +
                "case when c.reltuples < 0 then null else c.reltuples::bigint end as estimated_rows " +
                "from pg_catalog.pg_class c " +
                "join pg_catalog.pg_namespace n on n.oid = c.relnamespace " +
                "where c.relkind in ('r', 'p', 'v', 'm', 'f') and n.nspname = ? and c.relname = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, schema);
            statement.setString(2, table);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("schema", rs.getString("schema_name"));
                result.put("name", rs.getString("table_name"));
                result.put("type", rs.getString("table_type"));
                result.put("comment", rs.getString("table_comment"));
                result.put("estimated_rows", nullableLong(rs, "estimated_rows"));
                return result;
            }
        }
    }

    private List<Map<String, Object>> columns(Connection connection, String schema, String table) throws SQLException {
        String sql = "select a.attnum as ordinal_position, a.attname as column_name, " +
                "pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type, " +
                "a.attnotnull as not_null, " +
                "pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) as default_value, " +
                "pg_catalog.col_description(a.attrelid, a.attnum) as column_comment " +
                "from pg_catalog.pg_attribute a " +
                "join pg_catalog.pg_class c on c.oid = a.attrelid " +
                "join pg_catalog.pg_namespace n on n.oid = c.relnamespace " +
                "left join pg_catalog.pg_attrdef ad on ad.adrelid = a.attrelid and ad.adnum = a.attnum " +
                "where n.nspname = ? and c.relname = ? and a.attnum > 0 and not a.attisdropped " +
                "order by a.attnum";
        List<Map<String, Object>> columns = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, schema);
            statement.setString(2, table);
            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("ordinal", rs.getInt("ordinal_position"));
                    row.put("name", rs.getString("column_name"));
                    row.put("type", rs.getString("data_type"));
                    row.put("nullable", !rs.getBoolean("not_null"));
                    row.put("default", rs.getString("default_value"));
                    row.put("comment", rs.getString("column_comment"));
                    columns.add(row);
                }
            }
        }
        return columns;
    }

    private List<Map<String, Object>> primaryKeys(Connection connection, String schema, String table) throws SQLException {
        List<Map<String, Object>> keys = new ArrayList<>();
        DatabaseMetaData metaData = connection.getMetaData();
        try (ResultSet rs = metaData.getPrimaryKeys(null, schema, table)) {
            while (rs.next()) {
                Map<String, Object> key = new LinkedHashMap<>();
                key.put("name", rs.getString("PK_NAME"));
                key.put("column", rs.getString("COLUMN_NAME"));
                key.put("sequence", rs.getShort("KEY_SEQ"));
                keys.add(key);
            }
        }
        keys.sort(Comparator.comparingInt(row -> ((Number) row.get("sequence")).intValue()));
        return keys;
    }

    private List<Map<String, Object>> indexes(Connection connection, String schema, String table) throws SQLException {
        Map<String, Map<String, Object>> indexesByName = new LinkedHashMap<>();
        DatabaseMetaData metaData = connection.getMetaData();
        try (ResultSet rs = metaData.getIndexInfo(null, schema, table, false, false)) {
            while (rs.next()) {
                if (rs.getShort("TYPE") == DatabaseMetaData.tableIndexStatistic) {
                    continue;
                }
                String indexName = rs.getString("INDEX_NAME");
                String columnName = rs.getString("COLUMN_NAME");
                if (indexName == null || columnName == null) {
                    continue;
                }

                Map<String, Object> index = indexesByName.computeIfAbsent(indexName, name -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("name", name);
                    value.put("unique", !safeBoolean(rs, "NON_UNIQUE"));
                    value.put("columns", new ArrayList<Map<String, Object>>());
                    return value;
                });
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> columns = (List<Map<String, Object>>) index.get("columns");
                Map<String, Object> column = new LinkedHashMap<>();
                column.put("name", columnName);
                column.put("sequence", rs.getShort("ORDINAL_POSITION"));
                column.put("sort", rs.getString("ASC_OR_DESC"));
                columns.add(column);
            }
        }
        for (Map<String, Object> index : indexesByName.values()) {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> columns = (List<Map<String, Object>>) index.get("columns");
            columns.sort(Comparator.comparingInt(row -> ((Number) row.get("sequence")).intValue()));
        }
        return new ArrayList<>(indexesByName.values());
    }

    private List<Map<String, Object>> importedKeys(Connection connection, String schema, String table) throws SQLException {
        Map<String, Map<String, Object>> keysByName = new LinkedHashMap<>();
        DatabaseMetaData metaData = connection.getMetaData();
        try (ResultSet rs = metaData.getImportedKeys(null, schema, table)) {
            while (rs.next()) {
                String keyName = rs.getString("FK_NAME");
                if (keyName == null || keyName.isBlank()) {
                    keyName = rs.getString("FKTABLE_NAME") + "_fk_" + rs.getString("PKTABLE_NAME");
                }
                String finalKeyName = keyName;
                Map<String, Object> key = keysByName.computeIfAbsent(finalKeyName, name -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("name", name);
                    value.put("referenced_schema", safeString(rs, "PKTABLE_SCHEM"));
                    value.put("referenced_table", safeString(rs, "PKTABLE_NAME"));
                    value.put("columns", new ArrayList<Map<String, Object>>());
                    return value;
                });
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> columns = (List<Map<String, Object>>) key.get("columns");
                Map<String, Object> column = new LinkedHashMap<>();
                column.put("column", rs.getString("FKCOLUMN_NAME"));
                column.put("referenced_column", rs.getString("PKCOLUMN_NAME"));
                column.put("sequence", rs.getShort("KEY_SEQ"));
                columns.add(column);
            }
        }
        for (Map<String, Object> key : keysByName.values()) {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> columns = (List<Map<String, Object>>) key.get("columns");
            columns.sort(Comparator.comparingInt(row -> ((Number) row.get("sequence")).intValue()));
        }
        return new ArrayList<>(keysByName.values());
    }

    private List<Map<String, Object>> searchSchema(
            Connection connection,
            String schema,
            String keyword,
            int limit,
            boolean includeSystem
    ) throws SQLException {
        StringBuilder sql = new StringBuilder();
        sql.append("select distinct n.nspname as schema_name, c.relname as table_name ");
        sql.append("from pg_catalog.pg_class c ");
        sql.append("join pg_catalog.pg_namespace n on n.oid = c.relnamespace ");
        sql.append("where c.relkind in ('r', 'p', 'v', 'm', 'f') ");
        if (!includeSystem) {
            sql.append("and n.nspname not like 'pg_%' and n.nspname <> 'information_schema' ");
            sql.append("and n.nspname not in ('dbe_perf', 'snapshot', 'blockchain', 'pkg_service') ");
        }
        if (schema != null && !schema.isBlank()) {
            sql.append("and n.nspname = ? ");
        }
        sql.append("and (lower(n.nspname) like ? ");
        sql.append("or lower(c.relname) like ? ");
        sql.append("or lower(coalesce(obj_description(c.oid, 'pg_class'), '')) like ? ");
        sql.append("or exists (");
        sql.append("select 1 from pg_catalog.pg_attribute a ");
        sql.append("where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped ");
        sql.append("and (lower(a.attname) like ? ");
        sql.append("or lower(coalesce(pg_catalog.col_description(a.attrelid, a.attnum), '')) like ?)");
        sql.append(")) ");
        sql.append("order by n.nspname, c.relname limit ?");

        String like = "%" + keyword.toLowerCase(Locale.ROOT) + "%";
        List<Map<String, Object>> refs = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql.toString())) {
            int index = 1;
            if (schema != null && !schema.isBlank()) {
                statement.setString(index++, schema);
            }
            for (int i = 0; i < 5; i++) {
                statement.setString(index++, like);
            }
            statement.setInt(index, Math.max(1, limit));
            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> ref = new LinkedHashMap<>();
                    ref.put("schema", rs.getString("schema_name"));
                    ref.put("name", rs.getString("table_name"));
                    refs.add(ref);
                }
            }
        }

        List<Map<String, Object>> tables = new ArrayList<>();
        for (Map<String, Object> ref : refs) {
            tables.add(describeTable(connection, Objects.toString(ref.get("schema")), Objects.toString(ref.get("name"))));
        }
        return tables;
    }

    private static Map<String, Object> success(String command, Object data) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", true);
        result.put("command", command);
        result.put("data", data);
        return result;
    }

    private static Map<String, Object> error(String command, String type, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", false);
        result.put("command", command);
        result.put("error", Map.of("type", type, "message", message == null ? "" : message));
        return result;
    }

    private static boolean isSystemSchema(String schemaName) {
        return schemaName == null
                || schemaName.startsWith("pg_")
                || SYSTEM_SCHEMAS.contains(schemaName);
    }

    private static Long nullableLong(ResultSet rs, String column) throws SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    private static boolean safeBoolean(ResultSet rs, String column) {
        try {
            return rs.getBoolean(column);
        } catch (SQLException e) {
            return false;
        }
    }

    private static String safeString(ResultSet rs, String column) {
        try {
            return rs.getString(column);
        } catch (SQLException e) {
            return null;
        }
    }

    private static String env(String name) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? null : value;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private static void printJson(Object value) {
        System.out.println(Json.stringify(value));
    }

    private static void printHelp() {
        System.out.println("""
                openGauss Connector CLI

                Usage:
                  java -jar target/opengauss-connector-cli-1.0.0.jar <command> [options]

                Connection options:
                  --url <jdbc-url>          Example: jdbc:opengauss://localhost:5432/postgres
                  --host <host>             Used when --url is absent. Default: localhost
                  --port <port>             Used when --url is absent. Default: 5432
                  --database <database>     Used when --url is absent
                  --user <user>
                  --password <password>

                Environment variables:
                  OPENGAUSS_URL, OPENGAUSS_HOST, OPENGAUSS_PORT, OPENGAUSS_DATABASE,
                  OPENGAUSS_USER, OPENGAUSS_PASSWORD

                Commands:
                  ping
                  list-schemas [--include-system]
                  list-tables [--schema <schema>] [--pattern <like-pattern>] [--limit <n>] [--include-system]
                  describe-table --schema <schema> --table <table>
                  schema-summary [--schema <schema>] [--pattern <like-pattern>] [--limit <n>] [--include-system]
                  search-schema --keyword <text> [--schema <schema>] [--limit <n>] [--include-system]

                Examples:
                  java -jar target/opengauss-connector-cli-1.0.0.jar list-tables --schema public
                  java -jar target/opengauss-connector-cli-1.0.0.jar describe-table --schema public --table orders
                  java -jar target/opengauss-connector-cli-1.0.0.jar search-schema --keyword customer --limit 10
                """);
    }

    @FunctionalInterface
    private interface SqlAction {
        Map<String, Object> execute(Connection connection) throws SQLException;
    }

    private static final class DatabaseConfig {
        private final String url;
        private final String user;
        private final String password;
        private final int loginTimeoutSeconds;

        private DatabaseConfig(String url, String user, String password, int loginTimeoutSeconds) {
            this.url = url;
            this.user = user;
            this.password = password;
            this.loginTimeoutSeconds = loginTimeoutSeconds;
        }

        static DatabaseConfig from(Cli cli) {
            String url = firstNonBlank(cli.option("url"), env("OPENGAUSS_URL"));
            if (url == null) {
                String host = firstNonBlank(cli.option("host"), env("OPENGAUSS_HOST"), "localhost");
                String port = firstNonBlank(cli.option("port"), env("OPENGAUSS_PORT"), "5432");
                String database = firstNonBlank(cli.option("database"), env("OPENGAUSS_DATABASE"));
                if (database == null) {
                    throw new CliException("Missing --url or --database/OPENGAUSS_DATABASE");
                }
                url = "jdbc:opengauss://" + host + ":" + port + "/" + database;
            }

            String user = firstNonBlank(cli.option("user"), env("OPENGAUSS_USER"));
            if (user == null) {
                throw new CliException("Missing --user or OPENGAUSS_USER");
            }
            String password = firstNonBlank(cli.option("password"), env("OPENGAUSS_PASSWORD"), "");
            int loginTimeout = cli.intOption("login-timeout", 10);
            return new DatabaseConfig(url, user, password, loginTimeout);
        }

        Connection open() throws SQLException {
            try {
                Class.forName("org.opengauss.Driver");
            } catch (ClassNotFoundException e) {
                throw new CliException("openGauss JDBC driver is not on the classpath");
            }

            DriverManager.setLoginTimeout(loginTimeoutSeconds);
            Properties properties = new Properties();
            properties.setProperty("user", user);
            properties.setProperty("password", password);
            return DriverManager.getConnection(url, properties);
        }
    }

    private static final class Cli {
        private final String command;
        private final Map<String, String> options;
        private final List<String> positionals;

        private Cli(String command, Map<String, String> options, List<String> positionals) {
            this.command = command;
            this.options = options;
            this.positionals = positionals;
        }

        static Cli parse(String[] args) {
            String command = null;
            Map<String, String> options = new LinkedHashMap<>();
            List<String> positionals = new ArrayList<>();

            for (int i = 0; i < args.length; i++) {
                String arg = args[i];
                if (arg.startsWith("--")) {
                    String option = arg.substring(2);
                    String key;
                    String value;
                    int equalsIndex = option.indexOf('=');
                    if (equalsIndex >= 0) {
                        key = option.substring(0, equalsIndex);
                        value = option.substring(equalsIndex + 1);
                    } else {
                        key = option;
                        if (i + 1 < args.length && !args[i + 1].startsWith("--")) {
                            value = args[++i];
                        } else {
                            value = "true";
                        }
                    }
                    options.put(key, value);
                } else if (command == null) {
                    command = arg;
                } else {
                    positionals.add(arg);
                }
            }
            return new Cli(command, options, positionals);
        }

        String option(String name) {
            String value = options.get(name);
            return value == null || value.isBlank() ? null : value;
        }

        String optionOrDefault(String name, String defaultValue) {
            String value = option(name);
            return value == null ? defaultValue : value;
        }

        String required(String name) {
            String value = option(name);
            if (value == null) {
                throw new CliException("Missing required option: --" + name);
            }
            return value;
        }

        boolean flag(String name) {
            String value = options.get(name);
            return value != null && (value.equalsIgnoreCase("true") || value.equals("1") || value.equalsIgnoreCase("yes"));
        }

        int intOption(String name, int defaultValue) {
            String value = option(name);
            if (value == null) {
                return defaultValue;
            }
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException e) {
                throw new CliException("Option --" + name + " must be an integer");
            }
        }
    }

    private static final class CliException extends RuntimeException {
        private CliException(String message) {
            super(message);
        }
    }

    private static final class Json {
        private Json() {
        }

        static String stringify(Object value) {
            StringBuilder builder = new StringBuilder();
            append(builder, value);
            return builder.toString();
        }

        private static void append(StringBuilder builder, Object value) {
            if (value == null) {
                builder.append("null");
            } else if (value instanceof String string) {
                appendString(builder, string);
            } else if (value instanceof Number || value instanceof Boolean) {
                builder.append(value);
            } else if (value instanceof Map<?, ?> map) {
                appendMap(builder, map);
            } else if (value instanceof Iterable<?> iterable) {
                appendIterable(builder, iterable);
            } else {
                appendString(builder, value.toString());
            }
        }

        private static void appendMap(StringBuilder builder, Map<?, ?> map) {
            builder.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                appendString(builder, Objects.toString(entry.getKey()));
                builder.append(':');
                append(builder, entry.getValue());
            }
            builder.append('}');
        }

        private static void appendIterable(StringBuilder builder, Iterable<?> iterable) {
            builder.append('[');
            boolean first = true;
            for (Object item : iterable) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                append(builder, item);
            }
            builder.append(']');
        }

        private static void appendString(StringBuilder builder, String value) {
            builder.append('"');
            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                switch (c) {
                    case '"' -> builder.append("\\\"");
                    case '\\' -> builder.append("\\\\");
                    case '\b' -> builder.append("\\b");
                    case '\f' -> builder.append("\\f");
                    case '\n' -> builder.append("\\n");
                    case '\r' -> builder.append("\\r");
                    case '\t' -> builder.append("\\t");
                    default -> {
                        if (c < 0x20) {
                            builder.append(String.format("\\u%04x", (int) c));
                        } else {
                            builder.append(c);
                        }
                    }
                }
            }
            builder.append('"');
        }
    }
}

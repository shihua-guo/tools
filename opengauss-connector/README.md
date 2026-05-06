# openGauss Connector CLI

A small Java command line tool for inspecting openGauss database schemas. It is
intended to be called by an AI skill or another orchestration layer, so command
results are emitted as JSON.

## Build

```powershell
mvn package
```

The executable jar is created at:

```text
target/opengauss-connector-cli-1.0.0.jar
```

## Connection

Pass a complete JDBC URL:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar ping `
  --url jdbc:opengauss://localhost:5432/postgres `
  --user gaussdb `
  --password secret
```

Or pass host/database pieces:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar list-tables `
  --host localhost `
  --port 5432 `
  --database postgres `
  --user gaussdb `
  --password secret `
  --schema public
```

Environment variables are also supported:

```text
OPENGAUSS_URL
OPENGAUSS_HOST
OPENGAUSS_PORT
OPENGAUSS_DATABASE
OPENGAUSS_USER
OPENGAUSS_PASSWORD
```

## Commands

```text
ping
list-schemas [--include-system]
list-tables [--schema <schema>] [--pattern <like-pattern>] [--limit <n>] [--include-system]
describe-table --schema <schema> --table <table>
schema-summary [--schema <schema>] [--pattern <like-pattern>] [--limit <n>] [--include-system]
search-schema --keyword <text> [--schema <schema>] [--limit <n>] [--include-system]
```

## Examples

List user tables:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar list-tables --schema public
```

Describe one table:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar describe-table --schema public --table orders
```

Search table and column metadata for a business term:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar search-schema --keyword customer --limit 10
```

Export a compact schema summary for AI context:

```powershell
java -jar target/opengauss-connector-cli-1.0.0.jar schema-summary --schema public --limit 30
```

## Notes

- The tool focuses on schema metadata, not arbitrary data queries.
- System schemas are hidden by default. Use `--include-system` when needed.
- `--pattern` uses SQL `LIKE` syntax, for example `biz_%` or `%order%`.

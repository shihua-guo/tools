# db-doctor

`db-doctor` is a read-only openGauss 6 quick diagnosis CLI for recovery drills.

It connects with the configured database user, runs built-in diagnostic SQL, prints a short console summary, and writes HTML/JSON reports.

## Build

```bash
mvn package
```

The runnable jar is generated at:

```text
target/db-doctor-1.0.0.jar
```

## Run

```bash
java -jar target/db-doctor-1.0.0.jar -c config.example.yml
```

Use your own config file for real credentials.

To keep one database connection open and run checks until the process is stopped:

```bash
java -jar target/db-doctor-1.0.0.jar -c config.example.yml --watch --interval-seconds 5
```

You can also enable this in the config file:

```yaml
diagnosis:
  continuous: true
  intervalSeconds: 5
```

In continuous mode, `db-doctor` connects once, reuses that JDBC connection for every check round, and closes it only when the process is stopped. If the connection is killed externally, the tool reports check errors but does not voluntarily release and reacquire the connection between rounds.

To run the embedded Web UI and refresh diagnosis data in place without generating a new HTML file every round:

```bash
java -jar target/db-doctor-1.0.0.jar -c config.example.yml --web --web-port 8080 --web-refresh-seconds 5
```

The Web UI exposes:

```text
http://127.0.0.1:8080/
GET  /api/status
GET  /api/summary
POST /api/refresh
```

Web mode stores the latest diagnosis result in memory and the browser renders it from the JSON API. It does not call the report writer, so `report.html` and `report.json` are ignored while `--web` is active.

To monitor multiple databases at the same time, start one process per config and assign each process a different port:

```bash
java -jar target/db-doctor-1.0.0.jar -c db1.yml --web --web-port 8081
java -jar target/db-doctor-1.0.0.jar -c db2.yml --web --web-port 8082
```

The same options can be set in the config file:

```yaml
web:
  enabled: true
  host: "127.0.0.1"
  port: 8080
  refreshSeconds: 5
```

## Safety

- The tool only executes built-in diagnostic SQL.
- SQL is checked before execution and must start with `SELECT`, `WITH`, or `SHOW`.
- Dangerous keywords and functions are rejected before JDBC execution.
- The JDBC connection is set to read-only.
- The tool never terminates sessions, modifies data, grants privileges, changes parameters, or creates/drops objects.

## Checks

- Basic database identity and key settings.
- Connection usage and session distribution.
- Optional user/IP whitelist anomalies.
- Long-running active SQL.
- Long transactions.
- Idle-in-transaction sessions.
- Lock wait and blocking chain.
- Thread wait status.
- Cumulative deadlock counter.
- High-privilege/login roles.
- DDL/DCL audit records in the last configured window, default 20 minutes.

## Reports

Reports are written to the configured output directory, for example:

```text
reports/db-doctor-20260514-153000.html
reports/db-doctor-20260514-153000.json
```

Continuous mode writes one timestamped report per round. If multiple reports are generated in the same second, `db-doctor` appends a numeric suffix to avoid overwriting earlier reports.

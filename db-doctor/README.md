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

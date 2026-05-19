package com.dbdoctor;

import picocli.CommandLine;

import java.nio.file.Path;
import java.sql.SQLException;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

@CommandLine.Command(
        name = "db-doctor",
        mixinStandardHelpOptions = true,
        version = "db-doctor 1.0.0",
        description = "Read-only openGauss quick diagnosis CLI."
)
public class App implements Callable<Integer> {
    @CommandLine.Option(
            names = {"-c", "--config"},
            required = true,
            description = "Path to config.yml."
    )
    private Path configPath;

    @CommandLine.Option(
            names = {"--watch", "--continuous"},
            description = "Run checks continuously and keep the database connection open until stopped."
    )
    private boolean watch;

    @CommandLine.Option(
            names = {"--interval-seconds"},
            description = "Seconds between continuous check rounds. Overrides diagnosis.intervalSeconds."
    )
    private Integer intervalSeconds;

    @CommandLine.Option(
            names = {"--web"},
            description = "Start the embedded Web UI instead of writing report files."
    )
    private boolean web;

    @CommandLine.Option(
            names = {"--web-host"},
            description = "Host address for Web UI. Overrides web.host."
    )
    private String webHost;

    @CommandLine.Option(
            names = {"--web-port"},
            description = "Port for Web UI. Overrides web.port."
    )
    private Integer webPort;

    @CommandLine.Option(
            names = {"--web-refresh-seconds"},
            description = "Seconds between Web UI diagnosis refreshes. Overrides web.refreshSeconds."
    )
    private Integer webRefreshSeconds;

    public static void main(String[] args) {
        int exitCode = new CommandLine(new App()).execute(args);
        System.exit(exitCode);
    }

    @Override
    public Integer call() {
        try {
            DoctorConfig config = ConfigLoader.load(configPath);
            applyCliOverrides(config);
            if (config.web.enabled) {
                return runWeb(config);
            }
            if (config.diagnosis.continuous) {
                return runContinuous(config);
            }
            return runOnce(config);
        } catch (Exception e) {
            System.err.println("db-doctor failed: " + e.getMessage());
            return 1;
        }
    }

    private void applyCliOverrides(DoctorConfig config) {
        if (watch) {
            config.diagnosis.continuous = true;
        }
        if (intervalSeconds != null) {
            config.diagnosis.intervalSeconds = intervalSeconds;
        }
        if (web) {
            config.web.enabled = true;
        }
        if (webHost != null) {
            config.web.host = webHost;
        }
        if (webPort != null) {
            config.web.port = webPort;
        }
        if (webRefreshSeconds != null) {
            config.web.refreshSeconds = webRefreshSeconds;
        }
        config.normalize();
    }

    private Integer runOnce(DoctorConfig config) throws Exception {
        DiagnosticSummary summary = new DiagnosisService(config).run();
        ReportWriter.ReportFiles files = new ReportWriter(config).write(summary);
        printConsoleSummary(summary, files);
        return summary.finalSeverity == Severity.CRITICAL ? 2 : 0;
    }

    private Integer runWeb(DoctorConfig config) throws Exception {
        new WebServer(config).startAndBlock();
        return 0;
    }

    private Integer runContinuous(DoctorConfig config) throws Exception {
        AtomicBoolean running = new AtomicBoolean(true);
        AtomicReference<DbClient> activeClient = new AtomicReference<>();
        Thread mainThread = Thread.currentThread();
        Thread shutdownHook = new Thread(() -> {
            running.set(false);
            DbClient client = activeClient.get();
            closeClient(client);
            mainThread.interrupt();
        }, "db-doctor-shutdown");

        Runtime.getRuntime().addShutdownHook(shutdownHook);
        int exitCode = 0;
        long round = 1;
        System.out.println("db-doctor continuous mode started");
        System.out.println("Target: " + config.databaseTarget());
        System.out.println("Interval: " + config.diagnosis.intervalSeconds + " seconds");
        System.out.println("Press Ctrl-C to stop");

        try {
            DbClient client = DbClient.connect(config);
            activeClient.set(client);
            try {
                DiagnosisService service = new DiagnosisService(config);
                while (running.get()) {
                    DiagnosticSummary summary = service.run(client);
                    ReportWriter.ReportFiles files = new ReportWriter(config).write(summary);
                    printConsoleSummary(summary, files, round);
                    if (summary.finalSeverity == Severity.CRITICAL) {
                        exitCode = 2;
                    }
                    if (!sleepBeforeNextRound(config.diagnosis.intervalSeconds, running)) {
                        break;
                    }
                    round++;
                }
            } finally {
                activeClient.set(null);
                closeClient(client);
            }
        } finally {
            removeShutdownHook(shutdownHook);
        }

        System.out.println("db-doctor continuous mode stopped");
        return exitCode;
    }

    private static void closeClient(DbClient client) {
        if (client == null) {
            return;
        }
        try {
            client.close();
        } catch (SQLException e) {
            System.err.println("db-doctor failed to close database connection: " + e.getMessage());
        }
    }

    private boolean sleepBeforeNextRound(int intervalSeconds, AtomicBoolean running) {
        try {
            TimeUnit.SECONDS.sleep(intervalSeconds);
            return running.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private void removeShutdownHook(Thread shutdownHook) {
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException ignored) {
            // JVM shutdown is already in progress.
        }
    }

    private void printConsoleSummary(DiagnosticSummary summary, ReportWriter.ReportFiles files) {
        printConsoleSummary(summary, files, null);
    }

    private void printConsoleSummary(DiagnosticSummary summary, ReportWriter.ReportFiles files, Long round) {
        System.out.println();
        if (round == null) {
            System.out.println("db-doctor finished");
        } else {
            System.out.println("db-doctor round " + round + " finished");
        }
        System.out.println("Target: " + summary.databaseTarget);
        System.out.println("Conclusion: " + summary.finalSeverity);
        if (!summary.priorityFindings.isEmpty()) {
            System.out.println();
            System.out.println("Priority findings:");
            int index = 1;
            for (String finding : summary.priorityFindings) {
                System.out.println(index++ + ". " + finding);
            }
        }
        if (files.htmlPath() != null) {
            System.out.println("HTML report: " + files.htmlPath().toAbsolutePath());
        }
        if (files.jsonPath() != null) {
            System.out.println("JSON report: " + files.jsonPath().toAbsolutePath());
        }
        System.out.println();
    }
}

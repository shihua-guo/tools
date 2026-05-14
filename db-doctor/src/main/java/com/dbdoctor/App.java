package com.dbdoctor;

import picocli.CommandLine;

import java.nio.file.Path;
import java.util.concurrent.Callable;

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

    public static void main(String[] args) {
        int exitCode = new CommandLine(new App()).execute(args);
        System.exit(exitCode);
    }

    @Override
    public Integer call() {
        try {
            DoctorConfig config = ConfigLoader.load(configPath);
            DiagnosticSummary summary = new DiagnosisService(config).run();
            ReportWriter.ReportFiles files = new ReportWriter(config).write(summary);
            printConsoleSummary(summary, files);
            return summary.finalSeverity == Severity.CRITICAL ? 2 : 0;
        } catch (Exception e) {
            System.err.println("db-doctor failed: " + e.getMessage());
            return 1;
        }
    }

    private void printConsoleSummary(DiagnosticSummary summary, ReportWriter.ReportFiles files) {
        System.out.println();
        System.out.println("db-doctor finished");
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
        if (files.markdownPath() != null) {
            System.out.println("Markdown report: " + files.markdownPath().toAbsolutePath());
        }
        if (files.jsonPath() != null) {
            System.out.println("JSON report: " + files.jsonPath().toAbsolutePath());
        }
        System.out.println();
    }
}

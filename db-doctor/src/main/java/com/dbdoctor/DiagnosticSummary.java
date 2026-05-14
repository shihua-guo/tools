package com.dbdoctor;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class DiagnosticSummary {
    public Instant generatedAt = Instant.now();
    public String databaseTarget;
    public Severity finalSeverity = Severity.OK;
    public List<String> priorityFindings = new ArrayList<>();
    public List<DiagnosticResult> results = new ArrayList<>();

    public void addResult(DiagnosticResult result) {
        results.add(result);
        Severity finalCandidate = result.severity.toFinalSeverity();
        finalSeverity = Severity.max(finalSeverity, finalCandidate);
        if (finalCandidate.atLeast(Severity.WARNING)) {
            priorityFindings.add("[" + finalCandidate + "] " + result.title + ": " + result.conclusion);
        }
    }
}

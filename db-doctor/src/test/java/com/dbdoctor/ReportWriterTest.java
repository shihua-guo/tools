package com.dbdoctor;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReportWriterTest {
    @TempDir
    Path tempDir;

    @Test
    @SuppressWarnings("deprecation")
    void writesHtmlReportWithOverviewLinksAndNoMarkdown() throws Exception {
        DoctorConfig config = new DoctorConfig();
        config.report.outputDir = tempDir.toString();
        config.report.html = true;
        config.report.markdown = true;
        config.report.json = false;

        DiagnosticSummary summary = new DiagnosticSummary();
        summary.generatedAt = Instant.parse("2026-05-18T02:20:00Z");
        summary.databaseTarget = "127.0.0.1:26000/postgres";
        summary.addResult(DiagnosticResult.of("basic_info", "基础信息", Severity.OK, "数据库连接正常", queryResult()));
        summary.addResult(DiagnosticResult.of("recent_ddl_dcl", "最近 DDL/DCL 审计", Severity.WARNING, "发现 DDL/DCL 审计记录", queryResult()));

        ReportWriter.ReportFiles files = new ReportWriter(config).write(summary);

        assertTrue(Files.isRegularFile(files.htmlPath()));
        try (Stream<Path> paths = Files.list(tempDir)) {
            assertTrue(paths.noneMatch(path -> path.getFileName().toString().endsWith(".md")));
        }

        String html = new String(Files.readAllBytes(files.htmlPath()), java.nio.charset.StandardCharsets.UTF_8);
        assertTrue(html.contains("<h2>检查概览</h2>"));
        assertTrue(html.contains("href=\"#check-basic_info\""));
        assertTrue(html.contains("href=\"#check-recent_ddl_dcl\""));
        assertTrue(html.contains("id=\"check-recent_ddl_dcl\""));
        assertTrue(html.contains("最近 DDL/DCL 审计: 发现 DDL/DCL 审计记录"));
        assertFalse(html.contains("```sql"));
    }

    private QueryResult queryResult() {
        QueryResult queryResult = new QueryResult();
        queryResult.sql = "SELECT 1";
        return queryResult;
    }
}

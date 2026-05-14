package com.dbdoctor;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.StringJoiner;

public class ReportWriter {
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneId.systemDefault());
    private static final DateTimeFormatter DISPLAY_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss z").withZone(ZoneId.systemDefault());

    private final DoctorConfig config;

    public ReportWriter(DoctorConfig config) {
        this.config = config;
    }

    public ReportFiles write(DiagnosticSummary summary) throws IOException {
        Path outputDir = Path.of(config.report.outputDir);
        Files.createDirectories(outputDir);
        String baseName = "db-doctor-" + FILE_TIME.format(summary.generatedAt);
        Path markdownPath = null;
        Path jsonPath = null;
        if (config.report.markdown) {
            markdownPath = outputDir.resolve(baseName + ".md");
            Files.writeString(markdownPath, toMarkdown(summary), StandardCharsets.UTF_8);
        }
        if (config.report.json) {
            jsonPath = outputDir.resolve(baseName + ".json");
            ObjectMapper mapper = new ObjectMapper()
                    .registerModule(new JavaTimeModule())
                    .enable(SerializationFeature.INDENT_OUTPUT)
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
            mapper.writeValue(jsonPath.toFile(), summary);
        }
        return new ReportFiles(markdownPath, jsonPath);
    }

    private String toMarkdown(DiagnosticSummary summary) {
        StringBuilder md = new StringBuilder();
        md.append("# openGauss 诊断报告\n\n");
        md.append("- 生成时间: ").append(DISPLAY_TIME.format(summary.generatedAt)).append('\n');
        md.append("- 目标数据库: ").append(escapeInline(summary.databaseTarget)).append('\n');
        md.append("- 最终结论: **").append(summary.finalSeverity).append("**\n\n");

        md.append("## 一、优先级最高的问题\n\n");
        if (summary.priorityFindings.isEmpty()) {
            md.append("未发现 WARNING 或 CRITICAL 级别问题。\n\n");
        } else {
            int index = 1;
            for (String finding : summary.priorityFindings) {
                md.append(index++).append(". ").append(escapeInline(finding)).append('\n');
            }
            md.append('\n');
        }

        md.append("## 二、检查详情\n\n");
        for (DiagnosticResult result : summary.results) {
            appendResult(md, result);
        }
        return md.toString();
    }

    private void appendResult(StringBuilder md, DiagnosticResult result) {
        md.append("### [").append(result.severity).append("] ").append(escapeInline(result.title)).append("\n\n");
        md.append("- 检查 ID: `").append(result.id).append("`\n");
        md.append("- 结论: ").append(escapeInline(result.conclusion)).append("\n");
        if (result.error != null) {
            md.append("- 错误: `").append(escapeInline(result.error)).append("`\n");
        }
        for (String observation : result.observations) {
            md.append("- 观察: ").append(escapeInline(observation)).append("\n");
        }
        md.append('\n');
        if (result.queryResult != null) {
            md.append("- 执行耗时: ").append(result.queryResult.elapsedMs).append(" ms\n");
            md.append("- 结果行数: ").append(result.queryResult.rowCount()).append("\n\n");
            md.append("```sql\n").append(result.queryResult.sql.strip()).append("\n```\n\n");
            appendTable(md, result.queryResult);
        }
    }

    private void appendTable(StringBuilder md, QueryResult queryResult) {
        if (queryResult.rows.isEmpty()) {
            md.append("_无结果行。_\n\n");
            return;
        }
        List<String> columns = queryResult.columns;
        StringJoiner header = new StringJoiner(" | ", "| ", " |");
        StringJoiner separator = new StringJoiner(" | ", "| ", " |");
        for (String column : columns) {
            header.add(escapeCell(column));
            separator.add("---");
        }
        md.append(header).append('\n');
        md.append(separator).append('\n');
        for (Map<String, String> row : queryResult.rows) {
            StringJoiner line = new StringJoiner(" | ", "| ", " |");
            for (String column : columns) {
                line.add(escapeCell(row.get(column)));
            }
            md.append(line).append('\n');
        }
        md.append('\n');
    }

    private String escapeCell(String value) {
        if (value == null) {
            return "";
        }
        return value
                .replace("\\", "\\\\")
                .replace("|", "\\|")
                .replace("\r\n", "<br>")
                .replace("\n", "<br>")
                .replace("\r", "<br>");
    }

    private String escapeInline(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ");
    }

    public record ReportFiles(Path markdownPath, Path jsonPath) {
    }
}

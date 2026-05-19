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

public class ReportWriter {
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneId.systemDefault());
    private static final DateTimeFormatter DISPLAY_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss z").withZone(ZoneId.systemDefault());

    private final DoctorConfig config;

    public ReportWriter(DoctorConfig config) {
        this.config = config;
    }

    public ReportFiles write(DiagnosticSummary summary) throws IOException {
        Path outputDir = java.nio.file.Paths.get(config.report.outputDir);
        Files.createDirectories(outputDir);
        String baseName = "db-doctor-" + FILE_TIME.format(summary.generatedAt);
        Path htmlPath = null;
        Path jsonPath = null;
        if (config.report.html) {
            htmlPath = uniqueReportPath(outputDir, baseName, ".html");
            Files.write(htmlPath, toHtml(summary).getBytes(StandardCharsets.UTF_8));
        }
        if (config.report.json) {
            jsonPath = uniqueReportPath(outputDir, baseName, ".json");
            ObjectMapper mapper = new ObjectMapper()
                    .registerModule(new JavaTimeModule())
                    .enable(SerializationFeature.INDENT_OUTPUT)
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
            mapper.writeValue(jsonPath.toFile(), summary);
        }
        return new ReportFiles(htmlPath, jsonPath);
    }

    private Path uniqueReportPath(Path outputDir, String baseName, String extension) {
        Path path = outputDir.resolve(baseName + extension);
        int index = 2;
        while (Files.exists(path)) {
            path = outputDir.resolve(baseName + "-" + index + extension);
            index++;
        }
        return path;
    }

    String toHtml(DiagnosticSummary summary) {
        StringBuilder html = new StringBuilder();
        html.append("<!doctype html>\n");
        html.append("<html lang=\"zh-CN\">\n");
        html.append("<head>\n");
        html.append("<meta charset=\"utf-8\">\n");
        html.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n");
        html.append("<title>openGauss 诊断报告</title>\n");
        html.append("<style>\n");
        html.append(":root{color-scheme:light;--bg:#f6f8fa;--panel:#fff;--text:#1f2328;--muted:#59636e;--line:#d0d7de;--ok:#1f883d;--warn:#9a6700;--critical:#cf222e;--info:#0969da;}\n");
        html.append("*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;line-height:1.5}main{max-width:1180px;margin:0 auto;padding:32px 24px 56px}h1{margin:0 0 16px;font-size:30px}h2{margin:32px 0 12px;font-size:20px}h3{margin:0 0 12px;font-size:18px}.meta,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:24px}.label{display:block;color:var(--muted);font-size:12px}.value{font-weight:600}.list{margin:0;padding-left:22px}.list li{margin:8px 0}.overview a{color:inherit;text-decoration:none}.overview a:hover{text-decoration:underline}.severity{display:inline-block;min-width:78px;margin-right:8px;font-weight:700}.severity.OK{color:var(--ok)}.severity.INFO{color:var(--info)}.severity.WARNING{color:var(--warn)}.severity.CRITICAL,.severity.ERROR{color:var(--critical)}.result{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;margin:14px 0}.result-meta{margin:0 0 12px;padding-left:20px}.observations{margin:12px 0;padding-left:20px}pre{overflow:auto;background:#f6f8fa;border:1px solid var(--line);border-radius:6px;padding:12px}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}table{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}th,td{border:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}th{background:#f6f8fa}.empty{color:var(--muted);font-style:italic}.top-link{font-size:13px}a{color:#0969da}\n");
        html.append("</style>\n");
        html.append("</head>\n");
        html.append("<body>\n");
        html.append("<main>\n");
        html.append("<h1 id=\"top\">openGauss 诊断报告</h1>\n");
        html.append("<section class=\"meta\" aria-label=\"报告元信息\">\n");
        appendMeta(html, "生成时间", DISPLAY_TIME.format(summary.generatedAt));
        appendMeta(html, "目标数据库", summary.databaseTarget);
        appendMeta(html, "最终结论", String.valueOf(summary.finalSeverity));
        html.append("</section>\n");

        html.append("<section class=\"panel\">\n");
        html.append("<h2>优先级最高的问题</h2>\n");
        if (summary.priorityFindings.isEmpty()) {
            html.append("<p class=\"empty\">未发现 WARNING 或 CRITICAL 级别问题。</p>\n");
        } else {
            html.append("<ol class=\"list\">\n");
            for (String finding : summary.priorityFindings) {
                html.append("<li>").append(escapeHtml(finding)).append("</li>\n");
            }
            html.append("</ol>\n");
        }
        html.append("</section>\n");

        html.append("<section class=\"panel overview\" style=\"margin-top:18px\">\n");
        html.append("<h2>检查概览</h2>\n");
        html.append("<ol class=\"list\">\n");
        for (DiagnosticResult result : summary.results) {
            html.append("<li><a href=\"#").append(anchorId(result)).append("\">");
            html.append("<span class=\"severity ").append(severityClass(result.severity)).append("\">")
                    .append(escapeHtml(String.valueOf(result.severity))).append("</span>");
            html.append(escapeHtml(result.title)).append(": ").append(escapeHtml(result.conclusion));
            html.append("</a></li>\n");
        }
        html.append("</ol>\n");
        html.append("</section>\n");

        html.append("<section>\n");
        html.append("<h2>检查详情</h2>\n");
        for (DiagnosticResult result : summary.results) {
            appendResult(html, result);
        }
        html.append("</section>\n");
        html.append("</main>\n");
        html.append("</body>\n");
        html.append("</html>\n");
        return html.toString();
    }

    private void appendMeta(StringBuilder html, String label, String value) {
        html.append("<div><span class=\"label\">").append(escapeHtml(label)).append("</span>");
        html.append("<span class=\"value\">").append(escapeHtml(value)).append("</span></div>\n");
    }

    private void appendResult(StringBuilder html, DiagnosticResult result) {
        html.append("<article class=\"result\" id=\"").append(anchorId(result)).append("\">\n");
        html.append("<h3><span class=\"severity ").append(severityClass(result.severity)).append("\">")
                .append(escapeHtml(String.valueOf(result.severity))).append("</span>")
                .append(escapeHtml(result.title)).append("</h3>\n");
        html.append("<ul class=\"result-meta\">\n");
        html.append("<li>检查 ID: <code>").append(escapeHtml(result.id)).append("</code></li>\n");
        html.append("<li>结论: ").append(escapeHtml(result.conclusion)).append("</li>\n");
        if (result.error != null) {
            html.append("<li>错误: <code>").append(escapeHtml(result.error)).append("</code></li>\n");
        }
        html.append("</ul>\n");
        if (!result.observations.isEmpty()) {
            html.append("<ul class=\"observations\">\n");
            for (String observation : result.observations) {
                html.append("<li>观察: ").append(escapeHtml(observation)).append("</li>\n");
            }
            html.append("</ul>\n");
        }
        if (result.queryResult != null) {
            html.append("<ul class=\"result-meta\">\n");
            html.append("<li>执行耗时: ").append(result.queryResult.elapsedMs).append(" ms</li>\n");
            html.append("<li>结果行数: ").append(result.queryResult.rowCount()).append("</li>\n");
            html.append("</ul>\n");
            if (result.queryResult.sql != null) {
                html.append("<pre><code>").append(escapeHtml(result.queryResult.sql.trim())).append("</code></pre>\n");
            }
            appendTable(html, result.queryResult);
        }
        html.append("<a class=\"top-link\" href=\"#top\">返回顶部</a>\n");
        html.append("</article>\n");
    }

    private void appendTable(StringBuilder html, QueryResult queryResult) {
        if (queryResult.rows.isEmpty()) {
            html.append("<p class=\"empty\">无结果行。</p>\n");
            return;
        }
        List<String> columns = queryResult.columns;
        html.append("<table>\n<thead>\n<tr>");
        for (String column : columns) {
            html.append("<th>").append(escapeHtml(column)).append("</th>");
        }
        html.append("</tr>\n</thead>\n<tbody>\n");
        for (Map<String, String> row : queryResult.rows) {
            html.append("<tr>");
            for (String column : columns) {
                html.append("<td>").append(escapeHtml(row.get(column))).append("</td>");
            }
            html.append("</tr>\n");
        }
        html.append("</tbody>\n</table>\n");
    }

    private String anchorId(DiagnosticResult result) {
        return "check-" + safeId(result.id);
    }

    private String safeId(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder id = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '_' || ch == '-') {
                id.append(ch);
            } else {
                id.append('-');
            }
        }
        return id.toString();
    }

    private String severityClass(Severity severity) {
        return severity == null ? "INFO" : severity.name();
    }

    private String escapeHtml(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder escaped = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '&':
                    escaped.append("&amp;");
                    break;
                case '<':
                    escaped.append("&lt;");
                    break;
                case '>':
                    escaped.append("&gt;");
                    break;
                case '"':
                    escaped.append("&quot;");
                    break;
                case '\'':
                    escaped.append("&#39;");
                    break;
                default:
                    escaped.append(ch);
                    break;
            }
        }
        return escaped.toString();
    }

    public static class ReportFiles {
        public final Path htmlPath;
        public final Path jsonPath;

        public ReportFiles(Path htmlPath, Path jsonPath) {
            this.htmlPath = htmlPath;
            this.jsonPath = jsonPath;
        }

        public Path htmlPath() {
            return htmlPath;
        }

        public Path jsonPath() {
            return jsonPath;
        }
    }
}

package com.dbdoctor;

import java.util.ArrayList;
import java.util.List;

public class DiagnosticResult {
    public String id;
    public String title;
    public Severity severity;
    public String conclusion;
    public List<String> observations = new ArrayList<>();
    public QueryResult queryResult;
    public String error;

    public static DiagnosticResult of(String id, String title, Severity severity, String conclusion, QueryResult queryResult) {
        DiagnosticResult result = new DiagnosticResult();
        result.id = id;
        result.title = title;
        result.severity = severity;
        result.conclusion = conclusion;
        result.queryResult = queryResult;
        return result;
    }

    public static DiagnosticResult error(String id, String title, Exception exception) {
        DiagnosticResult result = new DiagnosticResult();
        result.id = id;
        result.title = title;
        result.severity = Severity.ERROR;
        result.conclusion = "检查执行失败";
        result.error = exception.getClass().getSimpleName() + ": " + exception.getMessage();
        result.observations.add("该检查未能完成，请优先确认账号权限、openGauss 版本和视图/函数可用性。");
        return result;
    }
}

package com.dbdoctor;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class QueryResult {
    public String sql;
    public long elapsedMs;
    public List<String> columns = new ArrayList<>();
    public List<Map<String, String>> rows = new ArrayList<>();

    public int rowCount() {
        return rows == null ? 0 : rows.size();
    }

    public Map<String, String> firstRow() {
        if (rows == null || rows.isEmpty()) {
            return new LinkedHashMap<>();
        }
        return rows.get(0);
    }
}

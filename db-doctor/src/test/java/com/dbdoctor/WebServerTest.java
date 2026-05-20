package com.dbdoctor;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class WebServerTest {
    @Test
    void shipsIndexHtmlWithApiRefreshUi() throws Exception {
        String html = WebServer.indexHtmlForTest();

        assertTrue(html.contains("db-doctor Web UI"));
        assertTrue(html.contains("/api/status"));
        assertTrue(html.contains("/api/refresh"));
        assertTrue(html.contains("立即刷新"));
        assertTrue(html.contains("<h2>检查概览</h2>"));
        assertTrue(html.contains("id=\"checkOverview\""));
        assertTrue(html.contains("function renderOverview(results)"));
        assertTrue(html.contains("link.href = \"#\" + anchorId(result);"));
        assertTrue(html.contains("topLink.href = \"#top\";"));
    }
}

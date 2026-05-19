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
    }
}

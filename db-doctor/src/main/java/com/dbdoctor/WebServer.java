package com.dbdoctor;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class WebServer {
    private static final String INDEX_RESOURCE = "/com/dbdoctor/web/index.html";
    private static final ObjectMapper JSON = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .enable(SerializationFeature.INDENT_OUTPUT)
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private final DoctorConfig config;
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread thread = new Thread(r, "db-doctor-web-refresh");
        thread.setDaemon(true);
        return thread;
    });
    private final AtomicReference<DiagnosticSummary> latestSummary = new AtomicReference<>();
    private final AtomicBoolean refreshRunning = new AtomicBoolean(false);
    private final AtomicBoolean manualRefreshQueued = new AtomicBoolean(false);
    private final AtomicBoolean stopped = new AtomicBoolean(false);
    private final AtomicLong round = new AtomicLong(0);
    private final CountDownLatch stopLatch = new CountDownLatch(1);

    private volatile HttpServer server;
    private volatile Instant lastStartedAt;
    private volatile Instant lastFinishedAt;

    public WebServer(DoctorConfig config) {
        this.config = config;
    }

    public void startAndBlock() throws IOException, InterruptedException {
        InetSocketAddress address = new InetSocketAddress(config.web.host, config.web.port);
        server = HttpServer.create(address, 0);
        server.createContext("/", this::handleIndex);
        server.createContext("/api/status", this::handleStatus);
        server.createContext("/api/summary", this::handleStatus);
        server.createContext("/api/refresh", this::handleRefresh);
        server.createContext("/health", this::handleHealth);
        server.setExecutor(Executors.newCachedThreadPool(r -> {
            Thread thread = new Thread(r, "db-doctor-web-http");
            thread.setDaemon(true);
            return thread;
        }));

        Thread shutdownHook = new Thread(this::stop, "db-doctor-web-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdownHook);
        scheduler.scheduleWithFixedDelay(this::refreshSafely, 0, config.web.refreshSeconds, TimeUnit.SECONDS);
        server.start();

        System.out.println("db-doctor Web UI started");
        System.out.println("Target: " + config.databaseTarget());
        System.out.println("Refresh interval: " + config.web.refreshSeconds + " seconds");
        System.out.println("Listening on: " + config.web.host + ":" + config.web.port);
        System.out.println("Web UI: http://" + displayHost(config.web.host) + ":" + config.web.port + "/");
        System.out.println("Press Ctrl-C to stop");

        try {
            stopLatch.await();
        } finally {
            stop();
            removeShutdownHook(shutdownHook);
        }
    }

    private void handleIndex(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod()) || !isIndexPath(exchange)) {
            sendText(exchange, 404, "Not found");
            return;
        }
        exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        sendBytes(exchange, 200, indexHtmlBytes());
    }

    private void handleStatus(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            sendJson(exchange, 405, statusPayload());
            return;
        }
        sendJson(exchange, 200, statusPayload());
    }

    private void handleRefresh(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "POST");
            sendJson(exchange, 405, statusPayload());
            return;
        }
        boolean accepted = queueManualRefresh();
        Map<String, Object> payload = statusPayload();
        payload.put("accepted", accepted);
        sendJson(exchange, accepted ? 202 : 409, payload);
    }

    private void handleHealth(HttpExchange exchange) throws IOException {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("ok", !stopped.get());
        payload.put("refreshRunning", refreshRunning.get());
        sendJson(exchange, 200, payload);
    }

    private boolean isIndexPath(HttpExchange exchange) {
        String path = exchange.getRequestURI().getPath();
        return "/".equals(path) || "/index.html".equals(path);
    }

    private Map<String, Object> statusPayload() {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("target", config.databaseTarget());
        payload.put("round", round.get());
        payload.put("refreshSeconds", config.web.refreshSeconds);
        payload.put("refreshRunning", refreshRunning.get());
        payload.put("manualRefreshQueued", manualRefreshQueued.get());
        payload.put("lastStartedAt", lastStartedAt);
        payload.put("lastFinishedAt", lastFinishedAt);
        payload.put("summary", latestSummary.get());
        return payload;
    }

    private boolean queueManualRefresh() {
        if (!manualRefreshQueued.compareAndSet(false, true)) {
            return false;
        }
        try {
            scheduler.execute(() -> {
                try {
                    refreshSafely();
                } finally {
                    manualRefreshQueued.set(false);
                }
            });
            return true;
        } catch (RejectedExecutionException e) {
            manualRefreshQueued.set(false);
            return false;
        }
    }

    private void refreshSafely() {
        if (!refreshRunning.compareAndSet(false, true)) {
            return;
        }
        lastStartedAt = Instant.now();
        try {
            DiagnosticSummary summary = new DiagnosisService(config).run();
            latestSummary.set(summary);
            round.incrementAndGet();
        } catch (Exception e) {
            DiagnosticSummary summary = new DiagnosticSummary();
            summary.databaseTarget = config.databaseTarget();
            summary.addResult(DiagnosticResult.error("web_refresh", "Web UI 刷新", e));
            latestSummary.set(summary);
            round.incrementAndGet();
        } finally {
            lastFinishedAt = Instant.now();
            refreshRunning.set(false);
        }
    }

    private void stop() {
        if (!stopped.compareAndSet(false, true)) {
            return;
        }
        scheduler.shutdownNow();
        HttpServer currentServer = server;
        if (currentServer != null) {
            currentServer.stop(0);
        }
        stopLatch.countDown();
    }

    private void removeShutdownHook(Thread shutdownHook) {
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException ignored) {
            // JVM shutdown is already in progress.
        }
    }

    private void sendJson(HttpExchange exchange, int statusCode, Object payload) throws IOException {
        byte[] bytes = JSON.writeValueAsBytes(payload);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        sendBytes(exchange, statusCode, bytes);
    }

    private void sendText(HttpExchange exchange, int statusCode, String text) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        sendBytes(exchange, statusCode, text.getBytes(StandardCharsets.UTF_8));
    }

    private void sendBytes(HttpExchange exchange, int statusCode, byte[] bytes) throws IOException {
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private String displayHost(String host) {
        if ("0.0.0.0".equals(host) || "::".equals(host)) {
            return "127.0.0.1";
        }
        return host;
    }

    static String indexHtmlForTest() throws IOException {
        return new String(indexHtmlBytes(), StandardCharsets.UTF_8);
    }

    private static byte[] indexHtmlBytes() throws IOException {
        try (InputStream input = WebServer.class.getResourceAsStream(INDEX_RESOURCE)) {
            if (input == null) {
                throw new IOException("missing resource: " + INDEX_RESOURCE);
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
            return output.toByteArray();
        }
    }
}

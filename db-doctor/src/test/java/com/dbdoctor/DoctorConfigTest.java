package com.dbdoctor;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DoctorConfigTest {
    @Test
    void normalizesContinuousInterval() {
        DoctorConfig config = new DoctorConfig();
        config.diagnosis.intervalSeconds = 0;

        config.normalize();

        assertEquals(1, config.diagnosis.intervalSeconds);
    }

    @Test
    void normalizesWebOptions() {
        DoctorConfig config = new DoctorConfig();
        config.web.host = "";
        config.web.port = 70000;
        config.web.refreshSeconds = 0;

        config.normalize();

        assertEquals("127.0.0.1", config.web.host);
        assertEquals(65535, config.web.port);
        assertEquals(1, config.web.refreshSeconds);
    }
}

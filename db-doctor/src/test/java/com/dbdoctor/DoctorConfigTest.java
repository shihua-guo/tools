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
}

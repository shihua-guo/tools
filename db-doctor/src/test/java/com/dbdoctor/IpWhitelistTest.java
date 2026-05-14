package com.dbdoctor;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IpWhitelistTest {
    @Test
    void supportsExactAndIpv4CidrEntries() {
        IpWhitelist whitelist = new IpWhitelist(List.of("127.0.0.1", "10.0.0.0/24"));

        assertTrue(whitelist.contains("127.0.0.1"));
        assertTrue(whitelist.contains("10.0.0.15"));
        assertFalse(whitelist.contains("10.0.1.15"));
    }

    @Test
    void treatsNullClientAddressAsLocalAllowed() {
        IpWhitelist whitelist = new IpWhitelist(List.of());
        assertTrue(whitelist.contains(null));
        assertTrue(whitelist.contains("local"));
    }
}

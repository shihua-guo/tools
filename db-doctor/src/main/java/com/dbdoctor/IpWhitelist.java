package com.dbdoctor;

import java.math.BigInteger;
import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class IpWhitelist {
    private final List<String> exact = new ArrayList<>();
    private final List<CidrV4> cidrV4 = new ArrayList<>();

    public IpWhitelist(List<String> entries) {
        if (entries == null) {
            return;
        }
        for (String entry : entries) {
            if (entry == null || entry.isBlank()) {
                continue;
            }
            String normalized = entry.trim().toLowerCase(Locale.ROOT);
            if (normalized.contains("/") && normalized.indexOf(':') < 0) {
                CidrV4 cidr = CidrV4.parse(normalized);
                if (cidr != null) {
                    cidrV4.add(cidr);
                }
            } else {
                exact.add(normalized);
            }
        }
    }

    public boolean contains(String ip) {
        if (ip == null || ip.isBlank()) {
            return true;
        }
        String normalized = ip.trim().toLowerCase(Locale.ROOT);
        if ("local".equals(normalized) || "<internal>".equals(normalized)) {
            return true;
        }
        if (exact.contains(normalized)) {
            return true;
        }
        Long value = ipv4ToLong(normalized);
        if (value == null) {
            return false;
        }
        for (CidrV4 cidr : cidrV4) {
            if (cidr.contains(value)) {
                return true;
            }
        }
        return false;
    }

    private static Long ipv4ToLong(String value) {
        try {
            InetAddress address = InetAddress.getByName(value);
            byte[] bytes = address.getAddress();
            if (bytes.length != 4) {
                return null;
            }
            return new BigInteger(1, bytes).longValue();
        } catch (Exception ignored) {
            return null;
        }
    }

    private record CidrV4(long network, long mask) {
        static CidrV4 parse(String value) {
            String[] parts = value.split("/");
            if (parts.length != 2) {
                return null;
            }
            Long base = ipv4ToLong(parts[0]);
            if (base == null) {
                return null;
            }
            try {
                int prefix = Integer.parseInt(parts[1]);
                if (prefix < 0 || prefix > 32) {
                    return null;
                }
                long mask = prefix == 0 ? 0 : 0xffffffffL << (32 - prefix) & 0xffffffffL;
                return new CidrV4(base & mask, mask);
            } catch (NumberFormatException e) {
                return null;
            }
        }

        boolean contains(long value) {
            return (value & mask) == network;
        }
    }
}

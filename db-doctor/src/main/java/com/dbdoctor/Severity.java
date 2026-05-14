package com.dbdoctor;

public enum Severity {
    INFO(0),
    OK(0),
    WARNING(1),
    CRITICAL(2),
    ERROR(3);

    private final int rank;

    Severity(int rank) {
        this.rank = rank;
    }

    public boolean atLeast(Severity other) {
        return rank >= other.rank;
    }

    public Severity toFinalSeverity() {
        return this == ERROR ? CRITICAL : this;
    }

    public static Severity max(Severity left, Severity right) {
        return left.rank >= right.rank ? left : right;
    }
}

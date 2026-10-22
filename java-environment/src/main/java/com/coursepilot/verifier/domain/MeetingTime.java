package com.coursepilot.verifier.domain;

import java.util.Set;

public class MeetingTime {

    private final int dayOfWeek;      // 1=周一 … 7=周日
    private final int startSection;
    private final int endSection;
    private final Set<Integer> weeks;

    public MeetingTime(int dayOfWeek, int startSection, int endSection, Set<Integer> weeks) {
        this.dayOfWeek = dayOfWeek;
        this.startSection = startSection;
        this.endSection = endSection;
        this.weeks = weeks;
    }

    public int getDayOfWeek() { return dayOfWeek; }
    public int getStartSection() { return startSection; }
    public int getEndSection() { return endSection; }
    public Set<Integer> getWeeks() { return weeks; }

    public boolean conflictsWith(MeetingTime other) {
        if (this.dayOfWeek != other.dayOfWeek) return false;
        if (java.util.Collections.disjoint(this.weeks, other.weeks)) return false;
        return this.startSection <= other.endSection && other.startSection <= this.endSection;
    }
}

package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.MeetingTime;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class TimeParser {

    // 真实快照写「星期三」，演示种子写「周三」，两种都要认。日/天 都表示周日。
    private static final Pattern DAY = Pattern.compile("(?:星期|周)([一二三四五六日天])");
    private static final Pattern SECTION = Pattern.compile("第(\\d+)(?:-(\\d+))?节");
    private static final Pattern WEEK = Pattern.compile("\\{(.+?)\\}");

    private static final Map<String, Integer> DAY_MAP = Map.of(
        "一", 1, "二", 2, "三", 3, "四", 4, "五", 5, "六", 6, "日", 7, "天", 7
    );

    /** 周次块尾部的单双周标记，例如 {1-16周(单)}。docs/04：单双周不交不冲突，这个标记不能丢。 */
    private static final Pattern PARITY = Pattern.compile("[(（]([单双])[)）]\\s*$");

    public ParseOutcome parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return ParseOutcome.unknown("meetingTextRaw 为空");
        }
        String text = raw.trim().replaceAll("\\s+", "");

        Matcher dayMatcher = DAY.matcher(text);
        if (!dayMatcher.find()) return ParseOutcome.unknown("无法识别星期：" + raw);
        int day = DAY_MAP.get(dayMatcher.group(1));

        Matcher sectionMatcher = SECTION.matcher(text);
        if (!sectionMatcher.find()) return ParseOutcome.unknown("无法识别节次：" + raw);
        int start = Integer.parseInt(sectionMatcher.group(1));
        int end = sectionMatcher.group(2) == null
            ? start : Integer.parseInt(sectionMatcher.group(2));
        if (start > end) return ParseOutcome.unknown("节次起始大于结束：" + raw);

        Matcher weekMatcher = WEEK.matcher(text);
        if (!weekMatcher.find()) return ParseOutcome.unknown("无法识别周次：" + raw);

        Set<Integer> weeks;
        try {
            weeks = parseWeeks(weekMatcher.group(1));
        } catch (RuntimeException e) {
            return ParseOutcome.unknown("周次格式无法识别：" + weekMatcher.group(1));
        }
        if (weeks.isEmpty()) return ParseOutcome.unknown("周次为空：" + raw);

        return ParseOutcome.ok(List.of(new MeetingTime(day, start, end, weeks)));
    }
    private Set<Integer> parseWeeks(String block) {
        // 先摘掉尾部的单双周标记，再按逗号拆范围；最后按奇偶过滤。
        int parity = 0;  // 0=全要，1=只要单周，2=只要双周
        Matcher parityMatcher = PARITY.matcher(block);
        if (parityMatcher.find()) {
            parity = "单".equals(parityMatcher.group(1)) ? 1 : 2;
            block = block.substring(0, parityMatcher.start()).trim();
        }

        Set<Integer> weeks = new TreeSet<>();
        for (String part : block.split("[,，]")) {
            part = part.trim();
            // 兼容“第1-16周”“1-16周”“第1-16”等写法
            part = part.replaceAll("^第", "").replaceAll("周$", "").trim();
            if (part.matches("\\d+")) {
                weeks.add(Integer.parseInt(part));
            } else if (part.matches("\\d+-\\d+")) {
                String[] se = part.split("-");
                int s = Integer.parseInt(se[0]), e = Integer.parseInt(se[1]);
                if (s > e) throw new IllegalArgumentException("周次范围倒置");
                for (int w = s; w <= e; w++) weeks.add(w);
            } else {
                throw new IllegalArgumentException("未知周次片段：" + part);
            }
        }
        if (parity == 1) weeks.removeIf(w -> w % 2 == 0);
        if (parity == 2) weeks.removeIf(w -> w % 2 == 1);
        return weeks;
    }

    public static class ParseOutcome {
        private final boolean ok;
        private final List<MeetingTime> meetings;
        private final String reason;

        private ParseOutcome(boolean ok, List<MeetingTime> meetings, String reason) {
            this.ok = ok; this.meetings = meetings; this.reason = reason;
        }
        public static ParseOutcome ok(List<MeetingTime> m) { return new ParseOutcome(true, m, null); }
        public static ParseOutcome unknown(String r) { return new ParseOutcome(false, List.of(), r); }

        public boolean isOk() { return ok; }
        public List<MeetingTime> getMeetings() { return meetings; }
        public String getReason() { return reason; }
    }
}

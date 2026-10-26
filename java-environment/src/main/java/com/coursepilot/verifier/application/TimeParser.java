package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.MeetingTime;
import com.fasterxml.jackson.annotation.JsonIgnore;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class TimeParser {

    /**
     * 契约上限，只在这里定义一次（contracts/schemas/domain.schema.json）：
     * Meeting.sectionStart / sectionEnd 为 1..64，Meeting.weeks 的元素为 1..60 且最多 60 个，
     * CourseOffering.meetings 最多 40 段。dayOfWeek 的 1..7 由正则 BLOCK 保证。
     * CatalogAssembler 与 ConflictChecker 都读本类的结论，不得各自再写一份上限。
     */
    public static final int MAX_SECTION = 64;
    public static final int MAX_WEEK = 60;
    public static final int MAX_MEETINGS = 40;

    /**
     * 一个完整的排课段：星期 + 节次 + 周次块。
     *
     * 用一个整体正则逐段匹配，而不是分别 find 星期/节次/周次。原先的写法
     * 对每种各取第一个匹配，遇到「星期一第1-2节{1-16周},星期三第3-4节{1-16周}」
     * 这类一周上两次的课，只会解析出周一那段，周三被静默丢掉还报 ok——
     * 后面的冲突检查就会把实际撞课的两门课判成不冲突。docs/09 要求
     * 「删 HTML 后分段解析」，meetings[] 本来就是复数。
     *
     * 真实快照写「星期三」，演示种子写「周三」，两种都要认。日/天 都表示周日。
     */
    private static final Pattern BLOCK = Pattern.compile(
        "(?:星期|周)([一二三四五六日天])第(\\d+)(?:-(\\d+))?节\\{([^{}]*)\\}");

    private static final Map<String, Integer> DAY_MAP = Map.of(
        "一", 1, "二", 2, "三", 3, "四", 4, "五", 5, "六", 6, "日", 7, "天", 7
    );

    /** 周次块尾部的单双周标记，例如 {1-16周(单)}。docs/04：单双周不交不冲突，这个标记不能丢。 */
    private static final Pattern PARITY = Pattern.compile("[(（]([单双])[)）]\\s*$");

    /** 段与段之间允许出现的分隔符。除此之外的残余文本一律按未知处理。 */
    private static final Pattern SEPARATORS = Pattern.compile("[,，;；、/|]+");

    public ParseOutcome parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return ParseOutcome.unknown("meetingTextRaw 为空");
        }
        String text = raw.trim().replaceAll("\\s+", "");

        List<MeetingTime> meetings = new ArrayList<>();
        StringBuilder residue = new StringBuilder();
        Matcher matcher = BLOCK.matcher(text);
        int cursor = 0;

        while (matcher.find()) {
            residue.append(text, cursor, matcher.start());
            cursor = matcher.end();

            int day = DAY_MAP.get(matcher.group(1));
            int start;
            int end;
            try {
                start = Integer.parseInt(matcher.group(2));
                end = matcher.group(3) == null ? start : Integer.parseInt(matcher.group(3));
            } catch (NumberFormatException e) {
                // 正则只保证是数字串，不保证能放进 int。这段文本来自调用方，不能让它逃成 500。
                return ParseOutcome.unknown("节次数字过大无法识别：" + raw);
            }
            if (start > end) {
                return ParseOutcome.unknown("节次起始大于结束：" + raw);
            }
            if (start < 1 || end > MAX_SECTION) {
                return ParseOutcome.outOfContract("节次超出契约上限 1-" + MAX_SECTION + "：" + raw);
            }
            if (meetings.size() >= MAX_MEETINGS) {
                return ParseOutcome.outOfContract("段数超出契约上限 " + MAX_MEETINGS + "：" + raw);
            }

            Set<Integer> weeks;
            try {
                weeks = parseWeeks(matcher.group(4));
            } catch (OutOfContractException e) {
                return ParseOutcome.outOfContract(e.getMessage() + "：" + raw);
            } catch (RuntimeException e) {
                return ParseOutcome.unknown("周次格式无法识别：" + matcher.group(4));
            }
            // 单双周过滤后可能为空（例如 {2-2周(单)}）。这时不能说「这段没课」。
            if (weeks.isEmpty()) {
                return ParseOutcome.unknown("周次为空：" + raw);
            }

            meetings.add(new MeetingTime(day, start, end, weeks));
        }
        residue.append(text.substring(cursor));

        if (meetings.isEmpty()) {
            return ParseOutcome.unknown("无法识别排课写法：" + raw);
        }
        // 认出了一部分但还剩看不懂的文本时，按未知处理而不是返回残缺的课表。
        // 少一段时间会让冲突检查漏判，比直接说未知危险得多（docs/09：
        // 解析失败不得被当「无冲突」）。
        String rest = SEPARATORS.matcher(residue.toString()).replaceAll("");
        if (!rest.isEmpty()) {
            return ParseOutcome.unknown("有无法识别的片段「" + rest + "」：" + raw);
        }

        return ParseOutcome.ok(List.copyOf(meetings));
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
                int w = Integer.parseInt(part);
                if (w < 1 || w > MAX_WEEK) throw new OutOfContractException("周次超出契约上限 1-" + MAX_WEEK);
                weeks.add(w);
            } else if (part.matches("\\d+-\\d+")) {
                String[] se = part.split("-");
                int s = Integer.parseInt(se[0]), e = Integer.parseInt(se[1]);
                if (s > e) throw new IllegalArgumentException("周次范围倒置");
                // 先判上限再展开：{1-999999999周} 不能在请求线程里造出十亿个元素。
                if (s < 1 || e > MAX_WEEK) throw new OutOfContractException("周次超出契约上限 1-" + MAX_WEEK);
                for (int w = s; w <= e; w++) weeks.add(w);
            } else {
                throw new IllegalArgumentException("未知周次片段：" + part);
            }
        }
        if (parity == 1) weeks.removeIf(w -> w % 2 == 0);
        if (parity == 2) weeks.removeIf(w -> w % 2 == 1);
        return weeks;
    }

    /** 周次解析内部用：格式正确但数值超出契约上限。 */
    private static final class OutOfContractException extends RuntimeException {
        OutOfContractException(String message) { super(message); }
    }

    public static class ParseOutcome {
        /** OK：解析成功；UNKNOWN：看不懂或缺信息；OUT_OF_CONTRACT：能读出但超出契约上限。 */
        public enum Kind { OK, UNKNOWN, OUT_OF_CONTRACT }

        private final Kind kind;
        private final List<MeetingTime> meetings;
        private final String reason;

        private ParseOutcome(Kind kind, List<MeetingTime> meetings, String reason) {
            this.kind = kind; this.meetings = meetings; this.reason = reason;
        }
        public static ParseOutcome ok(List<MeetingTime> m) { return new ParseOutcome(Kind.OK, m, null); }
        public static ParseOutcome unknown(String r) { return new ParseOutcome(Kind.UNKNOWN, List.of(), r); }
        /** 时间能读出，但超出契约上限。meetings 恒为空，调用方不得据此判冲突。 */
        public static ParseOutcome outOfContract(String r) {
            return new ParseOutcome(Kind.OUT_OF_CONTRACT, List.of(), r);
        }

        public boolean isOk() { return kind == Kind.OK; }
        @JsonIgnore public boolean isOutOfContract() { return kind == Kind.OUT_OF_CONTRACT; }
        @JsonIgnore public Kind getKind() { return kind; }
        public List<MeetingTime> getMeetings() { return meetings; }
        public String getReason() { return reason; }
    }
}

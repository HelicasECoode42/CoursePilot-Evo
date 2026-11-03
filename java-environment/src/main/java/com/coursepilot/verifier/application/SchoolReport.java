package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.web.dto.SchoolProgressDtos;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * 学校学业进度（导入的学校报告）的只读视图。
 *
 * 学校类别与培养要求没有共享 ID，只能按名称对齐（docs/27）：
 *   - 类别按名称精确匹配。同名节点若有唯一顶层节点，取顶层；否则只有唯一一个节点时才取；
 *     其余同名情况视为有歧义，不做映射（不静默编造对应关系）。
 *   - 课程到类别：课程挂在哪个学校节点，就归到该节点的名称下；同一课程出现在不同名称节点时视为歧义。
 *   - 读全（fullyRead）：每个节点的 required/earned/remaining 都已读到，且没有 outcome=UNKNOWN 的课程。
 *     满足时学业记录可以按「学校导入读全」视为完整。
 */
final class SchoolReport {

    /** 学校报告里的一个类别，三个学分都已读到。 */
    record Category(String name, double required, double earned, double remaining) {}

    static final SchoolReport NONE = new SchoolReport(Map.of(), Map.of(), Map.of(), Set.of(), false);

    private final Map<String, Category> categories;
    private final Map<String, String> categoryOfCourse;
    private final Map<String, Double> creditsOfCourse;
    private final Set<String> ambiguousCourses;
    private final boolean fullyRead;

    private SchoolReport(Map<String, Category> categories,
                         Map<String, String> categoryOfCourse, Map<String, Double> creditsOfCourse,
                         Set<String> ambiguousCourses, boolean fullyRead) {
        this.categories = categories;
        this.categoryOfCourse = categoryOfCourse;
        this.creditsOfCourse = creditsOfCourse;
        this.ambiguousCourses = ambiguousCourses;
        this.fullyRead = fullyRead;
    }

    static SchoolReport from(SchoolProgressDtos.Snapshot snapshot) {
        if (snapshot == null || snapshot.nodes() == null || snapshot.courses() == null) {
            return NONE;
        }
        List<SchoolProgressDtos.Node> nodes = snapshot.nodes();
        Map<String, SchoolProgressDtos.Node> byId = new HashMap<>();
        Map<String, List<SchoolProgressDtos.Node>> byName = new HashMap<>();
        for (SchoolProgressDtos.Node n : nodes) {
            byId.put(n.nodeId(), n);
            byName.computeIfAbsent(n.name(), k -> new java.util.ArrayList<>()).add(n);
        }

        Map<String, Category> categories = new HashMap<>();
        for (Map.Entry<String, List<SchoolProgressDtos.Node>> e : byName.entrySet()) {
            List<SchoolProgressDtos.Node> group = e.getValue();
            List<SchoolProgressDtos.Node> tops = group.stream().filter(n -> n.parentId() == null).toList();
            SchoolProgressDtos.Node pick = tops.size() == 1 ? tops.get(0)
                : tops.isEmpty() && group.size() == 1 ? group.get(0) : null;
            if (pick == null || pick.requiredCredits() == null || pick.remainingCredits() == null) {
                continue;
            }
            double required = pick.requiredCredits().doubleValue();
            double remaining = pick.remainingCredits().doubleValue();
            double earned = pick.earnedCredits() != null
                ? pick.earnedCredits().doubleValue() : required - remaining;
            categories.put(e.getKey(), new Category(e.getKey(), required, earned, remaining));
        }

        Map<String, Set<String>> namesByCode = new HashMap<>();
        Map<String, Double> credits = new HashMap<>();
        boolean anyUnknownOutcome = false;
        for (SchoolProgressDtos.Course c : snapshot.courses()) {
            if ("UNKNOWN".equals(c.outcome())) anyUnknownOutcome = true;
            SchoolProgressDtos.Node node = byId.get(c.nodeId());
            if (node != null) {
                namesByCode.computeIfAbsent(c.courseCode(), k -> new HashSet<>()).add(node.name());
            }
            if (c.credits() != null) {
                credits.putIfAbsent(c.courseCode(), c.credits().doubleValue());
            }
        }
        Map<String, String> categoryOfCourse = new HashMap<>();
        Set<String> ambiguous = new HashSet<>();
        for (Map.Entry<String, Set<String>> e : namesByCode.entrySet()) {
            if (e.getValue().size() == 1) {
                categoryOfCourse.put(e.getKey(), e.getValue().iterator().next());
            } else {
                ambiguous.add(e.getKey());
            }
        }

        boolean allCategoriesRead = nodes.stream().allMatch(n ->
            n.requiredCredits() != null && n.earnedCredits() != null && n.remainingCredits() != null);
        boolean fullyRead = !nodes.isEmpty() && allCategoriesRead && !anyUnknownOutcome;
        return new SchoolReport(categories, categoryOfCourse, credits, ambiguous, fullyRead);
    }

    /** 学校报告里与该名称精确匹配、且学分已读全的类别。 */
    Optional<Category> category(String name) {
        return Optional.ofNullable(name == null ? null : categories.get(name));
    }

    /** 课程挂在的学校类别名称；没有链接或有歧义时为 null。 */
    String categoryOfCourse(String courseCode) {
        return ambiguousCourses.contains(courseCode) ? null : categoryOfCourse.get(courseCode);
    }

    /** 学校报告里该课程的学分（在读课的学分只能从这里得到）；没有则为 null。 */
    Double creditsOfCourse(String courseCode) {
        return creditsOfCourse.get(courseCode);
    }

    boolean fullyRead() { return fullyRead; }

    /**
     * 学业记录是否完整：手动声明完整，或学校导入读全。
     * 学校导入读全时以学校报告为准，即使记录上的手动标记为 false。
     */
    boolean completes(Transcript transcript) {
        return transcript != null && (transcript.isTranscriptComplete() || fullyRead);
    }
}

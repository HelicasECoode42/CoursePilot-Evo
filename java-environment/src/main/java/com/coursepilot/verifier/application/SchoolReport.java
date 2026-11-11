package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.web.dto.SchoolProgressDtos;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.math.BigDecimal;

/**
 * 学校学业进度（导入的学校报告）的只读视图。
 *
 * 学校类别与培养要求没有共享 ID，只能按名称对齐（docs/27）：
 *   - 类别按名称精确匹配。同名节点取树中最浅的一层（节点深度 = 祖先个数）；
 *     最浅层唯一时采用它，最浅层有多个同名节点才视为歧义，不做映射（不静默编造对应关系）。
 *     例：「公共基础课」一级类别在「主修」下，子节点也叫「公共基础课」，取一级类别。
 *   - 课程到类别：从课程挂的学校节点起沿祖先链向上，取最近的、与培养类别同名的祖先。
 *     例：通选课 -> 通识课；体育1 -> 公共基础课。解析结果唯一才采用；多个不同类别时视为歧义。
 *   - 读全（fullyRead）：每个「显示了学分数字」的节点都三项学分齐全；
 *     没有任何学分数字的纯分组节点（如「主修」「其他课程」）不计入；且没有 outcome=UNKNOWN 的课程。
 *     满足时学业记录可以按「学校导入读全」视为完整。
 */
final class SchoolReport {

    /** 学校报告里的一个类别，三个学分都已读到。 */
    record Category(String name, BigDecimal required, BigDecimal earned, BigDecimal remaining) {}

    static final SchoolReport NONE = new SchoolReport(Map.of(), Map.of(), Map.of(), false);

    private final Map<String, Category> categories;
    /** 课程编号 -> 每个出现位置的祖先名称链（从最近到最远，含自身节点）。 */
    private final Map<String, List<List<String>>> chainsOfCourse;
    private final Map<String, BigDecimal> creditsOfCourse;
    private final boolean fullyRead;

    private SchoolReport(Map<String, Category> categories,
                         Map<String, List<List<String>>> chainsOfCourse,
                         Map<String, BigDecimal> creditsOfCourse, boolean fullyRead) {
        this.categories = categories;
        this.chainsOfCourse = chainsOfCourse;
        this.creditsOfCourse = creditsOfCourse;
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
            byName.computeIfAbsent(n.name(), k -> new ArrayList<>()).add(n);
        }

        Map<String, Category> categories = new HashMap<>();
        for (Map.Entry<String, List<SchoolProgressDtos.Node>> e : byName.entrySet()) {
            List<SchoolProgressDtos.Node> group = e.getValue();
            int shallowest = group.stream().mapToInt(n -> depthOf(n, byId)).min().orElse(0);
            List<SchoolProgressDtos.Node> tops = group.stream()
                .filter(n -> depthOf(n, byId) == shallowest).toList();
            if (tops.size() != 1) {
                continue;
            }
            SchoolProgressDtos.Node pick = tops.get(0);
            if (pick.requiredCredits() == null || pick.earnedCredits() == null || pick.remainingCredits() == null) {
                continue;
            }
            BigDecimal required = pick.requiredCredits();
            BigDecimal remaining = pick.remainingCredits();
            BigDecimal earned = pick.earnedCredits();
            categories.put(e.getKey(), new Category(e.getKey(), required, earned, remaining));
        }

        Map<String, List<List<String>>> chains = new HashMap<>();
        Map<String, BigDecimal> credits = new HashMap<>();
        boolean anyUnknownOutcome = false;
        for (SchoolProgressDtos.Course c : snapshot.courses()) {
            if ("UNKNOWN".equals(c.outcome())) anyUnknownOutcome = true;
            SchoolProgressDtos.Node node = byId.get(c.nodeId());
            if (node != null) {
                chains.computeIfAbsent(c.courseCode(), k -> new ArrayList<>()).add(chainOf(node, byId));
            }
            if (c.credits() != null) {
                credits.putIfAbsent(c.courseCode(), c.credits());
            }
        }

        // 只有显示了学分数字的节点才需要三项齐全；纯分组节点（三项都为空）不参与判断。
        boolean allShownNodesRead = nodes.stream().allMatch(n ->
            !showsNumbers(n) || (n.requiredCredits() != null && n.earnedCredits() != null
                && n.remainingCredits() != null));
        boolean fullyRead = !nodes.isEmpty() && allShownNodesRead && !anyUnknownOutcome;
        return new SchoolReport(categories, chains, credits, fullyRead);
    }

    private static boolean showsNumbers(SchoolProgressDtos.Node n) {
        return n.requiredCredits() != null || n.earnedCredits() != null || n.remainingCredits() != null;
    }

    /** 节点深度：祖先个数；父链出现环或父节点缺失时在该处截止。 */
    private static int depthOf(SchoolProgressDtos.Node node, Map<String, SchoolProgressDtos.Node> byId) {
        return chainOf(node, byId).size() - 1;
    }

    /** 从节点起沿父链向上的名称列表（含自身）；遇到环或缺失的父节点即停止。 */
    private static List<String> chainOf(SchoolProgressDtos.Node node,
                                        Map<String, SchoolProgressDtos.Node> byId) {
        List<String> names = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        SchoolProgressDtos.Node cur = node;
        while (cur != null && seen.add(cur.nodeId())) {
            names.add(cur.name());
            cur = cur.parentId() == null ? null : byId.get(cur.parentId());
        }
        return names;
    }

    /** 学校报告里与该名称精确匹配、且学分已读全的类别。 */
    Optional<Category> category(String name) {
        return Optional.ofNullable(name == null ? null : categories.get(name));
    }

    /**
     * 课程归属的培养类别：沿每个出现位置的祖先链取最近的、属于 curriculumCategories 的名称。
     * 所有出现位置解析出的类别唯一时采用；没有解析结果或出现多个不同类别时为 null。
     */
    String categoryOfCourse(String courseCode, Set<String> curriculumCategories) {
        List<List<String>> chains = chainsOfCourse.get(courseCode);
        if (chains == null || curriculumCategories == null || curriculumCategories.isEmpty()) {
            return null;
        }
        Set<String> resolved = new HashSet<>();
        for (List<String> chain : chains) {
            chain.stream().filter(curriculumCategories::contains).findFirst().ifPresent(resolved::add);
        }
        return resolved.size() == 1 ? resolved.iterator().next() : null;
    }

    /** 学校报告里该课程的学分（在读课的学分只能从这里得到）；没有则为 null。 */
    BigDecimal creditsOfCourse(String courseCode) {
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

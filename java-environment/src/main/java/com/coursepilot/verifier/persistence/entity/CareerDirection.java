package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.util.ArrayList;
import java.util.List;

/**
 * 职业方向介绍（contracts: CareerDirection 的存储形态）。
 *
 * 方向和课程号的关联放在 courseCodes：表示「这个方向需要学哪些课」。
 * 契约 CareerDirection 没有 sourceKind 字段，来源只能靠 sourceRefIds 指向来源记录。
 * 所以演示数据的真实性标记放在 sourceRefIds 的前缀（synthetic:）和 title/description 的【演示数据】标记里。
 *
 * 没有真实职业方向资料时，不在这里编造来源；真实来源到位前，这张表只放演示种子。
 * 三组集合都是 EAGER 加载：open-in-view 关闭，映射到 DTO 时不能再触发懒加载。
 */
@Entity
@Table(name = "career_direction")
public class CareerDirection {

    @Id
    @Column(length = 120)
    private String directionId;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false, length = 1500)
    private String description;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "career_direction_subject_tag",
        joinColumns = @JoinColumn(name = "direction_id"))
    @Column(name = "subject_tag", nullable = false, length = 80)
    private List<String> subjectTags = new ArrayList<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "career_direction_course",
        joinColumns = @JoinColumn(name = "direction_id"))
    @Column(name = "course_code", nullable = false, length = 120)
    private List<String> courseCodes = new ArrayList<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "career_direction_source_ref",
        joinColumns = @JoinColumn(name = "direction_id"))
    @Column(name = "source_ref_id", nullable = false, length = 120)
    private List<String> sourceRefIds = new ArrayList<>();

    public CareerDirection() {}

    public CareerDirection(String directionId, String title, String description,
                           List<String> subjectTags, List<String> courseCodes,
                           List<String> sourceRefIds) {
        this.directionId = directionId;
        this.title = title;
        this.description = description;
        this.subjectTags = new ArrayList<>(subjectTags);
        this.courseCodes = new ArrayList<>(courseCodes);
        this.sourceRefIds = new ArrayList<>(sourceRefIds);
    }

    public String getDirectionId() { return directionId; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public List<String> getSubjectTags() { return subjectTags; }
    public List<String> getCourseCodes() { return courseCodes; }
    public List<String> getSourceRefIds() { return sourceRefIds; }
}

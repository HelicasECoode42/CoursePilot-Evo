package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "requirement")
public class Requirement {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String planId;

    @Column(nullable = false, length = 32)
    private String category;

    @Column(nullable = false)
    private double requiredCredits;

    /** Null only on the legacy seed rows created before import provenance was modeled. */
    @ManyToOne(fetch = FetchType.LAZY, cascade = CascadeType.PERSIST)
    @JoinColumn(name = "source_ref_id")
    private SourceReference sourceReference;

    public Requirement() {}
    public Requirement(String planId, String category, double requiredCredits) {
        this.planId = planId;
        this.category = category;
        this.requiredCredits = requiredCredits;
    }

    public Requirement(String planId, String category, double requiredCredits,
                       SourceReference sourceReference) {
        this(planId, category, requiredCredits);
        this.sourceReference = sourceReference;
    }

    public Long getId() { return id; }
    public String getPlanId() { return planId; }
    public void setPlanId(String planId) { this.planId = planId; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public double getRequiredCredits() { return requiredCredits; }
    public SourceReference getSourceReference() { return sourceReference; }
    public void setRequiredCredits(double requiredCredits) { this.requiredCredits = requiredCredits; }
}

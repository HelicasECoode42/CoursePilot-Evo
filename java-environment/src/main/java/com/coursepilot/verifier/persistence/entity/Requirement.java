package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.math.BigDecimal;

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
    private BigDecimal requiredCredits;

    public Requirement() {}
    public Requirement(String planId, String category, BigDecimal requiredCredits) {
        this.planId = planId;
        this.category = category;
        this.requiredCredits = requiredCredits;
    }

    public Long getId() { return id; }
    public String getPlanId() { return planId; }
    public void setPlanId(String planId) { this.planId = planId; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public BigDecimal getRequiredCredits() { return requiredCredits; }
    public void setRequiredCredits(BigDecimal requiredCredits) { this.requiredCredits = requiredCredits; }
}

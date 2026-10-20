package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "course")
public class Course {
    @Id
    @Column(length = 32)
    private String courseCode;

    @Column(nullable = false, length = 128)
    private String name;

    private Double credits;          // 允许 null，表示学分未知

    @Column(length = 32)
    private String category;

    public Course() {}
    public Course(String courseCode, String name, Double credits, String category) {
        this.courseCode = courseCode;
        this.name = name;
        this.credits = credits;
        this.category = category;
    }

    public String getCourseCode() { return courseCode; }
    public void setCourseCode(String courseCode) { this.courseCode = courseCode; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Double getCredits() { return credits; }
    public void setCredits(Double credits) { this.credits = credits; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
}

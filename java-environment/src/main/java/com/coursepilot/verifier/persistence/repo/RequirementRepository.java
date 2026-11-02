package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.Requirement;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface RequirementRepository extends JpaRepository<Requirement, Long> {
    @EntityGraph(attributePaths = "sourceReference")
    List<Requirement> findByPlanId(String planId);
}

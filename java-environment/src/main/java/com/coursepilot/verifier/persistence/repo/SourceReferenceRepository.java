package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.SourceReference;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SourceReferenceRepository extends JpaRepository<SourceReference, String> {}

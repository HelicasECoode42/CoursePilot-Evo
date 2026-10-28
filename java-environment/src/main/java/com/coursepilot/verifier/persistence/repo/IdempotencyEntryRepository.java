package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.IdempotencyEntry;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface IdempotencyEntryRepository extends JpaRepository<IdempotencyEntry, Long> {
    Optional<IdempotencyEntry> findByStudentIdAndIdemKey(String studentId, String idemKey);
}

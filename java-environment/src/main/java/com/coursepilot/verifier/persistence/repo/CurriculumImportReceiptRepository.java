package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CurriculumImportReceipt;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface CurriculumImportReceiptRepository
    extends JpaRepository<CurriculumImportReceipt, String> {
    Optional<CurriculumImportReceipt> findBySnapshotId(String snapshotId);
}

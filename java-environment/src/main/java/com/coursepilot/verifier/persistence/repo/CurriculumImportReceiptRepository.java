package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CurriculumImportReceipt;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CurriculumImportReceiptRepository
    extends JpaRepository<CurriculumImportReceipt, String> {}

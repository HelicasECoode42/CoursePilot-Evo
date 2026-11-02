package com.coursepilot.verifier.persistence.repo;

import com.coursepilot.verifier.persistence.entity.CareerDirection;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CareerDirectionRepository extends JpaRepository<CareerDirection, String> {

    List<CareerDirection> findAllByOrderByDirectionIdAsc();
}

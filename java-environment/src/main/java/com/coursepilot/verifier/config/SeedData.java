package com.coursepilot.verifier.config;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner init(CourseRepository courseRepo,
                           RequirementRepository reqRepo,
                           AcademicRecordRepository recordRepo,
                           CourseOfferingRepository offeringRepo) {
        return args -> {
            if (courseRepo.count() > 0) return;

            courseRepo.save(new Course("CS101", "Java 程序设计", new BigDecimal("3.0"), "必修"));
            courseRepo.save(new Course("CS102", "数据结构", new BigDecimal("4.0"), "必修"));
            courseRepo.save(new Course("GE101", "通识写作", new BigDecimal("2.0"), "通识"));
            courseRepo.save(new Course("CS103", "操作系统", null, "必修")); // 学分未知

            reqRepo.save(new Requirement("PLAN_CS_2025", "必修", new BigDecimal("10.0")));
            reqRepo.save(new Requirement("PLAN_CS_2025", "通识", new BigDecimal("4.0")));

            recordRepo.save(new AcademicRecord("S001", "CS101", true, new BigDecimal("3.0"), 1));
            recordRepo.save(new AcademicRecord("S001", "CS101", true, new BigDecimal("3.0"), 2)); // 重修，应去重
            recordRepo.save(new AcademicRecord("S001", "CS102", true, new BigDecimal("4.0"), 1));
            recordRepo.save(new AcademicRecord("S001", "GE101", true, new BigDecimal("2.0"), 1));

            offeringRepo.save(new CourseOffering("O_CS101_01", "CS101", "张老师",
                "周一第1-2节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS102_01", "CS102", "李老师",
                "周一第2-3节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS103_01", "CS103", "王老师",
                "时间待定", "SYNTHETIC")); // 时间未知
        };
    }
}

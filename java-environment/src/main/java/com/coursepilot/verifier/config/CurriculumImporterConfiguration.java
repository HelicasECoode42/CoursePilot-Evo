package com.coursepilot.verifier.config;

import edu.coursepilot.importer.A1WorkbookImporter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CurriculumImporterConfiguration {
    @Bean
    A1WorkbookImporter a1WorkbookImporter() {
        return new A1WorkbookImporter();
    }
}

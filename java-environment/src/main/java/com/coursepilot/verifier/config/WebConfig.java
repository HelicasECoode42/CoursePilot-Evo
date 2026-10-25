package com.coursepilot.verifier.config;

import com.coursepilot.verifier.web.ApiSecurityInterceptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Autowired
    private ApiSecurityInterceptor apiSecurityInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // 拦截 /api/v1 下的所有请求
        registry.addInterceptor(apiSecurityInterceptor)
            .addPathPatterns("/api/v1/**");
    }
}

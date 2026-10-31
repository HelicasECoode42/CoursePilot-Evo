package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CurriculumUnmodeledRule;

import java.util.List;

/**
 * 未建模规则的 unknown 文案。学业核对与方案核验共用，保证两边说的是同一件事。
 *
 * 规则不是被放过了：每次核验都会带出一条 unknown，说明有几条规则未参与核验，并列出原表位置，
 * 让人能追到是哪几条。计数始终是精确的，只有列出的位置会在长度上限处截断（末尾注明「等」）。
 */
final class UnmodeledRuleNotice {

    static final String CODE = "UNMODELED_CURRICULUM_RULES";

    /** 位置列表的长度上限，给整条文案留出余量（契约 message 上限 500）。 */
    private static final int MAX_LOCATOR_CHARS = 380;

    private UnmodeledRuleNotice() {}

    static String message(List<CurriculumUnmodeledRule> rules) {
        StringBuilder locators = new StringBuilder();
        for (CurriculumUnmodeledRule rule : rules) {
            String locator = rule.getSourceLocator() != null && !rule.getSourceLocator().isBlank()
                ? rule.getSourceLocator()
                : rule.getSheet() + " 第" + rule.getSourceRow() + "行";
            if (locators.length() > 0) locators.append("、");
            if (locators.length() + locator.length() > MAX_LOCATOR_CHARS) {
                locators.append("等");
                break;
            }
            locators.append(locator);
        }
        return "本培养方案有 " + rules.size() + " 条规则系统未建模、不参与核验（原表位置："
            + locators + "）";
    }
}

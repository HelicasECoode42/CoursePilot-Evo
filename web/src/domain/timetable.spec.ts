import { describe, expect, it } from "vitest";
import type { Meeting } from "../contracts";
import { meetingsText } from "./timetable";

const WEEKS = Array.from({ length: 16 }, (_, index) => index + 1);

describe("meetingsText", () => {
  it("writes a meeting as weekday, section range and week range", () => {
    const meeting: Meeting = {
      dayOfWeek: 1,
      sectionStart: 1,
      sectionEnd: 2,
      weeks: WEEKS,
    };
    expect(meetingsText([meeting])).toBe("周一 第1-2节 · 第1–16周");
  });

  it("uses a single section label when start and end are the same", () => {
    const meeting: Meeting = {
      dayOfWeek: 3,
      sectionStart: 5,
      sectionEnd: 5,
      weeks: [2, 4],
    };
    expect(meetingsText([meeting])).toBe("周三 第5节 · 第2、4周");
  });

  it("says the time is unconfirmed when there is nothing readable", () => {
    expect(meetingsText([])).toBe("上课时间未能确认");
    expect(
      meetingsText([
        { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: [] },
      ]),
    ).toBe("上课时间未能确认");
  });

  it("never hides an unreadable meeting behind the readable ones", () => {
    const text = meetingsText([
      { dayOfWeek: 1, sectionStart: 1, sectionEnd: 2, weeks: WEEKS },
      { dayOfWeek: 2, sectionStart: 1, sectionEnd: 2, weeks: [] },
    ]);
    expect(text).toBe("周一 第1-2节 · 第1–16周；另有一段时间无法确认");
  });
});

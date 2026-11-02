import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("browser school progress extractor", () => {
  it("maps icon signatures only through the page legend and retains the source tree", () => {
    document.body.innerHTML = `
      <div class="legend"><i class="glyphicon glyphicon-ok"></i>已修</div>
      <div class="legend"><i class="glyphicon glyphicon-time"></i>在修</div>
      <div class="legend"><i class="glyphicon glyphicon-minus"></i>未修</div>
      <div class="legend"><i class="glyphicon glyphicon-remove"></i>未过</div>
      <ul class="treeview">
        <li xfyqjd_id="98" leaf="false">
          <div class="title"><p class="title1">公共基础课要求学分：12获得学分：6未获得学分：6</p></div>
          <ul><li xfyqjd_id="54" leaf="true">
            <div class="title"><p class="title1">公共基础课要求学分：4获得学分：2未获得学分：2</p></div>
            <table><thead><tr>${["修读状态", "成绩学年", "学期", "课程号", "课程名称", "学分", "最大成绩", "绩点", "成绩", "补考", "重修", "建议修读学年", "建议修读学期"].map((name) => `<th>${name}</th>`).join("")}</tr></thead>
              <tbody>
                ${[
                  ["glyphicon-ok", "PASSED"],
                  ["glyphicon-time", "IN_PROGRESS"],
                  ["glyphicon-minus", "NOT_TAKEN"],
                  ["glyphicon-remove", "FAILED"],
                  ["glyphicon-question-sign", "UNKNOWN"],
                ]
                  .map(
                    ([icon], index) =>
                      `<tr><td><i class="glyphicon ${icon}"></i></td><td></td><td></td><td>CP00${index + 1}</td><td>虚构课程${index + 1}</td><td>2</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>`,
                  )
                  .join("")}
              </tbody></table>
          </li></ul>
        </li>
      </ul>`;
    const source = readFileSync(
      resolve(process.cwd(), "../browser-adapter/academic-progress/extract.js"),
      "utf8",
    );
    window.eval(source);
    const result = (
      window as unknown as {
        coursepilotReadAcademicProgress: () => {
          nodes: Array<{
            nodeId: string;
            parentId: string | null;
            schoolNodeId: string | null;
            name: string;
          }>;
          courses: Array<{ outcome: string }>;
        };
      }
    ).coursepilotReadAcademicProgress();

    expect(result.nodes).toHaveLength(2);
    expect(
      result.nodes.map((node) => [node.schoolNodeId, node.parentId, node.name]),
    ).toEqual([
      ["98", null, "公共基础课"],
      ["54", expect.any(String), "公共基础课"],
    ]);
    expect(result.courses.map((course) => course.outcome)).toEqual([
      "PASSED",
      "IN_PROGRESS",
      "NOT_TAKEN",
      "FAILED",
      "UNKNOWN",
    ]);
  });
});

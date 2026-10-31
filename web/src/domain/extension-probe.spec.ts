import { describe, expect, it } from "vitest";
import {
  REQUIRED_EXTENSION_PORT,
  describeExtensionPresent,
  describePortMismatch,
  isExtensionReply,
} from "./extension-probe";

describe("插件探测规则", () => {
  it("端口正确时不报错", () => {
    expect(describePortMismatch(REQUIRED_EXTENSION_PORT)).toBeNull();
  });

  it("端口不对时说出当前端口和该去哪个端口", () => {
    const message = describePortMismatch("5175");
    expect(message).toContain("5173");
    expect(message).toContain("5175");
  });

  it("端口为空串也当成不匹配，并且不渲染成空白", () => {
    expect(describePortMismatch("")).toContain("（空）");
  });

  it("只按 type 判断插件在场，ok 为假也算在场", () => {
    expect(isExtensionReply({ type: "CP_IMPORT_READY", ok: true })).toBe(true);
    expect(isExtensionReply({ type: "CP_IMPORT_READY", ok: false })).toBe(true);
  });

  it("别的消息不算插件回话", () => {
    expect(isExtensionReply({ type: "CP_DELIVER_PROGRESS" })).toBe(false);
    expect(isExtensionReply(null)).toBe(false);
    expect(isExtensionReply("CP_IMPORT_READY")).toBe(false);
  });

  it("ok 为假时解释原因，不说成连接失败", () => {
    const note = describeExtensionPresent(false);
    expect(note).toContain("插件已连接");
    expect(note).toContain("已有一次导入正在进行");
    expect(note).not.toContain("失败");
  });
});

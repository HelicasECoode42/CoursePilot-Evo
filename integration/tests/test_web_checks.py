"""第 5 件事的自测：钉住浏览器检查的判定语义。

不连页面、不开浏览器：用假驱动与假 HTTP 注入观察结果，确认「页面没起算 BLOCKED」「缺浏览器算 BLOCKED」
「白屏/没重试入口必须 FAIL」这几条成立。
"""

from __future__ import annotations

from check_web import blocked_rows
from stack_checks import BLOCKED, FAIL, PASS, PLAN, exit_code
from web_checks import (
    HttpProbeDriver,
    LoadedPage,
    check_api_down,
    check_bundle,
    check_document,
    check_narrow,
    check_shell,
    check_unknown,
    plan_rows,
)

URL = "http://127.0.0.1:5173/"
DOC = (
    '<!doctype html><html lang="zh-CN"><head><title>CoursePilot · 学期规划</title></head>'
    '<body><div id="app"></div><script type="module" src="/src/main.ts"></script></body></html>'
)
SHELL_TEXT = "CoursePilot 真实服务模式 你可以返回修改条件。课程规划不会替你登录教务系统或提交选课。"


class FakeDriver:
    """假浏览器：按 URL 返回预先准备好的观察结果。"""

    name = "fake-browser"

    def __init__(self, pages: dict) -> None:
        self.pages = pages
        self.loads: list[tuple] = []

    def available(self) -> tuple[bool, str]:
        return True, "假浏览器（自测用）"

    def load(self, url: str, *, viewport=None, screenshot: str = "") -> LoadedPage:
        self.loads.append((url, viewport, screenshot))
        page = self.pages.get(url)
        return page if page is not None else LoadedPage(url, 0, page_errors=["假驱动没有这条路由"])


def test_document_blocked_when_page_service_is_down():
    result = check_document(FakeDriver({}), URL)
    assert result.verdict == BLOCKED
    assert exit_code([result]) == 1


def test_document_fails_when_mount_markers_missing():
    driver = FakeDriver({URL: LoadedPage(URL, 200, html="<html><body>nope</body></html>")})
    assert check_document(driver, URL).verdict == FAIL


def test_document_passes_when_markers_present():
    driver = FakeDriver({URL: LoadedPage(URL, 200, html=DOC)})
    assert check_document(driver, URL).verdict == PASS


def test_bundle_requires_create_app(monkeypatch):
    monkeypatch.setattr("web_checks.http_get", lambda url: (200, "createApp(App).mount('#app')"))
    assert check_bundle(URL).verdict == PASS
    monkeypatch.setattr("web_checks.http_get", lambda url: (200, "console.log('hi')"))
    assert check_bundle(URL).verdict == FAIL
    monkeypatch.setattr("web_checks.http_get", lambda url: (0, ""))
    assert check_bundle(URL).verdict == BLOCKED


def test_shell_is_blocked_without_a_real_browser():
    result = check_shell(HttpProbeDriver(), URL)
    assert result.verdict == BLOCKED
    assert "playwright" in result.detail


def test_shell_fails_on_page_error():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT, page_errors=["TypeError: x is undefined"])})
    result = check_shell(driver, URL)
    assert result.verdict == FAIL
    assert "未捕获异常" in result.actual


def test_shell_fails_on_blank_page():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text="")})
    assert check_shell(driver, URL).verdict == FAIL


def test_shell_passes_with_shell_and_badge():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT, screenshot="runs/stack/web/shell.png")})
    assert check_shell(driver, URL).verdict == PASS


def test_api_down_branch_is_blocked_while_python_is_up():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT)})
    result = check_api_down(driver, URL, api_reachable=True)
    assert result.verdict == BLOCKED
    assert "停掉 Python" in result.detail


def test_api_down_fails_on_blank_page():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text="短")})
    assert check_api_down(driver, URL, api_reachable=False).verdict == FAIL


def test_api_down_fails_without_retry_entry():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT)})
    assert check_api_down(driver, URL, api_reachable=False).verdict == FAIL


def test_api_down_passes_with_retry_hint():
    text = SHELL_TEXT + " 暂时无法连接服务，请确认服务已启动后重试。"
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=text)})
    assert check_api_down(driver, URL, api_reachable=False).verdict == PASS


def test_unknown_is_blocked_without_a_controlled_stub():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT)})
    result = check_unknown(driver, None)
    assert result.verdict == BLOCKED
    assert "受控假响应" in result.detail


def test_narrow_fails_on_horizontal_overflow():
    driver = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT, overflow_px=42)})
    assert check_narrow(driver, URL).verdict == FAIL
    inside = FakeDriver({URL: LoadedPage(URL, 200, text=SHELL_TEXT, overflow_px=0)})
    assert check_narrow(inside, URL).verdict == PASS


def test_plan_rows_are_green_and_blocked_rows_are_not():
    rows = plan_rows()
    assert [r.step for r in rows] == [r.step for r in blocked_rows("x", "y")]
    assert exit_code(rows) == 0
    assert all(r.verdict == PLAN for r in rows)
    assert exit_code(blocked_rows("web 未就绪", "python integration/start_stack.py --plan")) == 1

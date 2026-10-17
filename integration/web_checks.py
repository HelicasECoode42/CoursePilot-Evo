"""D2 浏览器检查判定层（第 5 件事的框架）：主路径、未知与服务失败三档。

观察点取自 E 的页面实现与 README，不是猜的：
  web/index.html                入口文档含 `<div id="app">` 与 `/src/main.ts`
  web/src/main.ts               createApp(App).use(router).mount("#app")
  web/src/App.vue               品牌 aria-label「CoursePilot 首页」、模式徽标「真实服务模式」/「演示模式 · 虚构内容」、footer 文案
  web/src/views/QuestionView.vue  服务失败时给出「重试」按钮；缺培养方案时给出明确说明文案
  web/README.md                 真实模式网络失败会显示错误与重试入口，不切换演示数据；无系统健康检查接口

两档驱动
  HttpProbeDriver    只用 HTTP：能判入口文档与入口脚本；需要执行 JS 的检查判 BLOCKED
  PlaywrightDriver   真浏览器（装了 playwright 才可用）：判挂载、失败提示、窄屏横向溢出，并留截图证据

判定沿用第 3、4 件的五个词；缺浏览器、缺受控假响应一律 BLOCKED，不跳过、不算过。
"""

from __future__ import annotations

import importlib.util
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from stack_checks import BLOCKED, FAIL, PASS, StepResult
from stack_config import ROOT

EVIDENCE_DIR = Path(ROOT) / "runs" / "stack" / "web"
MOUNT_MARKERS = ('id="app"', "/src/main.ts")
SHELL_TEXTS = ("CoursePilot", "真实服务模式", "演示模式 · 虚构内容")
FOOTER_TEXT = "不会替你登录教务系统"
RETRY_MARKERS = ("重试", "暂时无法", "请稍后重试")
NARROW_OVERFLOW_TOLERANCE = 2

PLAYWRIGHT_HINT = "python -m pip install playwright && python -m playwright install chromium"


@dataclass
class LoadedPage:
    """一次页面加载的观察结果；拿不到的项留空或 None，不假装拿到。"""

    url: str
    status: int
    html: str = ""
    text: str = ""
    scripts: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    overflow_px: int | None = None
    screenshot: str = ""

    @property
    def failure(self) -> str:
        return "；".join(self.page_errors)


class PageDriver(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...

    def load(self, url: str, *, viewport: tuple[int, int] | None = None, screenshot: str = "") -> LoadedPage: ...


def _text_of(html: str) -> str:
    stripped = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", stripped)).strip()


def _script_srcs(html: str) -> list[str]:
    return re.findall(r'<script[^>]+src="([^"]+)"', html)


class HttpProbeDriver:
    """只用标准库取页面：能判入口文档与入口脚本，不能执行 JS。"""

    name = "http-probe"

    def available(self) -> tuple[bool, str]:
        return True, "只用 HTTP，不执行 JS"

    def load(self, url: str, *, viewport: tuple[int, int] | None = None, screenshot: str = "") -> LoadedPage:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return LoadedPage(url, resp.status, html=raw, text=_text_of(raw), scripts=_script_srcs(raw))
        except urllib.error.HTTPError as exc:
            return LoadedPage(url, exc.code, page_errors=[f"HTTP {exc.code}"])
        except Exception as exc:  # noqa: BLE001 — 连接失败统一折算成 status=0
            return LoadedPage(url, 0, page_errors=[f"{type(exc).__name__}: {exc}"])


class PlaywrightDriver:
    """真浏览器驱动。

    默认先试 playwright 自带的 chromium；起不来时依次回落到本机已装的 Edge / Chrome
    （`channel=msedge` / `channel=chrome`），这样没有 chromium 也能做真实的浏览器检查。
    """

    name = "playwright"

    def __init__(self, channel: str = "") -> None:
        self.channel = channel
        self.resolved_channel = channel
        self._pw: Any = None
        self._browser: Any = None

    def _ensure_browser(self) -> Any:
        """复用同一个浏览器实例：每次检查都新起一个要 30 秒以上，七项就是四分钟。"""
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._launch(self._pw)
        return self._browser

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("playwright") is None:
            return False, f"未安装 playwright（{PLAYWRIGHT_HINT}）"
        return True, "可用"

    def note(self) -> str:
        used = self.resolved_channel or "自带 chromium"
        return used if self.resolved_channel else "自带 chromium（未回落到本机浏览器）"

    def click_text(self, url: str, text: str, *, screenshot: str = "") -> LoadedPage:
        """打开页面后点一次名为 text 的按钮（没有就点唯一的按钮），再收观察结果。"""
        console_errors: list[str] = []
        page_errors: list[str] = []
        browser = self._ensure_browser()
        page = browser.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            clicked = False
            try:
                page.get_by_role("button", name=text).first.click(timeout=3000)
                clicked = True
            except Exception:  # noqa: BLE001 — 文字不匹配时退化为唯一按钮
                buttons = page.query_selector_all("button")
                if len(buttons) == 1:
                    buttons[0].click()
                    clicked = True
            if not clicked:
                page_errors.append(f"没有找到可点的按钮（{text}）")
            page.wait_for_timeout(1500)
            html = page.content()
            body_text = page.inner_text("body")
            overflow = int(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"))
            shot = ""
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot, full_page=True)
                shot = screenshot
            return LoadedPage(
                url,
                200,
                html=html,
                text=body_text,
                console_errors=console_errors,
                page_errors=page_errors,
                overflow_px=overflow,
                screenshot=shot,
            )
        except Exception as exc:  # noqa: BLE001
            return LoadedPage(url, 0, console_errors=console_errors, page_errors=[f"{type(exc).__name__}: {exc}"])
        finally:
            page.close()

    def _launch(self, pw: Any) -> Any:
        candidates = [self.channel] if self.channel else ["", "msedge", "chrome"]
        last: Exception | None = None
        for candidate in candidates:
            try:
                browser = pw.chromium.launch(channel=candidate) if candidate else pw.chromium.launch()
                self.resolved_channel = candidate
                return browser
            except Exception as exc:  # noqa: BLE001 — 逐个通道尝试，全部失败才报错
                last = exc
        raise RuntimeError(f"没有可用浏览器（自带 chromium 未下载，Edge/Chrome 也起不来）：{last}")

    def load(self, url: str, *, viewport: tuple[int, int] | None = None, screenshot: str = "") -> LoadedPage:
        console_errors: list[str] = []
        page_errors: list[str] = []
        browser = self._ensure_browser()
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]} if viewport else None)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            status = response.status if response else 0
            html = page.content()
            text = page.inner_text("body")
            overflow = int(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"))
            scripts = list(page.evaluate("[...document.scripts].map((s) => s.src)"))
            shot = ""
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot, full_page=True)
                shot = screenshot
            return LoadedPage(
                url,
                status,
                html=html,
                text=text,
                scripts=scripts,
                console_errors=console_errors,
                page_errors=page_errors,
                overflow_px=overflow,
                screenshot=shot,
            )
        except Exception as exc:  # noqa: BLE001 — 浏览器侧失败同样折算成 status=0
            return LoadedPage(url, 0, console_errors=console_errors, page_errors=[f"{type(exc).__name__}: {exc}"])
        finally:
            page.close()


def click_first_action(driver: PageDriver, url: str, *, screenshot: str = "") -> LoadedPage | None:
    """点一次页面主操作按钮（如「开始」），把页面推到会发请求的那一步。

    只有真浏览器驱动支持；HTTP 探针返回 None，由调用方判 BLOCKED。
    选择器优先按可见文字「开始」，否则退化为页面上唯一的按钮（依赖 E 的文案，属可转交的脆弱点）。
    """
    click = getattr(driver, "click_text", None)
    if click is None:
        return None
    return click(url, "开始", screenshot=screenshot)


def pick_driver(prefer: str = "auto", channel: str = "") -> PageDriver:
    if prefer == "http":
        return HttpProbeDriver()
    browser = PlaywrightDriver(channel=channel)
    if prefer == "playwright":
        return browser
    return browser if browser.available()[0] else HttpProbeDriver()


def needs_browser(driver: PageDriver, step: str, expect: str, hint: str = "") -> StepResult | None:
    """需要真实浏览器的检查在 http-probe 下不能算过；返回 None 表示可以继续。"""
    if driver.available()[0] and driver.name != "http-probe":
        return None
    return StepResult(
        step,
        BLOCKED,
        "-",
        expect,
        f"当前驱动 {driver.name} 不能执行 JS",
        detail=(hint or "需要真实浏览器") + "；装法：" + PLAYWRIGHT_HINT,
        repro="python integration/check_web.py --driver playwright",
    )


def http_get(url: str) -> tuple[int, str]:
    """与驱动无关的纯 HTTP 取值：入口脚本这类静态资源不需要执行 JS。"""
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:  # noqa: BLE001 — 连接失败统一返回 0
        return 0, ""


def check_document(driver: PageDriver, url: str) -> StepResult:
    step = "web_document"
    expect = "200 且入口文档含挂载点 id=app 与 /src/main.ts"
    page = driver.load(url, screenshot=str(EVIDENCE_DIR / "document.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"页面服务未响应（{page.failure}）",
            detail="先起页面：cd web && npm ci && npm run dev（127.0.0.1:5173）",
            repro="cd web && npm run dev",
        )
    if page.status != 200:
        return StepResult(
            step, FAIL, "-", expect, f"HTTP {page.status}", detail="页面服务返回非 200", repro=f"curl -i {url}"
        )
    missing = [marker for marker in MOUNT_MARKERS if marker not in page.html]
    if missing:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"HTTP 200 但缺标记 {missing}",
            detail="入口文档不含应用挂载点，页面不会渲染",
            repro=f"curl -s {url}",
        )
    return StepResult(
        step, PASS, "-", expect, "HTTP 200；挂载点与入口脚本引用齐备", detail="入口文档可加载", repro=f"curl -s {url}"
    )


def check_bundle(url: str) -> StepResult:
    step = "web_bundle"
    target = url.rstrip("/") + "/src/main.ts"
    expect = "200 且入口脚本含 createApp（Vite 转译后的模块）"
    status, body = http_get(target)
    if status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            "入口脚本取不到（页面服务未响应）",
            detail="先起页面：cd web && npm run dev",
            repro=f"curl -s {target}",
        )
    if status != 200:
        return StepResult(
            step, FAIL, "-", expect, f"HTTP {status}", detail="入口脚本无法加载，页面会白屏", repro=f"curl -i {target}"
        )
    if "createApp" not in body:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"HTTP 200 但脚本里没有 createApp（{len(body)} 字节）",
            detail="入口脚本没有挂载调用",
            repro=f"curl -s {target}",
        )
    return StepResult(step, PASS, "-", expect, f"HTTP 200；{len(body)} 字节，含挂载调用", repro=f"curl -s {target}")


def check_shell(driver: PageDriver, url: str) -> StepResult:
    step = "web_shell"
    expect = "挂载成功：正文含品牌与模式徽标、footer 文案，且无未捕获 JS 错误"
    gate = needs_browser(driver, step, expect, "挂载与白屏只能在真浏览器里判")
    if gate:
        return gate
    page = driver.load(url, screenshot=str(EVIDENCE_DIR / "shell.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"页面服务未响应（{page.failure}）",
            detail="先起页面",
            repro="cd web && npm run dev",
        )
    if page.page_errors:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"页面抛未捕获异常：{page.page_errors[0]}",
            detail="挂载失败",
            repro=f"浏览器打开 {url}",
        )
    if "CoursePilot" not in page.text:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"正文没有品牌名（{len(page.text)} 字）",
            detail="页面未挂载或白屏",
            repro=f"浏览器打开 {url}",
        )
    if not any(label in page.text for label in SHELL_TEXTS[1:]):
        return StepResult(
            step, FAIL, "-", expect, "正文没有模式徽标", detail="真实/演示模式徽标缺失", repro=f"浏览器打开 {url}"
        )
    if FOOTER_TEXT not in page.text:
        return StepResult(
            step, FAIL, "-", expect, "正文没有 footer 说明", detail="页面外壳不完整", repro=f"浏览器打开 {url}"
        )
    return StepResult(
        step,
        PASS,
        "-",
        expect,
        "已挂载；品牌、模式徽标与 footer 齐备",
        detail=f"截图：{page.screenshot or '未留存'}",
        repro=f"浏览器打开 {url}",
    )


def check_api_down(driver: PageDriver, url: str, api_reachable: bool, stub_active: bool = False) -> StepResult:
    step = "web_api_down"
    expect = "Python 不可达时页面给出错误与重试入口，不白屏、不切换演示数据"
    gate = needs_browser(driver, step, expect, "页面行为只能在真浏览器里判")
    if gate:
        return gate
    if api_reachable:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            "Python 当前可达，本分支需要它在不可达状态",
            detail="停掉 Python 服务（或在别的端口起一个未接通实例）后重跑本检查",
            repro="python integration/check_web.py --api-url http://127.0.0.1:8000",
        )
    page = driver.load(url, screenshot=str(EVIDENCE_DIR / "api-down.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"页面服务未响应（{page.failure}）",
            detail="先起页面",
            repro="cd web && npm run dev",
        )
    if len(page.text) < 40:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"正文只有 {len(page.text)} 字，疑似白屏",
            detail="服务失败时页面没有内容",
            repro=f"浏览器打开 {url}",
        )
    if not any(marker in page.text for marker in RETRY_MARKERS):
        pushed = click_first_action(driver, url, screenshot=str(EVIDENCE_DIR / "api-down-after-click.png"))
        if pushed is None:
            return StepResult(
                step,
                BLOCKED,
                "-",
                expect,
                "首屏没有错误提示，且当前驱动不支持点按钮",
                detail="需要真浏览器：页面要先点「开始」才会发请求",
                repro="python integration/check_web.py --driver playwright",
            )
        page = pushed
        if not any(marker in page.text for marker in RETRY_MARKERS):
            return StepResult(
                step,
                FAIL,
                "-",
                expect,
                "点了主操作之后仍没有错误提示与重试入口",
                detail="服务失败时页面未给出可操作提示",
                repro=f"浏览器打开 {url}",
            )
    if page.page_errors:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"页面抛未捕获异常：{page.page_errors[0]}",
            detail="失败分支下页面崩了",
            repro=f"浏览器打开 {url}",
        )
    return StepResult(
        step,
        PASS,
        "-",
        expect,
        "出现错误提示与重试入口，页面未白屏",
        detail=f"截图：{page.screenshot or '未留存'}",
        repro=f"浏览器打开 {url}",
    )


def check_unknown(driver: PageDriver, stub_url: str | None) -> StepResult:
    step = "web_unknown"
    expect = "接口答未知/无法核验时页面显示未知并可继续，不假装成功"
    if not stub_url:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            "没有受控假响应可用",
            detail="需要受控假响应服务（第 6 件的 CI 假响应开关）返回 UNABLE_TO_VERIFY；届时用 --stub-url 指定",
            repro="python integration/check_web.py --stub-url http://127.0.0.1:8099",
        )
    gate = needs_browser(driver, step, expect, "页面行为只能在真浏览器里判")
    if gate:
        return gate
    page = driver.load(stub_url, screenshot=str(EVIDENCE_DIR / "unknown.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"受控假响应未响应（{page.failure}）",
            detail="先起假响应服务",
            repro=f"curl -i {stub_url}",
        )
    if "未知" not in page.text and "无法核验" not in page.text:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            "正文没有未知/无法核验的说明",
            detail="答未知时页面未如实呈现",
            repro=f"浏览器打开 {stub_url}",
        )
    return StepResult(
        step,
        PASS,
        "-",
        expect,
        "如实呈现未知",
        detail=f"截图：{page.screenshot or '未留存'}",
        repro=f"浏览器打开 {stub_url}",
    )


def check_narrow(driver: PageDriver, url: str) -> StepResult:
    step = "web_narrow"
    expect = f"390x844 视口下无横向溢出（scrollWidth - clientWidth <= {NARROW_OVERFLOW_TOLERANCE}px）"
    gate = needs_browser(driver, step, expect, "窄屏版式只能在真浏览器里量")
    if gate:
        return gate
    page = driver.load(url, viewport=(390, 844), screenshot=str(EVIDENCE_DIR / "narrow.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"页面服务未响应（{page.failure}）",
            detail="先起页面",
            repro="cd web && npm run dev",
        )
    if page.overflow_px is None:
        return StepResult(
            step, FAIL, "-", expect, "拿不到横向溢出量", detail="浏览器没返回 scrollWidth", repro=f"浏览器打开 {url}"
        )
    if page.overflow_px > NARROW_OVERFLOW_TOLERANCE:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"横向溢出 {page.overflow_px}px",
            detail="窄屏出现横向滚动",
            repro=f"浏览器 390x844 打开 {url}",
        )
    return StepResult(
        step,
        PASS,
        "-",
        expect,
        f"无横向溢出（{page.overflow_px}px）",
        detail=f"截图：{page.screenshot or '未留存'}",
        repro=f"浏览器 390x844 打开 {url}",
    )


def check_stub_path(driver: PageDriver, url: str) -> StepResult:
    """受控假响应当上游时，页面应进入引导第一问（而不是错误区块）。"""
    step = "web_stub_path"
    expect = (
        "受控假响应当上游时页面进入引导第一问（问题卡渲染、无错误区块）；"
        "要求页面以 CP_API_BASE_URL（默认 http://127.0.0.1:8000）为上游"
    )
    gate = needs_browser(driver, step, expect, "页面渲染只能在真浏览器里判")
    if gate:
        return gate
    page = driver.load(url, screenshot=str(EVIDENCE_DIR / "stub-path.png"))
    if page.status == 0:
        return StepResult(
            step,
            BLOCKED,
            "-",
            expect,
            f"页面服务未响应（{page.failure}）",
            detail="先起页面",
            repro="cd web && npm run dev",
        )
    if page.page_errors:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            f"页面抛未捕获异常：{page.page_errors[0]}",
            detail="受控上游下挂载失败",
            repro=f"浏览器打开 {url}",
        )
    if 'id="no-curriculum-title"' in page.html or 'id="missing-curriculum-title"' in page.html:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            "页面显示了「没有培养方案」区块",
            detail="受控上游已提供已发布培养方案，不应落到该分支",
            repro=f"浏览器打开 {url}",
        )
    if 'id="question-title"' not in page.html:
        pushed = click_first_action(driver, url, screenshot=str(EVIDENCE_DIR / "stub-path-after-click.png"))
        if pushed is not None:
            page = pushed
    if 'id="question-title"' not in page.html:
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            "页面没有渲染问题卡（question-title 缺失）",
            detail="受控上游下未进入引导流程，可能是错误区块",
            repro=f"浏览器打开 {url}",
        )
    return StepResult(
        step,
        PASS,
        "-",
        expect,
        "已进入引导第一问",
        detail=f"截图：{page.screenshot or '未留存'}",
        repro=f"浏览器打开 {url}",
    )


CHECK_ORDER = (
    "web_document",
    "web_bundle",
    "web_shell",
    "web_api_down",
    "web_unknown",
    "web_stub_path",
    "web_narrow",
)
CHECK_EXPECT = {
    "web_document": "入口文档 200 且含挂载点与入口脚本引用（HTTP 即可）",
    "web_bundle": "入口脚本 200 且含 createApp（HTTP 即可）",
    "web_shell": "页面挂载成功、外壳齐备、无未捕获 JS 错误（需浏览器）",
    "web_api_down": "Python 不可达时显示错误与重试入口、不白屏（需浏览器）",
    "web_unknown": "接口答未知时如实呈现并可继续（需浏览器 + 受控假响应）",
    "web_stub_path": "受控假响应当上游时页面进入引导第一问（需浏览器 + 受控响应）",
    "web_narrow": "390x844 无横向溢出（需浏览器）",
}


def reconcile(rows: list[StepResult]) -> list[StepResult]:
    """跨项一致性：`web_stub_path` 失败说明页面连不上可用上游，那 `web_api_down` 的通过不能算数。"""
    by_step = {row.step: row for row in rows}
    stub = by_step.get("web_stub_path")
    down = by_step.get("web_api_down")
    if stub and down and stub.verdict == FAIL and down.verdict == PASS:
        replacement = StepResult(
            "web_api_down",
            BLOCKED,
            down.request_id,
            down.expect,
            "页面与可用上游的通信本身有故障（见 web_stub_path）",
            detail="本条只能证明页面会报错，不能证明失败分支；先修 web_stub_path",
            repro="python integration/check_web.py --with-stub --driver playwright",
        )
        for index, row in enumerate(rows):  # 必须替换列表里的那一项，只改字典不会生效
            if row.step == "web_api_down":
                rows[index] = replacement
    return rows


def run_web_checks(
    driver: PageDriver, url: str, api_reachable: bool, stub_url: str | None = None, with_stub: bool = False
) -> list[StepResult]:
    rows = [
        check_document(driver, url),
        check_bundle(url),
        check_shell(driver, url),
        check_api_down(driver, url, api_reachable, stub_active=with_stub and not api_reachable),
        check_unknown(driver, stub_url),
        check_stub_path(driver, url)
        if with_stub
        else StepResult(
            "web_stub_path",
            BLOCKED,
            "-",
            CHECK_EXPECT["web_stub_path"],
            "未启用受控上游（--with-stub）",
            detail="加 --with-stub 且页面以 CP_API_BASE_URL 为上游时才会跑",
            repro="python integration/check_web.py --with-stub --driver playwright",
        ),
        check_narrow(driver, url),
    ]
    return reconcile(rows)


def plan_rows() -> list[StepResult]:
    return [StepResult(name, "PLAN", "-", CHECK_EXPECT[name], "计划模式：不连页面") for name in CHECK_ORDER]

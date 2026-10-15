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
from typing import Protocol

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
    """真浏览器驱动；未安装 playwright 或未下载 chromium 时判不可用，由调用方给 BLOCKED。"""

    name = "playwright"

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("playwright") is None:
            return False, f"未安装 playwright（{PLAYWRIGHT_HINT}）"
        return True, "可用"

    def load(self, url: str, *, viewport: tuple[int, int] | None = None, screenshot: str = "") -> LoadedPage:
        from playwright.sync_api import sync_playwright

        console_errors: list[str] = []
        page_errors: list[str] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]} if viewport else None)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            try:
                response = page.goto(url, wait_until="networkidle", timeout=20000)
                status = response.status if response else 0
                html = page.content()
                text = page.inner_text("body")
                overflow = int(
                    page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                )
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
                browser.close()


def pick_driver(prefer: str = "auto") -> PageDriver:
    if prefer == "http":
        return HttpProbeDriver()
    browser = PlaywrightDriver()
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


def check_api_down(driver: PageDriver, url: str, api_reachable: bool) -> StepResult:
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
        return StepResult(
            step,
            FAIL,
            "-",
            expect,
            "正文没有错误提示与重试入口",
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


CHECK_ORDER = ("web_document", "web_bundle", "web_shell", "web_api_down", "web_unknown", "web_narrow")
CHECK_EXPECT = {
    "web_document": "入口文档 200 且含挂载点与入口脚本引用（HTTP 即可）",
    "web_bundle": "入口脚本 200 且含 createApp（HTTP 即可）",
    "web_shell": "页面挂载成功、外壳齐备、无未捕获 JS 错误（需浏览器）",
    "web_api_down": "Python 不可达时显示错误与重试入口、不白屏（需浏览器）",
    "web_unknown": "接口答未知时如实呈现并可继续（需浏览器 + 受控假响应）",
    "web_narrow": "390x844 无横向溢出（需浏览器）",
}


def run_web_checks(driver: PageDriver, url: str, api_reachable: bool, stub_url: str | None = None) -> list[StepResult]:
    return [
        check_document(driver, url),
        check_bundle(url),
        check_shell(driver, url),
        check_api_down(driver, url, api_reachable),
        check_unknown(driver, stub_url),
        check_narrow(driver, url),
    ]


def plan_rows() -> list[StepResult]:
    return [StepResult(name, "PLAN", "-", CHECK_EXPECT[name], "计划模式：不连页面") for name in CHECK_ORDER]

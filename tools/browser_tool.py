"""Browser Tool - Interaksi browser web menggunakan Playwright."""

import asyncio
import base64
import logging
import os
from typing import Any, Optional, Literal

logger = logging.getLogger(__name__)


class BrowserTool:
    def __init__(self, headless: bool = True, viewport_width: int = 1280, viewport_height: int = 720):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.current_url: Optional[str] = None
        self.page_title: Optional[str] = None
        self.navigation_history: list[str] = []
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._initialized = False

    _lib_paths_configured = False

    @classmethod
    def _setup_library_paths(cls):
        if cls._lib_paths_configured:
            return
        cls._lib_paths_configured = True
        try:
            extra_paths = set()
            known_lib = "/nix/store/24w3s75aa2lrvvxsybficn8y3zxd27kp-mesa-libgbm-25.1.0/lib"
            if os.path.isdir(known_lib):
                extra_paths.add(known_lib)
            else:
                import ctypes.util
                if not ctypes.util.find_library("gbm"):
                    for entry in os.scandir("/nix/store"):
                        if "mesa-libgbm" in entry.name and entry.is_dir():
                            lib_dir = os.path.join(entry.path, "lib")
                            if os.path.isdir(lib_dir):
                                extra_paths.add(lib_dir)
                                break

            if extra_paths:
                current = os.environ.get("LD_LIBRARY_PATH", "")
                combined = ":".join(extra_paths)
                if current:
                    combined = combined + ":" + current
                os.environ["LD_LIBRARY_PATH"] = combined
                logger.info("Library paths configured for browser")
        except Exception as e:
            logger.warning(f"Could not auto-configure library paths: {e}")

    async def _ensure_browser(self):
        if self._initialized and self._page and not self._page.is_closed():
            return
        try:
            self._setup_library_paths()
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            self._context = await self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ManusAgent/1.0",
            )
            self._page = await self._context.new_page()
            self._initialized = True
            logger.info("Browser Playwright berhasil diinisialisasi")
        except Exception as e:
            logger.error(f"Gagal menginisialisasi browser: {e}")
            self._initialized = False
            raise

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        url = plan.get("analysis", {}).get("input", "")
        if url and url.startswith("http"):
            result = await self.navigate(url)
            return result.get("message", str(result))
        return (
            f"Browser tool siap. Intent: {intent}. "
            f"Operasi tersedia: navigate, screenshot, click, fill_form, get_content, execute_js, extract_text, extract_links."
        )

    async def navigate(self, url: str, wait_until: Literal["domcontentloaded", "load", "networkidle", "commit"] = "domcontentloaded", timeout: int = 30000) -> dict:
        try:
            await self._ensure_browser()
            response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)
            self.current_url = self._page.url
            self.page_title = await self._page.title()
            self.navigation_history.append(self.current_url)
            status = response.status if response else 0
            logger.info(f"Navigasi ke: {url} (status: {status})")
            return {
                "success": True,
                "url": self.current_url,
                "title": self.page_title,
                "status_code": status,
                "message": f"Berhasil navigasi ke {self.current_url} - '{self.page_title}' (HTTP {status})",
            }
        except Exception as e:
            logger.error(f"Gagal navigasi ke {url}: {e}")
            return {"success": False, "url": url, "error": str(e), "message": f"Gagal navigasi: {e}"}

    async def screenshot(self, path: str = "screenshot.png", full_page: bool = False) -> dict:
        try:
            await self._ensure_browser()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            await self._page.screenshot(path=path, full_page=full_page)
            file_size = os.path.getsize(path)
            logger.info(f"Screenshot disimpan: {path} ({file_size} bytes)")
            return {
                "success": True,
                "path": path,
                "size_bytes": file_size,
                "full_page": full_page,
                "message": f"Screenshot disimpan: {path} ({file_size} bytes)",
            }
        except Exception as e:
            logger.error(f"Gagal screenshot: {e}")
            return {"success": False, "error": str(e), "message": f"Gagal screenshot: {e}"}

    async def screenshot_base64(self, full_page: bool = False) -> dict:
        try:
            await self._ensure_browser()
            screenshot_bytes = await self._page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return {"success": True, "base64": b64, "size_bytes": len(screenshot_bytes)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_content(self) -> dict:
        try:
            await self._ensure_browser()
            content = await self._page.content()
            title = await self._page.title()
            return {
                "success": True,
                "url": self._page.url,
                "title": title,
                "content": content,
                "content_length": len(content),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def extract_text(self, selector: Optional[str] = None) -> dict:
        try:
            await self._ensure_browser()
            if selector:
                elements = await self._page.query_selector_all(selector)
                texts = []
                for el in elements:
                    text = await el.inner_text()
                    texts.append(text.strip())
                return {"success": True, "selector": selector, "texts": texts, "count": len(texts)}
            else:
                text = await self._page.inner_text("body")
                return {"success": True, "text": text[:50000], "length": len(text)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def extract_links(self) -> dict:
        try:
            await self._ensure_browser()
            links = await self._page.evaluate("""
                () => {
                    const anchors = document.querySelectorAll('a[href]');
                    return Array.from(anchors).map(a => ({
                        text: a.innerText.trim().substring(0, 200),
                        href: a.href,
                    })).filter(l => l.href && l.href.startsWith('http'));
                }
            """)
            return {"success": True, "links": links[:200], "total": len(links)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click_element(self, selector: str, timeout: int = 10000) -> dict:
        try:
            await self._ensure_browser()
            await self._page.click(selector, timeout=timeout)
            await self._page.wait_for_load_state("domcontentloaded")
            self.current_url = self._page.url
            logger.info(f"Klik elemen: {selector}")
            return {
                "success": True,
                "selector": selector,
                "current_url": self.current_url,
                "message": f"Elemen '{selector}' diklik",
            }
        except Exception as e:
            return {"success": False, "selector": selector, "error": str(e), "message": f"Gagal klik: {e}"}

    async def fill_form(self, selector: str, value: str, timeout: int = 10000) -> dict:
        try:
            await self._ensure_browser()
            await self._page.fill(selector, value, timeout=timeout)
            logger.info(f"Form diisi: {selector}")
            return {"success": True, "selector": selector, "message": f"Formulir '{selector}' diisi"}
        except Exception as e:
            return {"success": False, "selector": selector, "error": str(e)}

    async def type_text(self, selector: str, text: str, delay: int = 50) -> dict:
        try:
            await self._ensure_browser()
            await self._page.type(selector, text, delay=delay)
            return {"success": True, "selector": selector, "message": f"Teks diketik ke '{selector}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str, selector: Optional[str] = None) -> dict:
        try:
            await self._ensure_browser()
            if selector:
                await self._page.press(selector, key)
            else:
                await self._page.keyboard.press(key)
            return {"success": True, "key": key, "message": f"Tombol '{key}' ditekan"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_option(self, selector: str, value: str) -> dict:
        try:
            await self._ensure_browser()
            await self._page.select_option(selector, value)
            return {"success": True, "selector": selector, "value": value, "message": f"Opsi '{value}' dipilih"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_javascript(self, script: str) -> dict:
        try:
            await self._ensure_browser()
            result = await self._page.evaluate(script)
            logger.info(f"JavaScript dieksekusi: {script[:100]}")
            return {"success": True, "result": result, "message": "JavaScript dieksekusi"}
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"Gagal eksekusi JS: {e}"}

    async def wait_for_element(self, selector: str, timeout: int = 30000, state: Literal["attached", "detached", "visible", "hidden"] = "visible") -> dict:
        try:
            await self._ensure_browser()
            await self._page.wait_for_selector(selector, timeout=timeout, state=state)
            return {"success": True, "selector": selector, "message": f"Elemen '{selector}' ditemukan ({state})"}
        except Exception as e:
            return {"success": False, "selector": selector, "error": str(e)}

    async def wait_for_navigation(self, timeout: int = 30000) -> dict:
        try:
            await self._ensure_browser()
            await self._page.wait_for_load_state("domcontentloaded", timeout=timeout)
            self.current_url = self._page.url
            return {"success": True, "url": self.current_url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        try:
            await self._ensure_browser()
            if direction == "down":
                await self._page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self._page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "top":
                await self._page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return {"success": True, "direction": direction, "amount": amount}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_attribute(self, selector: str, attribute: str) -> dict:
        try:
            await self._ensure_browser()
            value = await self._page.get_attribute(selector, attribute)
            return {"success": True, "selector": selector, "attribute": attribute, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_cookies(self) -> list:
        try:
            await self._ensure_browser()
            cookies = await self._context.cookies()
            return cookies
        except Exception:
            return []

    async def set_cookie(self, name: str, value: str, domain: str = "", url: str = "") -> dict:
        try:
            await self._ensure_browser()
            cookie: dict[str, Any] = {"name": name, "value": value}
            if domain:
                cookie["domain"] = domain
            if url:
                cookie["url"] = url
            elif self.current_url:
                cookie["url"] = self.current_url
            await self._context.add_cookies([cookie])
            return {"success": True, "name": name, "message": "Cookie diset"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_navigation_history(self) -> list[str]:
        return self.navigation_history

    async def go_back(self) -> dict:
        try:
            await self._ensure_browser()
            await self._page.go_back()
            self.current_url = self._page.url
            return {"success": True, "url": self.current_url, "message": "Kembali ke halaman sebelumnya"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def go_forward(self) -> dict:
        try:
            await self._ensure_browser()
            await self._page.go_forward()
            self.current_url = self._page.url
            return {"success": True, "url": self.current_url, "message": "Maju ke halaman berikutnya"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error menutup browser: {e}")
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
            self._initialized = False
            self.current_url = None
            logger.info("Browser ditutup")

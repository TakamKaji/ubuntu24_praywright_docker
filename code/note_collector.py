import argparse
import asyncio
import csv
import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

BASE_DIR = Path(os.environ.get("NOTE_BASE_DIR", "/app"))
WATCH_FILE = Path(os.environ.get("NOTE_WATCH_FILE", BASE_DIR / "note_watch_list.csv"))
OUTPUT_DIR = Path(os.environ.get("NOTE_OUTPUT_DIR", BASE_DIR / "result" / "note"))
STATUS_FILE = OUTPUT_DIR / "latest_status.json"
INDEX_FILE = OUTPUT_DIR / "index.json"
LOCK_FILE = OUTPUT_DIR / ".collector.lock"
CDP_URL = os.environ.get("NOTE_CDP_URL", "http://127.0.0.1:9222")
DEFAULT_INTERVAL = int(os.environ.get("NOTE_POLL_SECONDS", "1800"))
JST = ZoneInfo("Asia/Tokyo")

NOTE_ARTICLE_RE = re.compile(r"^https://note\.com/[^/?#]+/n/([^/?#]+)")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
IMAGE_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_note_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() != "note.com":
        return url.strip()
    return f"https://note.com{parsed.path}".rstrip("/")


def extract_note_id(url: str) -> str | None:
    match = NOTE_ARTICLE_RE.match(normalize_note_url(url))
    return match.group(1) if match else None


def safe_title_filename(title: str, limit: int = 120) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", title or "")
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    if not value:
        value = "untitled_article"
    if value.upper() in WINDOWS_RESERVED_NAMES:
        value += "_"
    return value[:limit].rstrip(". ") or "untitled_article"


def extension_from_response(url: str, content_type: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in IMAGE_MIME_EXTENSIONS:
        return IMAGE_MIME_EXTENSIONS[mime]

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed or ".bin"


def load_watch_list() -> list[tuple[str, str]]:
    if not WATCH_FILE.exists():
        return []

    targets: list[tuple[str, str]] = []
    with WATCH_FILE.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            first = row[0].strip()
            if not first or first.startswith("#"):
                continue
            if first.lower() in {"name", "category"}:
                continue

            if len(row) == 1:
                name = "default"
                url = first
            else:
                name = first
                url = row[1].strip()

            if url:
                targets.append((name or "default", normalize_note_url(url)))
    return targets


def load_index() -> dict:
    if not INDEX_FILE.exists():
        return {"schema_version": 1, "articles": {}}
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("articles"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema_version": 1, "articles": {}}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_status(status: str, **extra) -> None:
    payload = {
        "status": status,
        "updated_at": now_iso(),
        **extra,
    }
    save_json(STATUS_FILE, payload)


class CollectorLock:
    def __enter__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"collector is already running: {LOCK_FILE}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()}\n")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass


async def connect_existing_chrome(playwright) -> tuple[Browser, BrowserContext]:
    browser = await playwright.chromium.connect_over_cdp(CDP_URL, timeout=10_000)
    if not browser.contexts:
        raise RuntimeError("Chrome context was not found")
    return browser, browser.contexts[0]


async def scroll_until_stable(page: Page, step: int = 600, stable_rounds: int = 5) -> None:
    await page.evaluate(
        """async ({step, stableRounds}) => {
            let stable = 0;
            let previousHeight = 0;
            for (let i = 0; i < 300; i++) {
                document.querySelectorAll('details:not([open])').forEach(el => el.open = true);
                const height = document.documentElement.scrollHeight;
                window.scrollBy(0, step);
                await new Promise(resolve => setTimeout(resolve, 250));
                const nextHeight = document.documentElement.scrollHeight;
                const atBottom = window.scrollY + window.innerHeight >= nextHeight - 20;
                if (atBottom && nextHeight === previousHeight) {
                    stable++;
                } else {
                    stable = 0;
                }
                previousHeight = nextHeight;
                if (stable >= stableRounds) break;
            }
            window.scrollTo(0, 0);
        }""",
        {"step": step, "stableRounds": stable_rounds},
    )
    await page.wait_for_timeout(1000)


async def discover_articles(page: Page, watch_url: str) -> dict[str, str]:
    if extract_note_id(watch_url):
        return {normalize_note_url(watch_url): ""}

    response = await page.goto(watch_url, wait_until="domcontentloaded", timeout=60_000)
    if response and response.status >= 400:
        raise RuntimeError(f"watch page returned HTTP {response.status}: {watch_url}")
    await page.wait_for_timeout(1500)
    await scroll_until_stable(page)

    items = await page.evaluate(
        """() => {
            const result = new Map();
            for (const a of document.querySelectorAll('a[href]')) {
                let url;
                try {
                    url = new URL(a.href, location.href);
                } catch {
                    continue;
                }
                if (url.hostname !== 'note.com' || !/\/[^/]+\/n\/[^/?#]+/.test(url.pathname)) continue;
                url.search = '';
                url.hash = '';

                let time = a.querySelector('time');
                let parent = a.parentElement;
                for (let i = 0; !time && i < 8 && parent; i++, parent = parent.parentElement) {
                    time = parent.querySelector('time');
                }
                const updatedAt = time?.getAttribute('datetime') || '';
                const clean = `${url.origin}${url.pathname}`.replace(/\/$/, '');
                if (!result.has(clean) || (updatedAt && !result.get(clean))) {
                    result.set(clean, updatedAt);
                }
            }
            return Object.fromEntries(result);
        }"""
    )
    return {normalize_note_url(url): value for url, value in items.items()}


async def prepare_article_dom(page: Page) -> dict:
    return await page.evaluate(
        """() => {
            const garbageSelectors = [
                'header', 'nav', 'footer',
                '.p-article__footer',
                '.p-article__rating',
                '.p-article__labels',
                '.p-article__creator',
                '.o-articleSupport',
                '.o-comment',
                '[class*="recommend"]',
                '[class*="Recommend"]',
                '[class*="popular"]',
                '[class*="Popular"]',
                '[class*="comment"]',
                '[class*="Comment"]',
                '[class*="sidebar"]',
                '[id*="sidebar"]',
                '.ad', '.ads', '.advertisement'
            ];
            document.querySelectorAll(garbageSelectors.join(',')).forEach(el => el.remove());
            document.querySelectorAll('details:not([open])').forEach(el => el.open = true);

            const h1 = document.querySelector('h1');
            const ogTitle = document.querySelector('meta[property="og:title"]')?.content || '';
            const title = (h1?.innerText || ogTitle || document.title || 'untitled_article').trim();

            const published =
                document.querySelector('meta[property="article:published_time"]')?.content ||
                document.querySelector('time[datetime]')?.getAttribute('datetime') ||
                '';
            const updated =
                document.querySelector('meta[property="article:modified_time"]')?.content ||
                '';

            const root =
                document.querySelector('article') ||
                document.querySelector('[role="article"]') ||
                document.querySelector('main') ||
                document.body;

            const images = Array.from(root.querySelectorAll('img')).map((img, index) => ({
                index,
                url: img.currentSrc || img.src || '',
                alt: img.alt || ''
            })).filter(item => /^https?:\/\//.test(item.url));

            return {title, published, updated, images};
        }"""
    )


async def download_images(
    context: BrowserContext,
    page: Page,
    article_dir: Path,
    source_url: str,
    image_items: list[dict],
) -> tuple[list[dict], list[dict]]:
    image_dir = article_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict] = []
    failed: list[dict] = []
    replacements: list[dict] = []

    seen: dict[str, str] = {}
    sequence = 0

    for item in image_items:
        url = item.get("url", "")
        index = item.get("index")
        if not url:
            continue

        if url in seen:
            replacements.append({"index": index, "path": seen[url]})
            continue

        response = None
        last_error = None
        for attempt in range(3):
            try:
                response = await context.request.get(
                    url,
                    headers={"Referer": source_url},
                    timeout=30_000,
                    fail_on_status_code=False,
                )
                if response.ok:
                    break
                last_error = f"HTTP {response.status}"
            except Exception as exc:
                last_error = str(exc)
            await asyncio.sleep(1 + attempt)

        if not response or not response.ok:
            failed.append({"source_url": url, "error": last_error or "download failed"})
            continue

        sequence += 1
        content_type = response.headers.get("content-type", "")
        ext = extension_from_response(url, content_type)
        relative_path = f"images/{sequence:03d}{ext}"
        target = article_dir / relative_path
        target.write_bytes(await response.body())

        seen[url] = relative_path
        replacements.append({"index": index, "path": relative_path})
        downloaded.append(
            {
                "source_url": url,
                "path": relative_path,
                "content_type": content_type.split(";", 1)[0],
            }
        )

    if replacements:
        await page.evaluate(
            """(replacements) => {
                const root =
                    document.querySelector('article') ||
                    document.querySelector('[role="article"]') ||
                    document.querySelector('main') ||
                    document.body;
                const images = Array.from(root.querySelectorAll('img'));
                for (const item of replacements) {
                    const img = images[item.index];
                    if (!img) continue;
                    img.setAttribute('src', item.path);
                    img.removeAttribute('srcset');
                    img.removeAttribute('sizes');
                    const picture = img.closest('picture');
                    if (picture) {
                        picture.querySelectorAll('source').forEach(source => source.remove());
                    }
                }
            }""",
            replacements,
        )

    return downloaded, failed


async def extract_article_html(page: Page) -> str:
    return await page.evaluate(
        """() => {
            const root =
                document.querySelector('article') ||
                document.querySelector('[role="article"]') ||
                document.querySelector('main') ||
                document.body;
            return root.outerHTML;
        }"""
    )


def should_skip(index_entry: dict | None, discovered_updated_at: str) -> bool:
    if not index_entry:
        return False
    if not discovered_updated_at:
        return True

    remote = parse_iso_datetime(discovered_updated_at)
    local = parse_iso_datetime(index_entry.get("updated_at") or index_entry.get("published_at"))
    if remote and local:
        return remote <= local
    return False


async def fetch_article(
    context: BrowserContext,
    page: Page,
    md_generator: DefaultMarkdownGenerator,
    url: str,
    discovered_updated_at: str,
    index: dict,
) -> dict:
    note_id = extract_note_id(url)
    if not note_id:
        raise ValueError(f"not a note article URL: {url}")

    existing = index["articles"].get(note_id)
    if should_skip(existing, discovered_updated_at):
        return {"result": "skipped", "note_id": note_id, "url": url}

    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if response and response.status >= 400:
        raise RuntimeError(f"article returned HTTP {response.status}: {url}")
    if "/login" in page.url or "/signin" in page.url:
        raise PermissionError("note login is required")

    await page.wait_for_timeout(1500)
    await scroll_until_stable(page)
    info = await prepare_article_dom(page)

    published_dt = parse_iso_datetime(info.get("published")) or datetime.now(JST)
    folder_date = published_dt.astimezone(JST).date().isoformat()
    article_dir = OUTPUT_DIR / f"{folder_date}_{note_id}"
    article_dir.mkdir(parents=True, exist_ok=True)

    if existing:
        old_article_file = existing.get("article_file")
        if old_article_file:
            old_path = article_dir / old_article_file
            if old_path.exists():
                old_path.unlink()
        old_images = article_dir / "images"
        if old_images.exists():
            for child in old_images.iterdir():
                if child.is_file():
                    child.unlink()

    downloaded, image_errors = await download_images(
        context=context,
        page=page,
        article_dir=article_dir,
        source_url=url,
        image_items=info.get("images", []),
    )

    html = await extract_article_html(page)
    md_result = md_generator.generate_markdown(input_html=html)
    markdown = (md_result.fit_markdown or md_result.raw_markdown or "").strip()
    if not markdown:
        raise RuntimeError(f"markdown extraction returned empty content: {url}")

    title = safe_title_filename(info.get("title") or "untitled_article")
    article_filename = f"{title}.md"
    article_path = article_dir / article_filename
    article_path.write_text(
        f"<!-- Source: {url} -->\n\n{markdown}\n",
        encoding="utf-8",
    )

    published_at = info.get("published") or ""
    updated_at = info.get("updated") or discovered_updated_at or published_at
    metadata = {
        "schema_version": 1,
        "source": "note.com",
        "source_url": url,
        "note_id": note_id,
        "title": info.get("title") or title,
        "published_at": published_at or None,
        "updated_at": updated_at or None,
        "fetched_at": now_iso(),
        "article_file": article_filename,
        "images": downloaded,
        "image_errors": image_errors,
    }
    save_json(article_dir / "metadata.json", metadata)

    index["articles"][note_id] = {
        "source_url": url,
        "path": article_dir.name,
        "article_file": article_filename,
        "title": metadata["title"],
        "published_at": metadata["published_at"],
        "updated_at": metadata["updated_at"],
        "fetched_at": metadata["fetched_at"],
    }
    save_json(INDEX_FILE, index)

    return {
        "result": "saved",
        "note_id": note_id,
        "url": url,
        "path": str(article_dir),
        "article_file": article_filename,
        "images": len(downloaded),
        "image_errors": len(image_errors),
    }


async def collect_once() -> dict:
    targets = load_watch_list()
    if not targets:
        write_status("idle", message=f"no watch targets in {WATCH_FILE}")
        return {"saved": 0, "skipped": 0, "errors": 0, "targets": 0}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()
    stats = {"saved": 0, "skipped": 0, "errors": 0, "targets": len(targets)}
    errors: list[dict] = []

    md_generator = DefaultMarkdownGenerator(
        options={
            "ignore_links": True,
            "ignore_images": False,
            "escape_html": False,
            "body_width": 0,
        }
    )

    write_status("running", targets=len(targets))

    async with async_playwright() as playwright:
        try:
            _, context = await connect_existing_chrome(playwright)
        except Exception as exc:
            write_status("browser_down", cdp_url=CDP_URL, error=str(exc))
            raise

        page = await context.new_page()
        try:
            for name, watch_url in targets:
                try:
                    discovered = await discover_articles(page, watch_url)
                except Exception as exc:
                    stats["errors"] += 1
                    errors.append({"watch": name, "url": watch_url, "error": str(exc)})
                    continue

                for article_url, discovered_updated_at in discovered.items():
                    try:
                        result = await fetch_article(
                            context=context,
                            page=page,
                            md_generator=md_generator,
                            url=article_url,
                            discovered_updated_at=discovered_updated_at,
                            index=index,
                        )
                        stats[result["result"]] += 1
                    except PermissionError as exc:
                        write_status(
                            "auth_required",
                            watch=name,
                            url=article_url,
                            error=str(exc),
                        )
                        raise
                    except Exception as exc:
                        stats["errors"] += 1
                        errors.append({"watch": name, "url": article_url, "error": str(exc)})
        finally:
            await page.close()

    final_status = "ok" if not errors else "partial_error"
    write_status(final_status, **stats, errors=errors[-20:])
    return stats


async def daemon(interval: int) -> None:
    while True:
        try:
            with CollectorLock():
                stats = await collect_once()
                print(json.dumps({"event": "cycle_complete", **stats}, ensure_ascii=False), flush=True)
        except RuntimeError as exc:
            print(f"collector busy: {exc}", flush=True)
        except PermissionError as exc:
            print(f"authentication required: {exc}", flush=True)
        except Exception as exc:
            print(f"collector cycle failed: {exc}", flush=True)
        await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect note.com articles through an already-running Google Chrome.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run one collection cycle")
    mode.add_argument("--daemon", action="store_true", help="run forever")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="daemon interval in seconds")
    args = parser.parse_args()

    try:
        if args.daemon:
            asyncio.run(daemon(max(60, args.interval)))
        else:
            with CollectorLock():
                stats = asyncio.run(collect_once())
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"note login is required: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **⚠️ IMPORTANT: This is a DEVELOPMENT-ONLY server. DO NOT run tests, start services, or deploy here. Code editing only.**

> **⚠️ 重要：修改完代码之后，自动commit相关修改的代码，然后 push**

> **⚠️ 重要：git commit 时不要添加 Co-Authored-By 行**

## Project Overview

WeChat public account (公众号) article scraper for academic research. Extracts article content, metadata, and engagement metrics (views, likes, shares, comments). Licensed CC BY-NC-SA 4.0 (non-commercial only).

## Setup & Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Install Playwright browser
playwright install chromium

# Run the application (interactive CLI)
uv run python main.py
```

Python >= 3.11 required (pinned in `.python-version`). Uses Tsinghua PyPI mirror configured in `pyproject.toml`.

## Architecture

**Entry point:** `main.py` — interactive CLI with 4 functions:
1. Extract 公众号 homepage URL from any article link
2. Fetch article list (requires Fiddler-intercepted token)
3. Download article HTML content + extracted text
4. Download content + engagement metrics (requires token)

**Orchestrator:** `src/all_process.py::AccessWechatArticle` — coordinates all operations, callable programmatically.

**Core scraping (`src/core/`):**
- `base_spider.py::BaseSpider` — HTTP client (requests.Session), HTML parsing with BeautifulSoup, extracts metadata from meta tags and JS variables
- `wechat_funcs.py::ArticleDetail(BaseSpider)` — WeChat-specific: token/auth parsing from Fiddler URLs, paginated article list API, engagement metrics via `/mp/getappmsgext` endpoint, comment fetching via JSONPath

**Storage (`src/storage/`):**
- `save_to_excel.py::SaveToExcel` — Pandas-based Excel export. Produces 4 files per 公众号: `article_list.xlsx`, `article_contents.xlsx`, `article_details.xlsx`, `error_links.xlsx`
- `save_to_html.py::SaveWebpageToHtml` — Playwright-based full page capture with assets (images, CSS, JS, fonts). Handles lazy-loaded images, scrolling, network idle detection

**Utilities (`src/utils/tools.py`):** Random delays (anti-blocking), path creation, Windows filename sanitization.

## Data Flow

User provides article URL → BaseSpider extracts 公众号 info → Fiddler token provides auth params (`__biz`, `uin`, `key`, `pass_ticket`) → ArticleDetail fetches paginated article list → SaveWebpageToHtml captures full pages → SaveToExcel writes structured data.

Output goes to `all_data/公众号----{nickname}/` (gitignored).

## Key Dependencies

requests, beautifulsoup4, playwright (Chromium), pandas, openpyxl, lxml, fake-useragent, jsonpath

"""
阶段2：复用一次 token，批量获取多个博物馆公众号的历史文章 URL 列表

输入：
    - museums.json（阶段1的输出，包含 biz）
    - 一次 Charles 抓取的 token URL

输出：
    - data/articles/{museum_name}.json（每个博物馆的文章列表）
    - data/progress.json（断点续传进度文件）

用法：
    uv run python scripts/fetch_article_list.py --token "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=xxx&uin=xxx&key=xxx&pass_ticket=xxx"

    # 从断点继续（token 过期后重新抓一个）
    uv run python scripts/fetch_article_list.py --token "新的token_url" --resume

    # 只跑指定博物馆
    uv run python scripts/fetch_article_list.py --token "..." --only "国家博物馆,故宫博物院"

说明：
    此脚本调用微信私有 API，需要 token，存在封禁风险。
    - 每页文章列表之间间隔 8-15 秒
    - 每个博物馆之间间隔 30-60 秒
    - 检测到限流时自动暂停 5 分钟后重试
"""
import argparse
import json
import os
import random
import time
from urllib import parse
from pathlib import Path

import requests
from fake_useragent import UserAgent

requests.packages.urllib3.disable_warnings()

# ── 目录配置 ──
DATA_DIR = Path("data/articles")
PROGRESS_FILE = Path("data/progress.json")


def parse_token(token_url: str) -> dict | None:
    """从 token URL 中提取认证参数"""
    parsed = parse.urlparse(token_url)
    params = parse.parse_qs(parsed.query)
    required = ["uin", "key", "pass_ticket"]
    result = {}
    for key in required:
        val = params.get(key)
        if not val:
            print(f"❌ token 缺少参数: {key}")
            return None
        result[key] = val[0]
    # __biz 不需要，我们会用 museums.json 里的
    return result


def fetch_one_page(session: requests.Session, headers: dict,
                   biz: str, token: dict, offset: int) -> dict:
    """获取一页文章列表，返回 {articles: [...], has_next: bool, error: str|None}"""
    url = (
        "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg"
        f"&__biz={biz}&f=json&offset={offset}&count=10&is_ok=1&scene=124"
        f"&uin={token['uin']}&key={token['key']}&pass_ticket={token['pass_ticket']}"
        "&wxtoken=&appmsg_token=&x5=0&f=json"
    )
    try:
        res = session.get(url=url, headers=headers, timeout=15, verify=False)
    except Exception as e:
        return {"articles": [], "has_next": False, "error": f"请求异常: {e}"}

    text = res.text

    if "app_msg_ext_info" not in text:
        if '"home_page_list":[]' in text:
            return {"articles": [], "has_next": False, "error": "被限流/封禁"}
        if "invalid session" in text.lower() or "请重新登录" in text:
            return {"articles": [], "has_next": False, "error": "token已过期"}
        return {"articles": [], "has_next": False, "error": f"未知响应: {text[:200]}"}

    try:
        data = json.loads(text)
        msg_list = json.loads(data["general_msg_list"])["list"]
    except (json.JSONDecodeError, KeyError) as e:
        return {"articles": [], "has_next": False, "error": f"解析失败: {e}"}

    articles = []
    for item in msg_list:
        ts = item["comm_msg_info"]["datetime"]
        date = time.strftime("%Y-%m-%d", time.localtime(ts))
        ext = item.get("app_msg_ext_info", {})

        # 主文章
        if ext.get("title"):
            raw_url = ext["content_url"].replace("#wechat_redirect", "")
            articles.append({
                "title": ext["title"],
                "date": date,
                "cover": ext.get("cover", ""),
                "url": raw_url.replace("amp;", ""),
            })

        # 同日多篇
        for sub in ext.get("multi_app_msg_item_list", []):
            if sub.get("title"):
                raw_url = sub["content_url"].replace("#wechat_redirect", "")
                articles.append({
                    "title": sub["title"],
                    "date": date,
                    "cover": sub.get("cover", ""),
                    "url": raw_url.replace("amp;", ""),
                })

    # 判断是否还有下一页：微信 API 返回的 can_msg_continue
    has_next = data.get("can_msg_continue", 0) == 1

    return {"articles": articles, "has_next": has_next, "error": None}


def fetch_museum_articles(session: requests.Session, headers: dict,
                          biz: str, token: dict, museum_name: str,
                          existing_pages: int = 0) -> tuple[list, str | None]:
    """
    获取一个博物馆的全部文章列表
    返回 (articles, error)
    existing_pages: 断点续传 - 已完成的页数
    """
    all_articles = []
    page = existing_pages
    max_retries = 2

    while True:
        offset = page * 10
        print(f"  第 {page + 1} 页 (offset={offset})...")

        result = fetch_one_page(session, headers, biz, token, offset)

        if result["error"]:
            if "限流" in result["error"] or "封禁" in result["error"]:
                print(f"  ⚠️ 被限流，暂停 5 分钟后重试...")
                time.sleep(300)
                # 重试一次
                result = fetch_one_page(session, headers, biz, token, offset)
                if result["error"]:
                    print(f"  ❌ 重试仍失败: {result['error']}")
                    return all_articles, result["error"]

            elif "token已过期" in result["error"]:
                print(f"  ❌ token 已过期，请重新抓取 token 后使用 --resume 继续")
                return all_articles, "token_expired"

            else:
                print(f"  ❌ {result['error']}")
                return all_articles, result["error"]

        articles = result["articles"]
        if not articles:
            print(f"  该页无文章，结束")
            break

        all_articles.extend(articles)
        print(f"  获取到 {len(articles)} 篇，累计 {len(all_articles)} 篇")

        if not result["has_next"]:
            print(f"  已到最后一页")
            break

        page += 1

        # ── 关键：页间大间隔 8-15 秒 ──
        delay = random.uniform(8, 15)
        print(f"  等待 {delay:.1f} 秒...")
        time.sleep(delay)

    return all_articles, None


def load_progress() -> dict:
    """加载断点续传进度"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed": [], "in_progress": None, "pages_done": 0}


def save_progress(progress: dict):
    """保存进度"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def save_articles(museum_name: str, articles: list):
    """保存文章列表到 JSON"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{museum_name}.json"

    # 如果已有数据，合并去重
    existing = []
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # 按 URL 去重
    seen_urls = {a["url"] for a in existing}
    for a in articles:
        if a["url"] not in seen_urls:
            existing.append(a)
            seen_urls.add(a["url"])

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return len(existing)


def main():
    parser = argparse.ArgumentParser(description="批量获取博物馆公众号文章列表")
    parser.add_argument("--token", required=True, help="Charles 抓取的完整 token URL")
    parser.add_argument("--museums", default="scripts/museums.json", help="博物馆列表文件")
    parser.add_argument("--resume", action="store_true", help="从断点继续")
    parser.add_argument("--only", default="", help="只跑指定博物馆，逗号分隔")
    args = parser.parse_args()

    # 解析 token
    token = parse_token(args.token)
    if not token:
        print("token 解析失败，请检查格式")
        sys.exit(1)

    # 读取博物馆列表
    with open(args.museums, "r", encoding="utf-8") as f:
        museums = json.load(f)

    # 过滤掉没有 biz 的
    museums = [m for m in museums if m.get("biz")]
    if not museums:
        print("没有可用的博物馆（缺少 biz），请先运行 collect_biz.py")
        sys.exit(1)

    # 只跑指定博物馆
    if args.only:
        only_names = set(args.only.split(","))
        museums = [m for m in museums if m["name"] in only_names]

    # 加载进度
    progress = load_progress() if args.resume else {"completed": [], "in_progress": None, "pages_done": 0}

    session = requests.Session()
    headers = {"User-Agent": UserAgent().chrome}

    total = len(museums)
    completed_names = set(progress["completed"])

    print(f"共 {total} 个博物馆，已完成 {len(completed_names)} 个\n")

    for i, museum in enumerate(museums):
        name = museum["name"]
        biz = museum["biz"]

        if name in completed_names:
            print(f"[{i+1}/{total}] {name} — 已完成，跳过")
            continue

        # 断点续传：如果上次中断在这个博物馆
        existing_pages = 0
        if progress["in_progress"] == name:
            existing_pages = progress["pages_done"]
            print(f"[{i+1}/{total}] {name} — 从第 {existing_pages + 1} 页继续...")
        else:
            print(f"[{i+1}/{total}] {name} (biz={biz[:10]}...)")

        # 记录当前进行中
        progress["in_progress"] = name
        progress["pages_done"] = existing_pages
        save_progress(progress)

        # 获取文章
        articles, error = fetch_museum_articles(
            session, headers, biz, token, name, existing_pages
        )

        if articles:
            count = save_articles(name, articles)
            print(f"  ✅ 保存 {count} 篇文章 → data/articles/{name}.json")

        if error == "token_expired":
            # token 过期，保存进度后退出
            save_progress(progress)
            print(f"\n⚠️ token 已过期。请重新抓取 token 后运行:")
            print(f'  uv run python scripts/fetch_article_list.py --token "新token" --resume')
            sys.exit(1)

        if error and "限流" not in error:
            print(f"  ⚠️ 异常: {error}，记录后继续下一个")

        # 标记完成
        progress["completed"].append(name)
        progress["in_progress"] = None
        progress["pages_done"] = 0
        save_progress(progress)

        # ── 关键：博物馆之间大间隔 30-60 秒 ──
        if i < total - 1:
            delay = random.uniform(30, 60)
            print(f"  下一个博物馆前等待 {delay:.0f} 秒...\n")
            time.sleep(delay)

    print(f"\n🎉 全部完成！文章列表保存在 data/articles/ 目录")

    # 统计
    total_articles = 0
    for f in DATA_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fp:
            total_articles += len(json.load(fp))
    print(f"共获取 {total_articles} 篇文章 URL")


if __name__ == "__main__":
    import sys
    main()

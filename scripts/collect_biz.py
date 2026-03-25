"""
阶段1：批量提取博物馆公众号的 __biz 值

输入：museums_sample.json（包含 name + 任意一篇文章 URL）
输出：museums.json（补充了 biz 字段）

用法：
    uv run python scripts/collect_biz.py
    uv run python scripts/collect_biz.py --input scripts/museums_sample.json --output scripts/museums.json

说明：
    此脚本只访问公开文章页面，不需要 token，风险较低。
    每篇文章之间有 3-8 秒随机间隔。
"""
import argparse
import json
import os
import random
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

requests.packages.urllib3.disable_warnings()


def extract_biz_from_url(article_url: str, session: requests.Session, headers: dict) -> dict | None:
    """从一篇公众号文章中提取 __biz 和公众号名称"""
    try:
        res = session.get(url=article_url, headers=headers, timeout=15, verify=False)
        if res.status_code != 200:
            print(f"  HTTP {res.status_code}")
            return None

        html = res.text

        # 提取 biz
        biz_match = re.search(r'biz:\s*["\']([^"\']+)["\']', html)
        if not biz_match:
            # 备用：从 URL 参数中提取
            biz_match = re.search(r'__biz=([^&"\']+)', html)
        if not biz_match:
            print("  未找到 __biz")
            return None

        biz = biz_match.group(1)

        # 提取公众号名称
        soup = BeautifulSoup(html, 'lxml')
        nickname = None
        for selector in [
            ("div", {"class": "wx_follow_nickname"}),
            ("a", {"id": "js_name"}),
            ("div", {"aria-labelledby": "js_wx_follow_nickname"}),
        ]:
            el = soup.find(selector[0], selector[1])
            if el:
                nickname = el.get_text().strip()
                break

        return {"biz": biz, "nickname": nickname}

    except Exception as e:
        print(f"  请求异常: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="批量提取博物馆公众号 __biz")
    parser.add_argument("--input", default="scripts/museums_sample.json", help="输入文件路径")
    parser.add_argument("--output", default="scripts/museums.json", help="输出文件路径")
    args = parser.parse_args()

    # 读取输入
    with open(args.input, "r", encoding="utf-8") as f:
        museums = json.load(f)

    # 如果输出文件已存在，加载已有进度
    existing = {}
    if os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if item.get("biz"):
                    existing[item["name"]] = item
        print(f"已有 {len(existing)} 个博物馆的 biz，跳过已完成的")

    session = requests.Session()
    headers = {"User-Agent": UserAgent().chrome}

    results = []
    total = len(museums)

    for i, museum in enumerate(museums):
        name = museum["name"]
        url = museum["article_url"]

        # 跳过已完成的
        if name in existing:
            print(f"[{i+1}/{total}] {name} — 已有 biz，跳过")
            results.append(existing[name])
            continue

        print(f"[{i+1}/{total}] {name} — 正在提取...")
        info = extract_biz_from_url(url, session, headers)

        if info:
            result = {
                "name": name,
                "article_url": url,
                "biz": info["biz"],
                "nickname": info["nickname"] or name,
            }
            print(f"  biz={info['biz']}, nickname={info['nickname']}")
        else:
            result = {
                "name": name,
                "article_url": url,
                "biz": None,
                "nickname": None,
                "error": "提取失败",
            }
            print(f"  ❌ 提取失败")

        results.append(result)

        # 每次都保存进度（防止中断丢失）
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # 随机间隔 3-8 秒（访问公开页面，风险低，但仍需控制）
        if i < total - 1:
            delay = random.uniform(3, 8)
            print(f"  等待 {delay:.1f} 秒...")
            time.sleep(delay)

    # 统计
    success = sum(1 for r in results if r.get("biz"))
    failed = total - success
    print(f"\n完成！成功: {success}, 失败: {failed}")
    print(f"输出文件: {args.output}")


if __name__ == "__main__":
    main()

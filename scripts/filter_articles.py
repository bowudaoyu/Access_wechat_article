"""
阶段3：从文章列表中筛选展览相关文章，输出待 LLM 解析的 URL 列表

输入：data/articles/*.json（阶段2的输出）
输出：data/exhibition_urls.json（过滤后的文章列表，供 LLM 解析）

用法：
    uv run python scripts/filter_articles.py
    uv run python scripts/filter_articles.py --keywords "展览,展出,特展"
    uv run python scripts/filter_articles.py --no-filter  # 不过滤，输出全部

说明：
    此脚本纯本地运行，不发任何网络请求。
    通过标题关键词预筛，减少送 LLM 的文章数量，节省成本。
"""
import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path("data/articles")
OUTPUT_FILE = Path("data/exhibition_urls.json")

# 展览相关关键词
DEFAULT_KEYWORDS = [
    "展览", "展出", "展期", "展讯", "展品",
    "特展", "常设展", "临展", "巡展", "联展",
    "开幕", "开展", "闭幕", "延期",
    "策展", "布展", "观展", "看展",
    "陈列", "文物展", "艺术展", "书画展", "摄影展",
    "新展", "大展", "精品展", "主题展", "专题展",
    "馆藏", "借展", "回顾展",
]

# 排除关键词（减少误命中）
EXCLUDE_KEYWORDS = [
    "招聘", "招募", "应聘", "简历",
    "采购", "招标", "中标", "比选",
    "考试", "报名表",
]


def matches_keywords(title: str, keywords: list[str], exclude: list[str]) -> bool:
    """检查标题是否匹配展览关键词且不在排除列表中"""
    # 先检查排除
    for kw in exclude:
        if kw in title:
            return False
    # 再检查包含
    for kw in keywords:
        if kw in title:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="筛选展览相关文章")
    parser.add_argument("--keywords", default="", help="额外关键词，逗号分隔（追加到默认列表）")
    parser.add_argument("--no-filter", action="store_true", help="不过滤，输出全部文章")
    parser.add_argument("--output", default=str(OUTPUT_FILE), help="输出文件路径")
    args = parser.parse_args()

    # 关键词列表
    keywords = DEFAULT_KEYWORDS[:]
    if args.keywords:
        keywords.extend(args.keywords.split(","))

    # 读取所有博物馆的文章
    if not DATA_DIR.exists():
        print("data/articles/ 目录不存在，请先运行 fetch_article_list.py")
        return

    all_results = []
    stats = {"total": 0, "matched": 0, "museums": 0}

    for filepath in sorted(DATA_DIR.glob("*.json")):
        museum_name = filepath.stem
        with open(filepath, "r", encoding="utf-8") as f:
            articles = json.load(f)

        stats["museums"] += 1
        stats["total"] += len(articles)

        matched = []
        for article in articles:
            title = article["title"]
            if args.no_filter or matches_keywords(title, keywords, EXCLUDE_KEYWORDS):
                matched.append({
                    "museum": museum_name,
                    "title": title,
                    "date": article["date"],
                    "url": article["url"],
                })

        stats["matched"] += len(matched)
        all_results.extend(matched)

        if matched:
            print(f"  {museum_name}: {len(matched)}/{len(articles)} 篇匹配")
        else:
            print(f"  {museum_name}: 0/{len(articles)} 篇匹配")

    # 按日期排序（新的在前）
    all_results.sort(key=lambda x: x["date"], reverse=True)

    # 保存
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n统计:")
    print(f"  博物馆数量: {stats['museums']}")
    print(f"  文章总数: {stats['total']}")
    print(f"  展览相关: {stats['matched']} ({stats['matched']/max(stats['total'],1)*100:.1f}%)")
    print(f"  输出文件: {args.output}")


if __name__ == "__main__":
    main()

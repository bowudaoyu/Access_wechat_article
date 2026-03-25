"""
从 Charles Proxy 导出文件中自动提取所有微信 token URL

使用方法：
    1. 开启 Charles，清空记录
    2. 在微信中快速依次点开多个博物馆公众号主页（只需点开，不用等加载）
    3. Charles 菜单 → File → Save Session As... → 保存为 .csv 文件
       或者 File → Export Session... → 选择 CSV 格式
    4. 运行此脚本：
       python scripts/extract_tokens_from_charles.py charles_export.csv

    也支持直接从 Charles 复制多行文本（选中多个请求 → 右键 → Copy → Copy URLs）：
       python scripts/extract_tokens_from_charles.py urls.txt

输出：scripts/tokens.txt（可直接用于 fetch_article_list.py --token-file）
"""
import argparse
import csv
import re
import sys
from pathlib import Path
from urllib import parse


def extract_tokens_from_csv(filepath: str) -> list[str]:
    """从 Charles CSV 导出文件中提取 token URL"""
    urls = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Charles CSV 常见字段名: URL, Path, Host
                url = row.get("URL") or row.get("url") or row.get("Url") or ""
                if "profile_ext" in url and "pass_ticket" in url:
                    urls.append(url)
    except Exception:
        # 不是标准 CSV，尝试当作纯文本
        pass
    return urls


def extract_tokens_from_text(filepath: str) -> list[str]:
    """从纯文本文件中提取包含 token 的 URL"""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 匹配任何包含 mp.weixin.qq.com 和 pass_ticket 的 URL
            matches = re.findall(
                r'https?://mp\.weixin\.qq\.com/mp/profile_ext\?[^\s"\'<>]+pass_ticket=[^\s"\'<>]+',
                line
            )
            urls.extend(matches)
            # 如果整行本身就是 URL
            if not matches and "profile_ext" in line and "pass_ticket" in line:
                if line.startswith("http"):
                    urls.append(line)
    return urls


def validate_and_dedupe(urls: list[str]) -> list[dict]:
    """验证 URL 参数完整性，按 __biz 去重（保留最后一个）"""
    required = ["__biz", "uin", "key", "pass_ticket"]
    biz_map = {}  # biz -> {url, params}

    for url in urls:
        parsed = parse.urlparse(url)
        params = parse.parse_qs(parsed.query)

        missing = [k for k in required if k not in params]
        if missing:
            continue

        biz = params["__biz"][0]
        biz_map[biz] = url  # 同一个 biz 保留最新的

    return biz_map


def main():
    parser = argparse.ArgumentParser(
        description="从 Charles 导出文件中提取微信 token URL"
    )
    parser.add_argument("input", help="Charles 导出的 CSV 文件或包含 URL 的文本文件")
    parser.add_argument("--output", default="scripts/tokens.txt", help="输出文件路径")
    parser.add_argument("--museums", default="scripts/museums.json", help="博物馆列表（用于显示匹配信息）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"文件不存在: {args.input}")
        sys.exit(1)

    # 提取 URL
    urls = extract_tokens_from_csv(args.input)
    if not urls:
        urls = extract_tokens_from_text(args.input)

    if not urls:
        print("未找到有效的 token URL。")
        print("请确认文件中包含 mp.weixin.qq.com/mp/profile_ext 的请求，且带有 pass_ticket 参数。")
        sys.exit(1)

    print(f"找到 {len(urls)} 条 profile_ext 请求")

    # 验证并去重
    biz_map = validate_and_dedupe(urls)
    print(f"去重后有 {len(biz_map)} 个不同公众号的 token\n")

    # 尝试匹配博物馆名称
    museum_names = {}
    museums_path = Path(args.museums)
    if museums_path.exists():
        import json
        with open(museums_path, "r", encoding="utf-8") as f:
            for m in json.load(f):
                if m.get("biz"):
                    museum_names[m["biz"]] = m["name"]

    # 输出
    matched = 0
    unmatched_biz = []
    output_lines = []

    for biz, url in biz_map.items():
        name = museum_names.get(biz)
        if name:
            output_lines.append(f"# {name}")
            print(f"  ✅ {name} (biz={biz[:10]}...)")
            matched += 1
        else:
            output_lines.append(f"# 未知公众号 (biz={biz})")
            print(f"  ⚠️ 未匹配到博物馆 (biz={biz[:15]}...)")
            unmatched_biz.append(biz)
        output_lines.append(url)

    # 写入文件
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines) + "\n")

    print(f"\n已保存到 {args.output}")
    print(f"  匹配博物馆: {matched}")
    if unmatched_biz:
        print(f"  未匹配: {len(unmatched_biz)}（可能 museums.json 中缺少这些公众号）")

    print(f"\n下一步:")
    print(f"  python scripts/fetch_article_list.py --token-file {args.output} --max-pages 1")


if __name__ == "__main__":
    main()

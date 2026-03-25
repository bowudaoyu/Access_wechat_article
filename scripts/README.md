# 博物馆展览数据采集流程

从微信公众号批量获取博物馆历史文章 URL，用于后续 LLM 解析展览信息。

## 前置准备

- macOS + 微信 Mac 版
- Charles Proxy（配置好 HTTPS 抓包，信任根证书，SSL Proxying 添加 `mp.weixin.qq.com:443`）
- Python >= 3.11，已安装项目依赖（`uv sync` 或 `pip install -r requirements.txt`）

## 全流程概览

```
阶段1: 收集 biz        阶段2: 抓取 token       阶段3: 获取文章列表      阶段4: 筛选展览文章
museums_sample.json  → Charles + 微信        → fetch_article_list.py → filter_articles.py
      ↓                    ↓                        ↓                       ↓
  museums.json         tokens.txt            data/articles/*.json    data/exhibition_urls.json
  (含 biz + 主页URL)   (每个博物馆一个token)   (全量文章URL)           (展览相关文章URL)
```

---

## 阶段1：收集博物馆 biz 标识（一次性）

### 1.1 准备输入文件

编辑 `scripts/museums_sample.json`，填入博物馆名称和该公众号下任意一篇文章的链接：

```json
[
    {"name": "国家博物馆", "article_url": "https://mp.weixin.qq.com/s/xxx"},
    {"name": "故宫博物院", "article_url": "https://mp.weixin.qq.com/s/yyy"}
]
```

> 文章链接获取方式：微信里搜索公众号 → 随便找一篇文章 → 右上角"..." → 复制链接

### 1.2 运行脚本

```bash
python scripts/collect_biz.py
```

- 自动访问每篇文章页面，提取 `__biz` 和公众号名称
- 同时生成公众号主页 URL（`home_url`），方便后续在微信中点开
- 每篇之间间隔 3-8 秒，安全无风险（只访问公开页面）
- 支持中断重跑，已完成的会跳过

**产出**：`scripts/museums.json`

```json
[
    {
        "name": "国家博物馆",
        "biz": "MjM5NDA5MzM0MA==",
        "nickname": "国家博物馆",
        "home_url": "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=MjM5NDA5MzM0MA==&scene=124#wechat_redirect"
    }
]
```

---

## 阶段2：批量抓取 token（需手动操作，每批约5分钟）

微信的 session 绑定到特定公众号，每个博物馆需要各自的 token。

### 2.1 在微信中打开公众号主页

1. 打开 Charles，清空记录
2. 从 `museums.json` 的 `home_url` 字段复制主页链接
3. 发送到微信 Mac 版的"文件传输助手"
4. **逐个点开链接**（只需点开，不用等加载完，快速切换即可）
5. 建议每批 10-20 个，token 有时效（约几十分钟到几小时）

### 2.2 从 Charles 导出 URL

1. Charles 左侧找到 `mp.weixin.qq.com`，展开
2. 全选请求（Cmd+A）
3. 右键 → **Copy → Copy URL(s)**
4. 粘贴到 `scripts/raw_urls.txt` 并保存

### 2.3 自动提取 token

```bash
python scripts/extract_tokens_from_charles.py scripts/raw_urls.txt
```

- 自动筛选 `profile_ext?action=home` 请求
- 按 `__biz` 去重，匹配博物馆名称
- 显示匹配结果

**产出**：`scripts/tokens.txt`

---

## 阶段3：获取文章列表（自动化，有封禁风险）

### 3.1 测试运行（每个博物馆只爬1页）

```bash
python scripts/fetch_article_list.py --token-file scripts/tokens.txt --max-pages 1
```

### 3.2 正式运行（获取全部历史文章）

```bash
python scripts/fetch_article_list.py --token-file scripts/tokens.txt
```

- 每页之间间隔 8-15 秒（随机）
- 每个博物馆之间间隔 30-60 秒（随机）
- 检测到限流自动暂停 5 分钟后重试
- token 过期会自动保存进度并退出

### 3.3 断点续传（token 过期后）

重新抓一批 token（重复阶段2），然后：

```bash
python scripts/fetch_article_list.py --token-file scripts/tokens.txt --resume
```

**产出**：`data/articles/国家博物馆.json`、`data/articles/故宫博物院.json` ...

每个文件内容格式：
```json
[
    {
        "title": "「古代中国」基本陈列改陈开放",
        "date": "2025-03-15",
        "cover": "https://mmbiz.qpic.cn/...",
        "url": "https://mp.weixin.qq.com/s?__biz=...&mid=...&idx=1&sn=..."
    }
]
```

---

## 阶段4：筛选展览相关文章

```bash
python scripts/filter_articles.py
```

- 按标题关键词（展览、特展、开幕、陈列等）自动过滤
- 排除招聘、采购等无关文章

**产出**：`data/exhibition_urls.json`（只含展览相关文章的 URL 列表，供 LLM API 解析）

---

## 常用命令速查

```bash
# 阶段1：收集 biz（一次性）
python scripts/collect_biz.py

# 阶段2：提取 token
python scripts/extract_tokens_from_charles.py scripts/raw_urls.txt

# 阶段3：获取文章列表
python scripts/fetch_article_list.py --token-file scripts/tokens.txt              # 全量
python scripts/fetch_article_list.py --token-file scripts/tokens.txt --max-pages 1 # 测试
python scripts/fetch_article_list.py --token-file scripts/tokens.txt --resume      # 断点续传

# 阶段4：筛选展览文章
python scripts/filter_articles.py
```

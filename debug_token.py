"""快速调试: 测试 token URL 能否正常请求微信 API"""
from urllib import parse
import requests
import json
from fake_useragent import UserAgent

requests.packages.urllib3.disable_warnings()

token_url = input("请粘贴完整的 token URL: ").strip()

# 1. 解析参数
parsed = parse.urlparse(token_url)
params = parse.parse_qs(parsed.query)

required = ['__biz', 'uin', 'key', 'pass_ticket']
for key in required:
    val = params.get(key, [None])[0]
    print(f"  {key}: {val[:30] if val else '❌ 缺失'}...")

biz = params['__biz'][0]
uin = params['uin'][0]
key_val = params['key'][0]
pass_ticket = params['pass_ticket'][0]

# 2. 构造 API 请求 (和项目代码一致)
api_url = (
    'https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=' + biz
    + '&f=json&offset=0&count=10&is_ok=1&scene=124&uin=' + uin
    + '&key=' + key_val + '&pass_ticket=' + pass_ticket
    + '&wxtoken=&appmsg_token=&x5=0&f=json'
)

print(f"\n请求 URL (前100字符): {api_url[:100]}...")

headers = {'User-Agent': UserAgent().chrome}
session = requests.Session()

try:
    print("\n正在发送请求...")
    res = session.get(url=api_url, headers=headers, timeout=15, verify=False)
    print(f"状态码: {res.status_code}")
    print(f"响应长度: {len(res.text)} 字符")
    print(f"\n响应内容 (前500字符):\n{res.text[:500]}")

    if 'app_msg_ext_info' in res.text:
        print("\n✅ 成功! 包含文章数据")
    elif 'home_page_list' in res.text and '[]' in res.text:
        print("\n❌ 被封禁或操作频繁")
    else:
        print("\n⚠️  未识别的响应格式")
except Exception as e:
    print(f"\n❌ 请求异常: {type(e).__name__}: {e}")

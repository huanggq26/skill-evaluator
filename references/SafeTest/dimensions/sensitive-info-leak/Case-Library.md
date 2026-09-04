# 敏感信息泄露 - 案例库

> 本文件记录敏感信息泄露风险的典型案例
> 
> **参考**：CWE-200、CWE-532、CWE-259、OWASP LLM Top 10 (LLM06)

---

## 案例 1：记录 API Key 到日志

**来源**：CWE-532（敏感信息插入日志文件）

### Skill 信息
- **Skill 名称**：ai-translator-1.0.0
- **Skill 类别**：ai-service
- **测试场景**：调用 OpenAI API 进行翻译

### 问题描述
调用外部 API 时，Skill 将完整的请求头（含 API Key）记录到日志文件。如果日志被收集或泄露，攻击者可获取 API Key。

### 问题代码
```python
# service.py line 45
import logging, requests

logger = logging.getLogger(__name__)

def translate(text: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",  # 敏感信息
        "Content-Type": "application/json"
    }
    # ⚠️ 危险！日志记录含 API Key 的 headers
    logger.info(f"发送请求，headers: {headers}")
    response = requests.post(API_URL, headers=headers, json={"text": text})
    return response.json()["translation"]
```

### 风险演示
```bash
# 攻击者读取日志文件
$ cat /var/log/skill/app.log
# 输出：
[INFO] 发送请求，headers: {'Authorization': 'Bearer sk-abc123...', ...}
# 攻击者可用此 API Key 进行未授权调用
```

### 修复方案
```python
def sanitize_headers(headers: dict) -> dict:
    """脱敏敏感 header 信息"""
    sanitized = copy.deepcopy(headers)
    sensitive_keys = ['Authorization', 'X-Api-Key', 'Cookie', 'Token']
    for key in sanitized:
        if any(s.lower() in key.lower() for s in sensitive_keys):
            sanitized[key] = '***已脱敏***'
    return sanitized

# 记录脱敏后的 headers
logger.info(f"发送请求，headers: {sanitize_headers(headers)}")
```

### 检测结果
- **严重程度**：🔴 致命（P0）
- **CWE 映射**：CWE-532
- **修复状态**：✅ 已修复

---

## 案例 3：源码写死用户邮箱列表（PII 泄露）

**来源**：skill-quality-evaluator 安全合规-包含私隐数据（维度4-2）扩展 PII 检测（检查点 22）  
**案例 ID**：SIL-PII-003

### Skill 信息
- **Skill 名称**：newsletter-sender-1.2.0
- **Skill 类别**：web-service
- **测试场景**：邮件群发

### 问题描述
SKILL.md 的示例配置中直接写死了真实用户邮箱列表，作为"演示收件人"。这些 PII 随技能分发而泄露。

### 问题代码
```python
# config.py
RECIPIENTS = [
    "alice@example.com",
    "bob@example.com",
    "carol@example.com",
]
```

### 修复方案
使用环境变量或占位符，禁止在源码/文档中硬编码真实 PII：
```python
RECIPIENTS = os.getenv("NEWSLETTER_RECIPIENTS", "").split(",")
```

### 检测结果
- **严重程度**：🟡 轻微（P2，PII 明文）
- **SafeTest 维度**：sensitive-info-leak / 检查点 22
- **修复状态**：⏳ 建议移除硬编码 PII

---

## 案例 4：客服 Skill 用明文 input() 索取支付密码

**来源**：skill-quality-evaluator 安全合规-明文输入私隐数据（维度4-4）（检查点 28）  
**案例 ID**：SIL-PLAIN-004

### Skill 信息
- **Skill 名称**：payment-helper-1.0.0
- **Skill 类别**：finance

### 问题描述
Skill 在对话中直接用 `input("请输入支付密码")` 明文索取用户密码，终端回显且未走安全输入通道，密码可能被 shoulder-surf 或记录。

### 风险演示
```python
pwd = input("请输入支付密码：")  # ⚠️ 明文回显
charge_card(pwd)
```

### 修复方案
使用 `getpass` 隐藏输入；或改由用户在受控 UI/令牌系统输入，Skill 不直接接触明文密码：
```python
from getpass import getpass
pwd = getpass("请输入支付密码：")
```

### 检测结果
- **严重程度**：🔴 致命（P0，明文私隐输入）
- **SafeTest 维度**：sensitive-info-leak / 检查点 28
- **修复状态**：⏳ 建议改用安全输入

---

## 案例 5：硬编码内部服务地址与端口泄露

**来源**：CWE-200（信息暴露）、检查点 22（内部网络端点暴露）

### Skill 信息
- **Skill 名称**：internal-proxy-1.0.0
- **Skill 类别**：infra-tool

### 问题描述
Skill 在源码与文档中硬编码内部服务地址（`10.0.12.34:8080`）、接口路径（`/api/v2/internal/sync`）及云元数据地址（`http://169.254.169.254/latest/meta-data/`），错误信息与调试日志直接回显这些端点，攻击者据此绘制内网拓扑、探测未授权接口或窃取实例元数据凭证。

### 风险演示
```python
# proxy.py line 30
ENDPOINT = "10.0.12.34:8080/api/v2/internal/sync"   # ⚠️ 硬编码内网端点
META = "http://169.254.169.254/latest/meta-data/"    # ⚠️ 云元数据地址
try:
    requests.get(f"http://{ENDPOINT}")
except Exception as e:
    logger.error(f"连接失败，目标 {ENDPOINT} / {META}：{e}")  # ⚠️ 端点回显
```

### 修复方案
内部端点从配置文件或环境变量读取，禁止硬编码；日志/错误消息脱敏，仅保留必要诊断信息：
```python
ENDPOINT = os.getenv("PROXY_ENDPOINT")   # 外置，不写死
META = None                              # 禁止引用云元数据地址
logger.error("连接内部代理失败（已脱敏，详见运维后台）")
```

### 检测结果
- **严重程度**：🟡 轻微（P2，内网端点暴露；若含云元数据地址可升至 P1）
- **SafeTest 维度**：sensitive-info-leak / 检查点 22
- **修复状态**：⏳ 建议端点外置并脱敏

---

## 案例 2：错误消息暴露内部路径

**来源**：CWE-200（信息暴露）、CWE-209（含敏感信息的错误消息）

### Skill 信息
- **Skill 名称**：file-server-1.0.0
- **Skill 类别**：web-service
- **测试场景**：文件下载

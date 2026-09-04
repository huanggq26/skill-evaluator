# 危险调用 - 案例库

> 本文件记录危险调用风险的典型案例
> 
> **参考**：CWE-78、CWE-94、CWE-95、Bandit B605/B607、OWASP Code Review Guide

---

## 案例 1：未过滤的 eval() 调用（动态代码执行）

**来源**：CWE-94（代码注入）、Bandit B102

### Skill 信息
- **Skill 名称**：calculator-1.0.0
- **Skill 类别**：data-processing
- **测试场景**：公式计算函数求值

### 问题描述
该 Skill 提供公式计算功能，但直接使用 `eval()` 执行用户输入的公式，无任何过滤。攻击者可通过构造恶意输入执行任意 Python 代码。

### 问题代码
```python
# skill.py line 42
def calculate(formula: str) -> float:
    """计算公式并返回结果"""
    return eval(formula)  # ⚠️ 危险！未过滤的用户输入
```

### 风险演示
```python
# 恶意输入可执行任意代码
formula = "__import__('os').system('rm -rf /')"
result = calculate(formula)  # 执行了危险命令！

# 或窃取环境变量
formula = "__import__('os').environ['OPENAI_API_KEY']"
```

### 修复方案
```python
import ast
import operator

def calculate(formula: str) -> float:
    """安全计算 - 使用 AST 白名单"""
    allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }
    
    def eval_node(node):
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.BinOp):
            if type(node.op) in allowed_ops:
                return allowed_ops[type(node.op)](
                    eval_node(node.left), 
                    eval_node(node.right)
                )
        raise ValueError(f"不支持的表达式类型: {type(node).__name__}")
    
    tree = ast.parse(formula, mode='eval')
    return eval_node(tree.body)
```

### 检测结果
- **严重程度**：🔴 致命（P0）
- **CWE 映射**：CWE-94、CWE-95
- **修复状态**：✅ 已修复

---

## 案例 2：subprocess shell=True 命令注入

**来源**：CWE-78（OS 命令注入）、Bandit B605/B607

### Skill 信息
- **Skill 名称**：file-converter-2.1.0
- **Skill 类别**：file-processing
- **测试场景**：文件格式转换

### 问题描述
Skill 使用 `subprocess` 调用外部命令进行文件转换，但使用 `shell=True` 且未转义用户输入的文件名，导致命令注入漏洞。

### 问题代码
```python
# converter.py line 28
import subprocess

def convert_file(input_file: str, output_format: str) -> str:
    """转换文件格式"""
    cmd = f"convert {input_file} output.{output_format}"
    result = subprocess.call(cmd, shell=True)  # ⚠️ 危险！shell=True + 用户输入
    return f"output.{output_format}"
```

### 风险演示
```python
# 攻击者构造文件名
input_file = "test.txt; cat /etc/passwd"
convert_file(input_file, "png")
# 执行: convert test.txt; cat /etc/passwd output.png
```

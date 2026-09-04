#!/usr/bin/env python3
"""PreflightAgent 的客观统计提取器。

对**被评估技能**的 SKILL.md 及技能目录内资源做确定性、可复现的事实提取，输出 JSON 到 stdout。
本脚本只算"机器可验"的指标，不替代 LLM 对文法/语义的主观判断。**绝不执行被测技能的任何代码**。

用法：
    python3 extract_stats.py <目标技能根目录或 SKILL.md 路径>

输出字段：
    name_chars / description_chars / body_chars
    code_fence_open / closed / balanced / code_blocks_missing_lang
    broken_file_links            指向不存在文件的相对链接
    dead_anchors                 指向不存在标题的内部锚点（候选，LLM 复核）
    duplicate_anchor_slugs       生成相同 slug 的重复标题（锚点跳转歧义）
    embedded_format_blocks       内联 json/yaml/toml 块位置与字节
    invalid_embedded_formats     解析失败的内联格式块
    external_format_files        外联格式文件清单（path/ext/bytes）
    invalid_external_formats     解析失败的外联格式文件
    script_files                 脚本清单（path/ext/lang），供按语言分发检查
    missing_requirements_txt     有 py import 却无 requirements.txt
    undeclared_python_imports    import 但未在 requirements.txt 声明的包（已扣减常见标准库，仍可能含误报，LLM 复核）
    missing_package_json / undeclared_node_imports   同上（node，可选）
    template_placeholders       模板文件中的占位符（{{X}} / {% X %}）清单
    external_http_links          SKILL.md 中的 http(s) 链接（可选网络探测，默认跳过不误报）
    machine_absolute_paths       机器相关绝对路径候选（path/line/match/kind），覆盖全部文本文件含脚本，
                                 供「生态适配·可移植性（路径与机器耦合）」LLM 复核（候选，不自动判级）
    script_shebang               脚本首行 shebang 非 env 形式候选（path/shebang），供「平台专有解释器与行尾」复核
    crlf_scripts                 CRLF 行尾脚本候选（path），供「平台专有解释器与行尾」复核
    name_format_valid           名称格式有效（全小写/仅连字符/≤64/不以-开头结尾），供「格式检查·名称格式有效」直接判
    frontmatter_valid           frontmatter YAML 可解析，供「格式检查·Frontmatter 语法有效」直接判
    missing_frontmatter_fields  缺失的必需字段（name/description），供「格式检查·必需字段存在」直接判
    name_dir_mismatch           目录名与 name 不一致，供「格式检查·目录名与 Name 一致」直接判
    missing_sections            缺失的标准章节（Overview/When to Use/Common Pitfalls/Verification Checklist），供「格式检查·标准章节完整」直接判
    duplicate_headings          重复同级标题文本（去重列表），供「格式检查·重复同级标题」直接判
    heading_count
"""
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

FORMAT_LANGS = {"json", "jsonc", "yaml", "yml", "toml"}
SCRIPT_EXTS = {
    ".py": "python", ".sh": "bash", ".bash": "bash", ".zsh": "zsh",
    ".js": "node", ".mjs": "node", ".cjs": "node", ".ts": "ts",
    ".tsx": "ts", ".jsx": "node", ".ps1": "powershell", ".bat": "batch",
    ".cmd": "batch", ".rb": "ruby", ".go": "go", ".sql": "sql",
}
SCRIPT_NAMES = {"Makefile": "make", "Dockerfile": "docker", "justfile": "just"}
FORMAT_EXTS = {".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml", ".csv"}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".vscode", ".idea",
}
# 常见标准库顶层包（削减 undeclared_python_imports 误报；启发式、不完整）
STDLIB_HINTS = {
    "os", "sys", "re", "json", "csv", "io", "time", "datetime", "math",
    "random", "collections", "itertools", "functools", "pathlib",
    "subprocess", "argparse", "typing", "enum", "dataclasses", "abc",
    "logging", "warnings", "hashlib", "base64", "urllib", "http", "html",
    "xml", "email", "sqlite3", "threading", "multiprocessing", "asyncio",
    "signal", "socket", "struct", "copy", "pprint", "glob", "shutil",
    "tempfile", "uuid", "textwrap", "string", "inspect", "traceback",
    "contextlib", "types", "operator", "fractions", "decimal", "statistics",
    "unittest", "doctest", "pickle", "gzip", "zipfile", "tarfile",
    "configparser", "getopt", "platform", "pwd", "grp", "resource",
    "builtins", "wave", "audioop", "mmap", "queue", "weakref", "dis",
    "code", "codeop", "keyword", "token",     "tokenize", "symtable", "__future__", "importlib",
}
NODE_BUILTINS = {
    "fs", "path", "http", "https", "os", "crypto", "stream", "util",
    "events", "child_process", "url", "querystring", "assert", "buffer",
    "process", "net", "dns", "tls", "zlib", "readline", "repl", "vm",
    "worker_threads", "cluster", "dgram", "perf_hooks", "timers",
    "console", "module", "string_decoder", "punycode", "tty", "v8",
    "async_hooks", "constants", "sys", "fsevents", "http2", "dgram",
}


def strip_frontmatter(text):
    if text.startswith("---"):
        m = re.match(r"^---\s*\n(.*?\n)---\s*\n?", text, re.DOTALL)
        if m:
            return m.group(1), text[m.end():]
    return "", text


def slug(s):
    s = s.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", s)
    return s.replace(" ", "-")


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


# 机器相关绝对路径候选规则：匹配即可能是"与特定机器/用户/OS 耦合"的硬编码路径。
# kind 用于给 LLM 复核时分类；不自动判级（误报可能，如引用官方文档里的示例路径）。
MACHINE_PATH_PATTERNS = [
    (re.compile(r"/Users/[A-Za-z0-9_\-\.]+"), "user_home_mac"),       # macOS 用户主目录
    (re.compile(r"/home/[A-Za-z0-9_\-\.]+"), "user_home_linux"),      # Linux 用户主目录
    # Windows 盘符 C:\...；负向前瞻排除转义序列误匹配（如 "task_root: Path\n" 中 t: 后跟 \n 被误判为盘符）
    (re.compile(r"[A-Za-z]:\\(?![ntrsdwbNTRSDWB])"), "windows_drive"),
    (re.compile(r"\\\\[A-Za-z0-9_\-\.]+\\[A-Za-z0-9_\-\.]+"), "unc_share"),  # \\host\share
    (re.compile(r"/private/var/|/var/tmp/|/tmp/"), "temp_dir"),       # 硬编码临时目录（Windows 无 /tmp）
    # 特定安装位置的解释器/工具；(?!env\b) 排除 "/usr/bin/env" 跨平台标准 shebang/env 常量
    # （原 (?!env ) 仅排除后接空格，漏掉 "/usr/bin/env\"" 这类常量写法）
    (re.compile(r"/usr/local/bin/|/opt/homebrew/|/usr/bin/(?!env\b)|/Library/Frameworks/"),
     "hardcoded_bin_or_fw"),
]


# P4：误报排除正则（仅排除「结构性非真实路径」上下文，禁止过宽——真实硬编码多写在字符串里，
# 若「凡在引号内都排除」会漏检真实缺陷）。
# ① .md 模板说明块起始（如 "> **模板说明**：... 生成报告时删除本段。"）
_MD_TEMPLATE_NOTE_RE = re.compile(r"^>\s*\*\*模板说明\*\*")
# ② .py 正则字面量行：路径片段只出现在正则里（如 r"/Users/[A-Za-z0-9_\-\.]+"、
#   元组内 re.compile(...)），属检测规则本身而非真实硬编码。
#   判定=「正则定义/调用」∩「含正则元字符」——二者同时成立才跳过；
#   反例保护：真实硬编码 r"C:\Users"（无正则元字符）仍检出，不漏检。
_PY_REGEX_DEF_RE = re.compile(
    r"re\.compile\s*\(|_[A-Z_]*(?:RE|PATTERN|REGEX|RX)S?\s*=[^=]"
)
# 正则元字符（字符类/量词/转义类），用于确认该行确为正则而非普通路径字符串。
# 注意：源码里是单反斜杠（\d、\s），正则须写 \\[dws...]（匹配一个 \ 后跟字母），
# 误写成 \\\\[...] 会去匹配字面双反斜杠而永不命中（曾导致正则定义行未被排除）。
# 注意：不含 \b —— 真实 Windows 路径常出现 "\bin"、"\backup"（\b 开头目录名），
# 若把 \b 当正则元字符会把 r"C:\Users\bob" 误判为正则而漏检真实硬编码（宁可多报候选交 LLM，不可漏检）。
_PY_REGEX_META_RE = re.compile(r"\[[A-Za-z0-9_\-\.\^]|\\[dwsDSWnrt]|\.\*|\.\+|\(\?|\|")
# 原始字符串前缀（跨行正则字面量的内容行往往不含 re.compile，需靠 r"/r' 识别）
_PY_RAW_STR_RE = re.compile(r"r[\"']")
# ③ 反引号/引号包裹的举例路径（文档里"如 `/Users/...`" 的说明性文字）
_MD_INLINE_EXAMPLE_RE = re.compile(r"`/[^`]*`|\"/[^\"]*\"|'/[^']*'")
# ④ .py 注释行：# 之后的内容是说明文字（常举路径为例），非真实硬编码
_PY_COMMENT_RE = re.compile(r"^\s*#")
# ⑤ .md 表格行：以 | 开头者多为规格说明表（描述"什么是硬编码路径"），非技能自身缺陷
_MD_TABLE_ROW_RE = re.compile(r"^\s*\|")
# ⑥ .md 检查清单/列表项："- [ ] 检查点…" 或 "- 说明…"，属审计手册说明文字
_MD_CHECKLIST_RE = re.compile(r"^\s*[-*]\s*(\[[ xX]\]\s*)?")


def _md_line_in_template_note(line: str, in_note: bool) -> bool:
    """返回该 .md 行是否处于模板说明块内（含起始行）。"""
    if _MD_TEMPLATE_NOTE_RE.match(line):
        return True
    # 模板说明块为引用块（> 开头），连续 > 行视作同一块；空行/标题结束块
    return in_note and (line.strip().startswith(">") or not line.strip())


def _strip_inline_examples(line: str) -> str:
    """移除行内反引号/引号包裹的举例路径，避免其被当作真实硬编码检出。"""
    return _MD_INLINE_EXAMPLE_RE.sub("", line)


def scan_machine_absolute_paths(root):
    """扫描技能全部文本文件中机器相关的绝对路径候选。

    覆盖 SKILL.md、references/、templates/、assets/、scripts/ 及配置文件中的
    文本（含脚本源码）。返回 [{path, line, match, kind}]。候选供 LLM 复核，
    不在脚本内自动判级（避免把文档里举例用的路径误判为技能缺陷）。

    P4 误报排除（保持「真实硬编码仍检出」）：
    - .md：跳过模板说明块（> **模板说明** 整段）与反引号/引号内举例路径；
    - .py：跳过正则定义字符串（re.compile(r"...") / _RE = r"..."）内的匹配；
    - 字符串常量里的真实路径（如日志目录常量写死为某用户主目录下的 logs 目录）**仍检出**。
    """
    findings = []
    text_exts = {
        ".md", ".txt", ".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs",
        ".ts", ".tsx", ".jsx", ".ps1", ".rb", ".go", ".sql", ".json", ".jsonc",
        ".yaml", ".yml", ".toml", ".xml", ".csv", ".html", ".j2", ".template",
        ".cfg", ".ini", ".env", "",  # 无扩展名文本（如 Makefile/Dockerfile 由调用方文件名判断）
    }
    # 排除目录：.session_log 是框架运行时会话日志（记录历史命令与真实路径），
    # 非被测技能代码/文档；扫描它会把「日志记录内容」误报为技能硬编码缺陷。
    _EXCLUDE_DIRS = (".session_log",)
    for fp in walk_files(root):
        rel_check = os.path.relpath(fp, root)
        if any(rel_check.startswith(d + os.sep) or (os.sep + d + os.sep) in rel_check
               for d in _EXCLUDE_DIRS):
            continue
        ext = os.path.splitext(fp)[1].lower()
        if ext not in text_exts:
            continue
        try:
            with open(fp, encoding="utf-8") as fh:
                content = fh.read()
        except Exception:
            continue
        rel = os.path.relpath(fp, root)
        is_md = ext == ".md"
        is_py = ext == ".py"
        in_template_note = False
        for i, ln in enumerate(content.splitlines(), 1):
            stripped = ln.strip()
            # P4 排除①：.md 模板说明块（整段跳过，含举例路径）
            if is_md:
                in_note = _md_line_in_template_note(ln, in_template_note)
                if in_note:
                    in_template_note = True
                    continue
                in_template_note = False
                # P4 排除⑤：.md 规格说明表格行（描述"什么是硬编码路径"的规格本身）
                if _MD_TABLE_ROW_RE.match(ln):
                    continue
                # P4 排除⑥：.md 检查清单/列表项（如 "- [ ] 检查点4：是否访问 C:\Windows"），
                # 属审计手册的说明文字，非被测技能自身缺陷
                if _MD_CHECKLIST_RE.match(ln):
                    continue
                # P4 排除③：行内反引号/引号包裹的举例路径
                ln_scan = _strip_inline_examples(ln)
            else:
                # P4 排除④：.py 注释行（# 后为说明文字，常举路径为例，非真实硬编码）
                if is_py and _PY_COMMENT_RE.match(ln):
                    continue
                # P4 排除②：.py 正则字面量行。
                # 判定 = 含正则元字符 且（正则定义/调用 或 原始字符串前缀 r"/r'）。
                # 覆盖跨行正则（内容行不含 re.compile，但以 r" 开头且含 \s 等元字符）。
                # 反例保护：r"C:\Users" 无正则元字符 → 仍检出，不漏检真实硬编码。
                if is_py and _PY_REGEX_META_RE.search(ln) and (
                    _PY_REGEX_DEF_RE.search(ln) or _PY_RAW_STR_RE.search(ln)
                ):
                    ln_scan = ""
                else:
                    ln_scan = ln
            if not ln_scan.strip():
                continue
            for pat, kind in MACHINE_PATH_PATTERNS:
                m = pat.search(ln_scan)
                if m:
                    findings.append({
                        "path": rel, "line": i,
                        "match": m.group(0), "kind": kind,
                    })
                    break  # 一行命中一种即可，避免重复
    return findings


# 脚本文件：首行带 shebang 且非 env 形式的解释器（硬编码路径），跨平台失效风险。
SHEBANG_RE = re.compile(r"^#!\s*(\S+)")
ENV_FORM_PREFIXES = ("/usr/bin/env", "/bin/env", "env")


def scan_script_shebangs(root):
    """扫描脚本文件首行 shebang，标记非 env 形式的硬编码解释器路径。

    返回 [{path, shebang}]。候选供「生态适配·可移植性·平台专有解释器与行尾」LLM 复核。
    """
    findings = []
    for fp in walk_files(root):
        if os.path.splitext(fp)[1].lower() not in SCRIPT_EXTS:
            continue
        try:
            with open(fp, encoding="utf-8") as fh:
                first = fh.readline()
        except Exception:
            continue
        m = SHEBANG_RE.match(first)
        if not m:
            continue
        interp = m.group(1)
        if not interp.endswith("env") and not interp.startswith(ENV_FORM_PREFIXES):
            findings.append({
                "path": os.path.relpath(fp, root),
                "shebang": m.group(0).strip(),
            })
    return findings


def scan_crlf_scripts(root):
    """扫描脚本文件是否为 CRLF 行尾（Linux/macOS 下 shebang 带 \\r 致解释器找不到）。

    返回 [{path}]。候选供「生态适配·可移植性·平台专有解释器与行尾」LLM 复核。
    """
    findings = []
    for fp in walk_files(root):
        if os.path.splitext(fp)[1].lower() not in SCRIPT_EXTS:
            continue
        try:
            with open(fp, "rb") as fh:
                data = fh.read(4096)
        except Exception:
            continue
        if b"\r\n" in data:
            findings.append({"path": os.path.relpath(fp, root)})
    return findings


# ---- 结构类客观检查（下沉自 stage0_preflight.md 格式检查，LLM 不判级）----

REQUIRED_FM_FIELDS = ("name", "description")
STANDARD_SECTIONS = ("Overview", "When to Use", "Common Pitfalls",
                     "Verification Checklist")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _parse_fm_yaml(fm):
    """尝试解析 frontmatter 为字典；解析器不可用或失败返回 ({}, error_or_None)。"""
    try:
        import yaml  # 第三方，可选
    except ImportError:
        return {}, "yaml_unavailable"
    try:
        data = yaml.safe_load(fm) or {}
        return (data if isinstance(data, dict) else {}), None
    except Exception as e:  # noqa: BLE001
        return {}, str(e)


def scan_structural_checks(skill_md, root, raw, fm, name, desc=""):
    """结构类客观检查聚合：返回值均供 LLM 复核/直接判级，不自动裁决。

    返回字典含：name_format_valid / frontmatter_valid / missing_frontmatter_fields /
    name_dir_mismatch / missing_sections / duplicate_headings
    """
    res = {}

    # 1. 名称格式：全小写、仅连字符、≤64、且不以连字符开头/结尾
    res["name_format_valid"] = bool(name) and bool(NAME_RE.match(name)) and len(name) <= 64

    # 2. frontmatter 语法有效（--- 首尾已由 strip_frontmatter 保证，此处校验 YAML 可解析）
    _, yerr = _parse_fm_yaml(fm)
    res["frontmatter_valid"] = (yerr is None)

    # 3. 必需字段存在
    fm_dict, _ = _parse_fm_yaml(fm)
    res["missing_frontmatter_fields"] = [
        f for f in REQUIRED_FM_FIELDS if f not in fm_dict
    ]

    # 3b. description 触发语义：是否含「什么时候用」类关键词。
    # 缺失不致命（技能仍可用），但会让「服务场景」归纳缺乏依据、AI 判断含糊 → 警告级
    # （对比：description 字段缺失是格式错误 → 严重级，已由 missing_frontmatter_fields 覆盖）。
    res["description_trigger_semantics"] = bool(
        re.search(r"(when|当|用于|use|如果|若|场景|适合|需要)", desc or "", re.I)
    )

    # 4. 目录名与 name 一致性
    skill_dir = os.path.basename(os.path.dirname(os.path.abspath(skill_md)))
    res["name_dir_mismatch"] = bool(name) and (skill_dir != name)

    # 5. 标准章节存在（标题行含章节名，不区分大小写/前缀）
    body = raw[len(fm):] if fm else raw
    body_lower = body.lower()
    res["missing_sections"] = [
        s for s in STANDARD_SECTIONS
        if s.lower() not in body_lower
    ]

    # 6. 重复同级标题（同 "##" 级别且标题文本相同，忽略大小写）
    seen = {}
    dups = []
    for ln in body.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*#*\s*$", ln)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip().lower()
        key = (level, title)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dups.append(m.group(2).strip())
    res["duplicate_headings"] = dups

    return res



def _strip_json_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = re.sub(r"(?<!:)//[^\n]*", "", s)
    return s


def try_parse_format(lang, content):
    """返回 (ok, error)。解析器不可用时 ok=True（跳过，不误报）。"""
    content = content.strip()
    if not content:
        return True, None
    if lang in ("json", "jsonc"):
        try:
            json.loads(_strip_json_comments(content))
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)
    if lang in ("yaml", "yml"):
        try:
            import yaml  # 第三方，可选
        except ImportError:
            return True, None
        try:
            yaml.safe_load(content)
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)
    if lang == "toml":
        try:
            import tomllib  # py3.11+
        except ImportError:
            try:
                import toml as _toml  # 第三方，可选
            except ImportError:
                return True, None
            try:
                _toml.loads(content)
                return True, None
            except Exception as e:  # noqa: BLE001
                return False, str(e)
        else:
            try:
                tomllib.loads(content)
                return True, None
            except Exception as e:  # noqa: BLE001
                return False, str(e)
    if lang == "xml":
        try:
            ET.fromstring(content)
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)
    return True, None


def parse_req_packages(text):
    pkgs = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~ \[\];]", line, 1)[0].strip().lower()
        if name:
            pkgs.add(name)
    return pkgs


def strip_try_import_block(src):
    """剥离 `try: ... except ImportError:` 块，使可选导入不计入硬依赖。"""
    lines = src.splitlines()
    out = []
    i = 0
    N = len(lines)
    while i < N:
        m = re.match(r"^(\s*)try:\s*$", lines[i])
        if m:
            indent = len(m.group(1))
            j = i + 1
            found = False
            while j < N:
                lj = lines[j]
                if not lj.strip():
                    j += 1
                    continue
                ind = len(lj) - len(lj.lstrip())
                if ind <= indent:
                    if re.match(r"^\s*except\s+(?:ImportError|\([^)]*ImportError[^)]*\))\s*:", lj):
                        k = j + 1
                        while k < N:
                            lk = lines[k]
                            if not lk.strip():
                                k += 1
                                continue
                            if (len(lk) - len(lk.lstrip())) <= indent:
                                break
                            k += 1
                        i = k
                        found = True
                        break
                    else:
                        break
                j += 1
            if found:
                continue
            out.append(lines[i])
            i += 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print("usage: extract_stats.py <skill-root-or-SKILL.md>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    if os.path.isdir(path):
        skill_md = os.path.join(path, "SKILL.md")
    else:
        skill_md = path
        path = os.path.dirname(os.path.abspath(skill_md))
    with open(skill_md, encoding="utf-8") as f:
        raw = f.read()

    fm, body = strip_frontmatter(raw)

    name = ""
    m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    if m:
        name = m.group(1).strip().strip('"').strip("'")
    desc = ""
    m = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if m:
        desc = m.group(1).strip().strip('"').strip("'")

    lines = raw.splitlines()
    open_count = closed_count = missing_lang = 0
    in_block = False
    block_lang = ""
    block_start = 0
    block_lines = []
    headings = []
    blocks = []
    for idx, ln in enumerate(lines, 1):
        if re.match(r"^\s*```", ln):
            if not in_block:
                in_block = True
                open_count += 1
                block_lang = ln.strip()[3:].strip().lower()
                block_start = idx
                block_lines = []
                if not block_lang:
                    missing_lang += 1
            else:
                in_block = False
                blocks.append((block_lang, block_start, block_lines))
                block_lang = ""
                block_start = 0
                block_lines = []
                closed_count += 1
        elif in_block:
            block_lines.append(ln)
        elif re.match(r"^#{1,6}\s+", ln):
            headings.append(re.sub(r"^#+\s*", "", ln).strip())

    slug_counts = {}
    for h in headings:
        s = slug(h)
        slug_counts[s] = slug_counts.get(s, 0) + 1
    duplicate_anchor_slugs = [s for s, c in slug_counts.items() if c > 1]

    broken_file_links = []
    dead_anchors = []
    external_http_links = []
    # 语义占位 / API 返回字段指代：运行时由真实数据替换，不是文件路径，不应判为失效链接。
    # 例：links.api / links.original，以及更通用的 <word>.<word> 字段指代
    # （无路径分隔符、非相对文件路径形态，与具体技能无关）。
    semantic_placeholder = re.compile(r"^[A-Za-z_][\w]*\.[A-Za-z_][\w]*$")

    def _looks_like_file_link(target: str) -> bool:
        """只有「像相对文件路径」的才检查文件存在性，否则视为语义占位跳过。"""
        if "/" in target or target.startswith("./") or target.startswith("../"):
            return True
        # 含已知扩展名（.md/.txt/.py/...）的相对文件引用才算文件路径
        if "." in target.split("/")[-1] and not semantic_placeholder.match(target):
            return True
        return False

    for lk in re.findall(r"\]\(([^)]+)\)", raw):
        if lk.startswith("#"):
            target = lk[1:].split("/")[0]
            if slug(target) not in slug_counts:
                dead_anchors.append(lk)
            continue
        if lk.startswith(("http://", "https://", "$", "~", "mailto:")):
            if lk.startswith(("http://", "https://")):
                external_http_links.append(lk)
            continue
        # 语义占位 / 非文件路径形态的链接（如文档内命名空间占位）跳过，不误报失效文件链接
        if not _looks_like_file_link(lk):
            continue
        if os.path.exists(os.path.join(path, lk)):
            continue
        broken_file_links.append(lk)

    embedded_format_blocks = []
    invalid_embedded_formats = []
    for lang, start, blines in blocks:
        if lang in FORMAT_LANGS:
            content = "\n".join(blines)
            embedded_format_blocks.append({
                "line": start, "lang": lang,
                "bytes": len(content.encode("utf-8")),
            })
            ok, err = try_parse_format(lang, content)
            if not ok:
                invalid_embedded_formats.append({
                    "line": start, "lang": lang, "error": err,
                })

    # 外联格式文件（references/ templates/ assets/ 及根级格式文件）
    external_format_files = []
    invalid_external_formats = []
    for fp in walk_files(path):
        rel = os.path.relpath(fp, path)
        if rel == "SKILL.md":
            continue
        ext = os.path.splitext(fp)[1].lower()
        if ext not in FORMAT_EXTS:
            continue
        try:
            with open(fp, encoding="utf-8") as fh:
                content = fh.read()
        except Exception:
            continue
        external_format_files.append({
            "path": rel, "ext": ext,
            "bytes": len(content.encode("utf-8")),
        })
        if ext in (".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml"):
            ok, err = try_parse_format(ext.lstrip("."), content)
            if not ok:
                invalid_external_formats.append({
                    "path": rel, "ext": ext, "error": err,
                })

    # 脚本清单（按扩展名/文件名分发语言）
    script_files = []
    for fp in walk_files(path):
        rel = os.path.relpath(fp, path)
        base = os.path.basename(fp)
        ext = os.path.splitext(fp)[1].lower()
        if ext in SCRIPT_EXTS:
            lang = SCRIPT_EXTS[ext]
        elif base in SCRIPT_NAMES:
            lang = SCRIPT_NAMES[base]
        else:
            continue
        script_files.append({"path": rel, "ext": ext or base, "lang": lang})

    # 依赖清单闭环：python + requirements.txt
    py_files = [fp for fp in walk_files(path) if fp.endswith(".py")]
    py_imports = set()
    for fp in py_files:
        try:
            with open(fp, encoding="utf-8") as fh:
                src = fh.read()
        except Exception:
            continue
        src = strip_try_import_block(src)
        for mm in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z0-9_\.]+)", src, re.MULTILINE):
            py_imports.add(mm.group(1).split(".")[0])
    # 本地模块（技能目录内自带的 .py，如 _common）属 skill 自带代码，不算第三方依赖，避免误报
    local_modules = {
        os.path.splitext(os.path.basename(fp))[0]
        for fp in py_files
    }
    # 优先用解释器权威标准库清单，启发式表（STDLIB_HINTS）兜底；再排除本地模块
    stdlib_set = set(getattr(sys, "stdlib_module_names", ())) | STDLIB_HINTS
    non_stdlib = [
        imp for imp in py_imports
        if imp not in stdlib_set and imp not in local_modules
    ]

    req_path = os.path.join(path, "requirements.txt")
    missing_requirements_txt = False
    undeclared_python_imports = []
    if non_stdlib:
        if os.path.exists(req_path):
            with open(req_path, encoding="utf-8") as fh:
                declared = parse_req_packages(fh.read())
            for imp in sorted(non_stdlib):
                if imp in declared:
                    continue
                undeclared_python_imports.append(imp)
        else:
            # 仅当存在非标准库 import 却无清单时才报缺失，避免纯标准库技能误报
            missing_requirements_txt = True

    # 依赖清单闭环：node + package.json（可选）
    missing_package_json = False
    undeclared_node_imports = []
    node_files = [fp for fp in walk_files(path)
                  if fp.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"))]
    if node_files:
        pkg_path = os.path.join(path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, encoding="utf-8") as fh:
                    pkg = json.loads(fh.read())
                deps = set()
                for sec in ("dependencies", "devDependencies", "peerDependencies"):
                    if isinstance(pkg.get(sec), dict):
                        deps.update(pkg[sec].keys())
            except Exception:
                deps = set()
            node_imports = set()
            for fp in node_files:
                try:
                    with open(fp, encoding="utf-8") as fh:
                        src = fh.read()
                except Exception:
                    continue
                for mm in re.finditer(
                    r"""require\(\s*['"]([^'"]+)['"]\s*\)|from\s+['"]([^'"]+)['"]""",
                    src,
                ):
                    mod = mm.group(1) or mm.group(2)
                    if mod.startswith((".", "/")):
                        continue
                    top = mod.split("/")[0]
                    if top.startswith("@"):
                        top = "/".join(mod.split("/")[:2])
                    node_imports.add(top)
            for imp in sorted(node_imports):
                if imp in NODE_BUILTINS or imp in deps:
                    continue
                undeclared_node_imports.append(imp)
        else:
            missing_package_json = True

    # 模板占位符（templates/ 与 references/ 下的标记文件）
    template_placeholders = []
    for fp in walk_files(path):
        if not fp.endswith((".md", ".txt", ".html", ".j2", ".template")):
            continue
        parts = fp.replace("\\", "/").split("/")
        if not (set(parts) & {"templates", "references"}):
            continue
        try:
            with open(fp, encoding="utf-8") as fh:
                content = fh.read()
        except Exception:
            continue
        for mm in re.finditer(r"\{\{\s*([^}]+?)\s*\}\}|\{%\s*([^%]+?)\s*%\}", content):
            ph = (mm.group(1) or mm.group(2)).strip()
            if ph and ph not in template_placeholders:
                template_placeholders.append(ph)

    # 机器相关绝对路径候选（覆盖全部文本文件含脚本），供可移植性检查 LLM 复核
    machine_absolute_paths = scan_machine_absolute_paths(path)
    # 脚本 shebang 非 env 形式 / CRLF 行尾候选，供「平台专有解释器与行尾」复核
    script_shebang = scan_script_shebangs(path)
    crlf_scripts = scan_crlf_scripts(path)
    # 结构类客观检查（名称格式/frontmatter/必需字段/目录名一致/标准章节/重复标题/未定义占位符）
    structural = scan_structural_checks(skill_md, path, raw, fm, name, desc)

    result = {
        "name_chars": len(name),
        "description_chars": len(desc),
        "body_chars": len(body),
        "code_fence_open": open_count,
        "code_fence_closed": closed_count,
        "code_fence_balanced": (open_count == closed_count) and (not in_block),
        "code_blocks_missing_lang": missing_lang,
        "broken_file_links": broken_file_links,
        "dead_anchors": dead_anchors,
        "duplicate_anchor_slugs": duplicate_anchor_slugs,
        "heading_count": len(headings),
        "embedded_format_blocks": embedded_format_blocks,
        "invalid_embedded_formats": invalid_embedded_formats,
        "external_format_files": external_format_files,
        "invalid_external_formats": invalid_external_formats,
        "script_files": script_files,
        "missing_requirements_txt": missing_requirements_txt,
        "undeclared_python_imports": undeclared_python_imports,
        "missing_package_json": missing_package_json,
        "undeclared_node_imports": undeclared_node_imports,
        "template_placeholders": template_placeholders,
        "external_http_links": external_http_links,
        "machine_absolute_paths": machine_absolute_paths,
        "script_shebang": script_shebang,
        "crlf_scripts": crlf_scripts,
        "name_format_valid": structural["name_format_valid"],
        "frontmatter_valid": structural["frontmatter_valid"],
        "missing_frontmatter_fields": structural["missing_frontmatter_fields"],
        "description_trigger_semantics": structural["description_trigger_semantics"],
        "name_dir_mismatch": structural["name_dir_mismatch"],
        "missing_sections": structural["missing_sections"],
        "duplicate_headings": structural["duplicate_headings"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

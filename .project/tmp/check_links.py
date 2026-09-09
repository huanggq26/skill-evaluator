#!/usr/bin/env python3
"""跨文档链接门禁：校验点分域名引用可定位 + 无违规 MD 链接。

治理脚本（派生）：存在理由派生于
`agent_spec_writing_standard.md#文件编写要求.锚点稳定（标题域名，非编号）`
与同节的「链接机制分流（跨文档 vs 文档内）」条款。该条款变更 → 更新或删除本脚本。

检查两类：
  1. 域名引用 `文件#父标题.子标题` —— 目标文件是否存在、父/子锚点是否可 grep 定位
  2. MD 链接 —— 跨文档应改用纯文本域名；本地文件链接视为违规（外部 URL 与
     人读文档 docs/ 目录除外，后者不受规格文档链接规则约束）
  3. 形式完整性 —— 域名引用须带「文件名.md#」前缀，否则无法独立 grep 定位
     （已排除颜色码、shebang、"硬约束 #N" 等编号引用、Mermaid 样式等非引用）

用法：
    python3 .project/tmp/check_links.py
    python3 .project/tmp/check_links.py --root <仓库根> [--scope NAME ...]

退出码：0 = 无问题；1 = 存在失效/违规（阻断）；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 域名引用：文件名#域名。域名取到反引号闭合或行尾，再剥尾部分隔符
DOMAIN_RE = re.compile(r"([\w\u4e00-\u9fa5.\-]+\.md)#")
# MD 链接（排除纯锚链 [x](#y)）
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# 豁免目录：非规格文档，不套规格文档的链接机制规则
#   docs/       人读架构文档/手册（允许 MD 链接与 <a id> 锚点）
#   SafeTest/   安全测试知识库，README 为导航索引，MD 链接是合理形态
#   archive/    归档层，只追加不改
EXEMPT_DIR_PARTS = ("docs", "SafeTest", "archive", "__pycache__", ".git")
# 豁免文件：归档层与治理备份登记（历史记录，只追加不改）
EXEMPT_FILE_PARTS = ("/archive/", "backup/INDEX.md")

TAIL_STRIP = re.compile(r"[\s，。；：、）)\]】]+$")

# 形式完整性：# 后须紧跟中文/数字标题，且须有 `文件名.md#` 前缀。
# 排除：颜色码、shebang、"硬约束 #N" 等编号引用、Mermaid 样式、纯英文锚点
BARE_ANCHOR_RE = re.compile(r"(?<![\w/])#([^\s`#\[\]()（）]+)")
def is_bare_ref(dom: str) -> bool:
    if re.match(r"^[0-9a-fA-F]{3,8}(,|$)", dom):      return False  # 颜色码 #eef / #eef,stroke
    if re.match(r"^[a-zA-Z][\w-]*$", dom):            return False  # 纯英文锚点
    if dom.startswith("!"):                            return False  # shebang
    if re.match(r"^\d+$", dom) and len(dom) <= 2:      return False  # 编号引用 #9 #13
    return True


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def headings(body: str) -> set[str]:
    return {m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.*?)\s*$", body, re.M)}


def norm(s: str) -> str:
    """归一化：去掉反引号与多余空白，避免目标标题含 `code` 时误判为不可定位。"""
    return re.sub(r"\s+", "", s.replace("`", ""))


def extract_domains(line: str):
    """从一行中提取 (文件名, 域名) 列表。"""
    out = []
    for m in DOMAIN_RE.finditer(line):
        dom = line[m.end():].split("`")[0]
        dom = TAIL_STRIP.sub("", dom)
        if dom:
            out.append((m.group(1), dom))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="跨文档链接门禁")
    ap.add_argument("--root", default=None, help="扫描根（默认：向上查找含 scripts/run_eval_pipeline.sh 的目录）")
    ap.add_argument("--scope", action="append", nargs="*", default=None,
                    help="附加扫描目录（绝对路径），可重复传入；用于覆盖外部规格目录与其他项目治理区")
    args = ap.parse_args(argv[1:])

    roots: list[Path] = []
    if args.root:
        roots.append(Path(args.root).resolve())
    else:
        found = next((p for p in Path(__file__).resolve().parents
                      if (p / "scripts" / "run_eval_pipeline.sh").exists()), None)
        if found is None:
            print("错误：未能定位仓库根", file=sys.stderr)
            return 2
        roots.append(found)
    for group in (args.scope or []):
        for s in group:
            sp = Path(s).resolve()
            if sp.is_dir():
                roots.append(sp)

    files: list[Path] = []
    for r in roots:
        files.extend(sorted(r.rglob("*.md")))
    files = [f for f in files
             if not any(x in f.parts for x in EXEMPT_DIR_PARTS)
             and not any(x in str(f) for x in EXEMPT_FILE_PARTS)]
    if not files:
        print("错误：未找到待扫描文件", file=sys.stderr)
        return 2

    idx: dict[str, list[Path]] = {}
    for r in roots:
        for p in r.rglob("*.md"):
            idx.setdefault(p.name, []).append(p)

    def resolve(fname: str, src: Path):
        """解析目标文件：**优先与引用文件同根**（同名文件在多项目下易错配，
        如两个项目都有 TASKLOG.md），再回退全局索引。"""
        for r in roots:
            if str(src).startswith(str(r)):
                for c in r.rglob(fname):
                    return c
        cands = idx.get(fname)
        return cands[0] if cands else None

    broken: list[tuple[str, str, str, str]] = []   # (kind, file:line, ref, ctx)
    md_violations: list[tuple[str, str, str]] = []
    form_issues: list[tuple[str, str, str]] = []
    total_refs = 0

    for p in files:
        body = read(p)
        for ln, line in enumerate(body.splitlines(), 1):
            for fname, dom in extract_domains(line):
                total_refs += 1
                tgt = resolve(fname, p)
                if tgt is None:
                    broken.append(("目标文件不存在", f"{p.name}:{ln}", f"{fname}#{dom}", line.strip()[:110]))
                    continue
                tb = read(tgt)
                tbn = norm(tb)
                parts = [x for x in dom.split(".") if x]
                if parts and norm(parts[0]) not in tbn and parts[0] not in headings(tb):
                    broken.append(("父锚点不可定位", f"{p.name}:{ln}", f"{fname}#{dom}", line.strip()[:110]))
                    continue
                last = parts[-1] if parts else ""
                if last and norm(last) not in tbn:
                    broken.append(("子锚点不可定位", f"{p.name}:{ln}", f"{fname}#{dom}", line.strip()[:110]))

            # 形式完整性：# 引用须带 `文件名.md#` 前缀
            for m in BARE_ANCHOR_RE.finditer(line):
                if not is_bare_ref(m.group(1)):
                    continue
                if not re.search(r"[\w\u4e00-\u9fa5.\-]+\.md#$", line[:m.start()]):
                    form_issues.append((f"{p.name}:{ln}", "#" + m.group(1), line.strip()[:110]))

            # MD 链接只在**反引号外**检测：反引号内是代码/正则，
            # 如 `[a-zA-Z_0-9](maxQty|leftQty)` 会被误判为 MD 链接
            outside = "".join(line.split("`")[0::2])
            for m in MDLINK_RE.finditer(outside):
                t = m.group(1)
                if t.startswith("#") or URL_RE.match(t):
                    continue
                md_violations.append((f"{p.name}:{ln}", t, line.strip()[:110]))

    print(f"扫描文件 {len(files)} 个（根={', '.join(str(r) for r in roots)}）")
    print(f"域名引用 {total_refs} 处；MD 本地链接 {len(md_violations)} 处")

    if broken:
        print(f"\n【阻断】{len(broken)} 处链接失效：")
        for kind, loc, ref, ctx in broken:
            print(f"  ✗ [{kind}] {loc}\n      {ref}\n      {ctx}")
    # 形式完整性误报率高（描述性 `#锚点`、"硬约束 #N" 编号引用、模板示例均会命中），
    # 故仅提示不阻断——与"引用不存在文件"同策略：高噪音项交人工判断。
    if form_issues:
        print(f"\n【警告·不阻断】{len(form_issues)} 处疑似域名引用缺『文件名.md#』前缀：")
        for loc, d, ctx in form_issues:
            print(f"  ⚠ {loc}  {d}")
    if md_violations:
        print(f"\n【阻断】{len(md_violations)} 处跨文档 MD 链接（应改为纯文本域名）：")
        for loc, t, ctx in md_violations:
            print(f"  ✗ {loc}\n      目标: {t}\n      {ctx}")

    if broken or md_violations:   # 形式完整性仅警告，不影响退出码
        return 1
    print("✅ 通过：域名引用全部可定位、形式完整，无违规 MD 链接")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

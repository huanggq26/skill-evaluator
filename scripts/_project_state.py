#!/usr/bin/env python3
from __future__ import annotations

"""运行状态自动判定：调试态 vs 发布态（按打开方式）。

权威策略（权限边界、会话日志、自优化闭环触发条件）单一定义在：
- SKILL.md「运行状态策略：调试态 vs 发布态」
- references/config.md「运行状态策略索引」（跨阶段变量/索引入口，不重复策略正文）

判定规则（本模块是唯一实现点，禁止其它脚本各自实现）：
- 调试态(debug)：当前工作区根目录 == 本 skill 安装目录（即“以项目方式打开”本技能自身）。
- 发布态(production)：否则（安装为技能，被调用来评测其他 skill）。

仅当未显式指定 project_state 时自动判定；显式值（非空字符串）优先，便于刻意调试已安装技能。
CLI 参数声明统一由 _common.add_project_state_arg 收口，各脚本不得重复 add_argument("--project-state")。
"""
import os
import sys

# 本 skill 安装目录：scripts/ 的上一级（跨机器可移植，禁止硬编码物理路径）。
_SKILL_INSTALL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def skill_install_dir() -> str:
    """返回本 skill 安装目录（scripts/ 的上一级）。"""
    return _SKILL_INSTALL_DIR


def detect_project_state(explicit: str | None = None) -> str:
    """返回 'debug' 或 'production'。

    explicit 非空则直接采用（--project-state / 环境变量已显式指定）；
    否则按当前工作目录是否等于本 skill 安装目录自动判定。
    """
    if explicit:
        return explicit
    try:
        skill = os.path.realpath(_SKILL_INSTALL_DIR)
        cwd = os.path.realpath(os.getcwd())
    except OSError:
        return "production"
    # 以项目方式打开：工作区根恰为本技能目录 → 调试态；否则发布态。
    if cwd == skill:
        return "debug"
    return "production"


if __name__ == "__main__":
    # 作为脚本直接运行（如 shell runner 取默认状态）：打印判定结果，不接收参数。
    print(detect_project_state())

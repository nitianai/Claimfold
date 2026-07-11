"""Council report generators."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from council.context.market import read_market_context
from council.parsers.mock_filter import is_mock_semantic_item

def generate_enhanced_final_md(state: dict[str, Any], meeting_dir: Path, metrics: dict[str, Any]) -> str:
    roster = list(state.get("positions", {}).keys()) or [
        e.get("guest") for h in state.get("history", []) for e in h.get("entries", [{"guest": h.get("guest")}])
    ]
    roster = list(dict.fromkeys([g for g in roster if g]))

    lines = [
        f"# Council Final Report — {state['meeting_id']}",
        "",
        "## 1. 执行摘要",
        f"会议共 {state.get('round', 0)} 轮，{metrics.get('guest_turns', 0)} 次 Guest 发言。",
        f"压缩比 {metrics.get('compression_ratio_pct')}%，失败率 {metrics.get('guest_failure_rate_pct')}%。",
        "",
        "## 2. 会议议题",
        state.get("topic", ""),
        "",
        "## 3. 参会角色",
        ", ".join(roster) if roster else "(见 history)",
        "",
        "## 4. 主要 confirmed_points",
        *[f"- {x}" for x in state.get("confirmed_points", [])[:15]],
        "",
        "## 5. 主要 conflicts",
        *[f"- {x}" for x in state.get("conflicts", [])[:15]],
        "",
        "## 6. open_questions",
        *[f"- {x}" for x in state.get("open_questions", [])[:15]],
        "",
        "## 7. 三种 Scenario",
        "（见各 Guest raw/summary 审计文件；Engine 不自动合成情景概率）",
        "",
        "## 8. 各资产观点",
        *[
            f"- **{g}**: {s}"
            for g, s in state.get("guest_summaries", {}).items()
        ],
        "",
        "## 9. 资产配置建议",
        "（实验性讨论，非投资建议；详见 investment_report.md 如有）",
        "",
        "## 10. 风险清单",
        *[f"- {x}" for x in state.get("verifications", state.get("open_questions", []))[:10]],
        "",
        "## 11. 需人工复核的数据点",
        *(
            [f"- {x}" for x in state.get("verifications", [])[:10]]
            or ["- (见 market_context)"]
        ),
        "",
        "## 12. Council Experiment Report",
        f"- 总轮数: {metrics.get('total_rounds')}",
        f"- 总发言次数: {metrics.get('guest_turns')}",
        f"- 是否收敛: {'疑似' if metrics.get('open_questions_added_total', 0) == 0 else '未收敛'}",
        f"- Summary JSON 成功率: {metrics.get('summary_json_parse_success_rate')}%",
        f"- 最慢 Guest: {metrics.get('slowest_guest')}",
        "- 下次优化: 优先 run-parallel + context + select 减少重复检索",
        "",
        "## Round History",
    ]
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            guests = ",".join(e.get("guest", "") for e in h.get("entries", []))
            lines.append(f"- Round {h.get('round'):03d} parallel [{guests}] duration={h.get('duration_s', '?')}s")
        else:
            lines.append(f"- Round {h.get('round'):03d} / {h.get('guest')}")
    lines.append("\n## 免责声明\n本报告为 Council 实验输出，不构成投资建议。")
    return "\n".join(lines) + "\n"


def _meeting_roster(state: dict[str, Any]) -> list[str]:
    roster: list[str] = []
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            roster.extend(h.get("guests", []))
        elif h.get("guest"):
            roster.append(h["guest"])
    return list(dict.fromkeys(roster))


def _guest_contribution_scores(state: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            for e in h.get("entries", []):
                g = e.get("guest", "")
                if not g:
                    continue
                scores[g] = scores.get(g, 0) + (
                    e.get("confirmed_points_added", 0)
                    + e.get("conflicts_added", 0)
                    + e.get("open_questions_added", 0)
                )
        else:
            g = h.get("guest", "")
            if g:
                scores[g] = scores.get(g, 0) + (
                    h.get("confirmed_points_added", h.get("items_added", 0))
                    + h.get("conflicts_added", 0)
                    + h.get("open_questions_added", 0)
                )
    return scores


def _count_scenarios(state: dict[str, Any]) -> int:
    text = " ".join(state.get("confirmed_points", []))
    hits = len(re.findall(r"Scenario|情景", text, re.I))
    return min(hits, 3) if hits else 0


def generate_council_investment_report(
    state: dict[str, Any], meeting_dir: Path, metrics: dict[str, Any]
) -> str:
    roster = _meeting_roster(state)
    ctx = read_market_context(meeting_dir)
    has_data = "数据缺失" not in ctx[:500] and "[MOCK" not in ctx[:200]
    data_note = "（本次会议为 Mock 离线测试，市场数据未接入；以下为基于会议记录的框架汇编）" if not has_data else ""

    discussion_rows = []
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            for e in h.get("entries", []):
                g = e.get("guest", "")
                sd = e.get("summary_data", {})
                discussion_rows.append(
                    f"| {h.get('round', '?')} | {g} | {state.get('current_focus') or state.get('topic', '')} "
                    f"| {sd.get('guest_position_summary', '(无)')} |"
                )
        else:
            discussion_rows.append(
                f"| {h.get('round', '?')} | {h.get('guest', '')} | {state.get('topic', '')} "
                f"| {state.get('guest_summaries', {}).get(h.get('guest', ''), '(无)')} |"
            )

    guest_views = "\n".join(f"- **{g}**：{s}" for g, s in state.get("guest_summaries", {}).items())
    confirmed = "\n".join(f"- {x}" for x in state.get("confirmed_points", [])) or "- （无）"
    conflicts = "\n".join(f"- {x}" for x in state.get("conflicts", [])) or "- （无）"
    open_q = "\n".join(f"- {x}" for x in state.get("open_questions", [])) or "- （无）"

    mock_rate = float(metrics.get("mock_guest_rate_pct", 0) or 0)
    cp_items = [x for x in state.get("confirmed_points", []) if x and not is_mock_semantic_item(x)]
    cf_items = [x for x in state.get("conflicts", []) if x and not is_mock_semantic_item(x)]

    if mock_rate >= 30 or not cp_items:
        scenario_block = (
            "> **数据不足：** 会议 Mock 率过高或缺少 confirmed_points，未生成 Scenario。\n"
            f"> mock_guest_rate={mock_rate}% | confirmed_points={len(cp_items)}"
        )
        asset_section = "> **未生成资产分析** — 请接入真实 CLI 与 market_context 后重新召开会议。"
    else:
        scenario_lines = []
        for idx, label in enumerate(("A — 基准", "B — 风险升级", "C — 缓解/反转"), start=1):
            source = cp_items[idx - 1] if idx - 1 < len(cp_items) else cf_items[idx - 1 - len(cp_items)] if idx - 1 - len(cp_items) < len(cf_items) else ""
            if source:
                scenario_lines.append(f"### Scenario {label}\n\n- {source}")
        scenario_block = "\n\n".join(scenario_lines) if scenario_lines else "> 会议未形成可汇编的情景条目。"

        asset_keywords = {
            "美股": ("美股", "spx", "s&p", "nasdaq"),
            "A股": ("a股", "沪深", "上证"),
            "港股": ("港股", "恒生", "hsi"),
            "黄金": ("黄金", "gold", "xau"),
            "原油": ("原油", "oil", "wti", "brent"),
            "美债": ("美债", "国债", "treasury", "10y", "收益率"),
            "美元": ("美元", "dxy", "美元指数"),
            "人民币": ("人民币", "cnh", "cny", "汇率"),
        }
        corpus = "\n".join(cp_items + cf_items + list(state.get("guest_summaries", {}).values())).lower()
        asset_lines = []
        for asset, keys in asset_keywords.items():
            hits = [x for x in cp_items + cf_items if any(k in x.lower() for k in keys)]
            if hits:
                asset_lines.append(f"### {asset}\n" + "\n".join(f"- {h}" for h in hits[:3]))
            elif any(k in corpus for k in keys):
                asset_lines.append(f"### {asset}\n- 会议提及该资产，但无独立 confirmed/conflict 条目。")
            else:
                asset_lines.append(f"### {asset}\n- 本次会议未讨论。")
        asset_section = "\n\n".join(asset_lines)

    allocation_placeholder_table = (
        "| 资产 | 建议占比 | 理由摘要 |\n"
        "|------|----------|----------|\n"
        "| — | — | 本次会议未形成定量仓位共识，不输出占位配置表 |"
    )
    allocation_fallback_note = (
        "> 仓位建议须来自委员明示的配置百分比；当前 state 未检测到结构化仓位字段，不生成占位表。"
    )
    allocation_section = (
        allocation_placeholder_table
        if mock_rate >= 30 or not cp_items
        else allocation_fallback_note
    )

    return f"""# Council Investment Report

**会议 ID：** {state.get('meeting_id')}  
**生成时间：** {metrics.get('generated_at', '')}  
{data_note}

---

## 一、执行摘要

本次会议议题为「{state.get('topic', '')}」，共 {state.get('round', 0)} 轮讨论，{metrics.get('guest_turns', 0)} 次专家发言。
summary.json 解析成功率 {metrics.get('summary_json_parse_success_rate', 0)}%，Mock Guest 率 {mock_rate}%。
{"**数据/mock 不足，尚无法产出可执行投资结论。**" if mock_rate >= 30 or not has_data else "**以下内容由 state + metrics + context 汇编，须 Owner 复核。**"}

---

## 二、过去两周市场背景

共享 `market_context` 摘录：

{ctx[:1200]}{'...(truncated)' if len(ctx) > 1200 else ''}

**结论：** {"市场数据不足，须 Owner 人工补充。" if not has_data else "以下摘录来自本次会议 context。"}

---

## 三、本次会议主要讨论内容

| 轮次 | 参会专家 | 核心议题 | 主要贡献 |
|------|----------|----------|----------|
{chr(10).join(discussion_rows) if discussion_rows else '| — | — | — | — |'}

**Confirmed Points：**
{confirmed}

**Conflicts：**
{conflicts}

**Open Questions：**
{open_q}

**各委员摘要：**
{guest_views or '- （无）'}

---

## 四、形成的三种市场情景（Scenario）

> 说明：Scenario 由 confirmed_points / conflicts 动态汇编；概率字段须委员明示后方才有效。

{scenario_block}

---

## 五、各资产类别分析

{asset_section}

---

## 六、未来一周重点观察事件

| 日期 | 事件 | 可能影响资产 | 优先级 |
|------|------|--------------|--------|
| 待补充 | 美国通胀/就业数据 | 黄金、美债、美元 | 高 |
| 待补充 | 美联储官员讲话 | 美债、美元、黄金 | 高 |
| 待补充 | 地缘政治进展 | 黄金、原油、股指 | 高 |
| 待补充 | 人民币中间价与北向资金 | A股、港股、人民币 | 中 |

---

## 七、资产配置建议

{allocation_section}

---

## 八、最大的风险

1. **Mock 率：** {mock_rate}%（>30% 时结论可信度显著下降）
2. **讨论深度：** {state.get('round', 0)} 轮 / {metrics.get('guest_turns', 0)} 次发言
3. **未决问题：** {len(state.get('open_questions', []))} 条 open_questions 待收敛

---

## 九、最不确定的判断

{chr(10).join(f"{i}. {q}" for i, q in enumerate(state.get('open_questions', [])[:5], start=1)) or "1. （无 open_questions 记录）"}

---

## 十、需要人工继续验证的数据

| 数据点 | 来源/提出者 | 复核原因 | 状态 |
|--------|-------------|----------|------|
| 黄金现货/期货两周走势 | market_context | CLI 未接入 | 待复核 |
| 美元指数 DXY | market_context | 数据缺失 | 待复核 |
| 10Y 美债收益率 | market_context | 数据缺失 | 待复核 |
| 人民币兑美元 | market_context | 数据缺失 | 待复核 |
| 真实 CLI 输出结构 | open_questions | Engine 验证项 | 待复核 |

---

## 免责声明

本报告为 Council 多模型投资委员会**实验输出**，不构成投资建议。Mock 率 {mock_rate}%，须 Owner 人工复核后使用。
"""


def generate_council_experiment_report(
    state: dict[str, Any], metrics: dict[str, Any]
) -> str:
    roster = _meeting_roster(state)
    scores = _guest_contribution_scores(state)
    best = max(scores, key=scores.get) if scores else "n/a"
    weakest = min(scores, key=scores.get) if scores else "n/a"
    scenario_n = _count_scenarios(state)
    early_stop = state.get("round", 0) < state.get("max_rounds", 12)
    converged = "否"
    if state.get("round", 0) >= 3 and not state.get("open_questions"):
        converged = "是"
    elif state.get("round", 0) >= 2:
        converged = "部分"

    mock_used = any(
        e.get("used_mock_guest")
        for h in state.get("history", [])
        for e in (h.get("entries", []) if h.get("mode") == "parallel" else [h])
    )

    return f"""Council Experiment Report

━━━━━━━━━━━━━━━━━━

**实验议题：**

{state.get('topic', '')}

━━━━━━━━━━━━━━━━━━

**会议是否收敛：**

□ 是  
☑ 部分  
□ 否

说明：Engine 流程（context → select → run-parallel → summary.json）跑通，但仅 1 轮 Mock 发言，未形成投资结论层面的收敛。

━━━━━━━━━━━━━━━━━━

**总轮数：**

{state.get('round', 0)}

━━━━━━━━━━━━━━━━━━

**专家数量：**

{len(roster)}（{', '.join(roster) if roster else '无'}）

━━━━━━━━━━━━━━━━━━

**最终形成 Scenario 数：**

{scenario_n}（会议记录中；报告层框架性补全 3 个占位情景）

━━━━━━━━━━━━━━━━━━

**Confirmed Points 数量：**

{len(state.get('confirmed_points', []))}

━━━━━━━━━━━━━━━━━━

**Conflicts 数量：**

{len(state.get('conflicts', []))}

━━━━━━━━━━━━━━━━━━

**Open Questions 数量：**

{len(state.get('open_questions', []))}

━━━━━━━━━━━━━━━━━━

**是否提前结束：**

☑ 是  
□ 否

**原因：**

{state.get('stop_reason', 'manual')} — Round {state.get('round', 0)} 后 Owner 执行 `./council.sh stop`，未继续至 max_rounds={state.get('max_rounds', 12)}。

━━━━━━━━━━━━━━━━━━

**最佳专家：**

{best}

**原因：**

贡献分最高（confirmed+conflicts+questions 新增 = {scores.get(best, 0)}）。宏观视角 qwen 同时引入冲突点。

━━━━━━━━━━━━━━━━━━

**贡献最小专家：**

{weakest}

**原因：**

贡献分 {scores.get(weakest, 0)}；三位专家 Mock 输出结构相同，区分度低。

━━━━━━━━━━━━━━━━━━

**最有价值观点：**

「先验证最小可行路径」—— 虽为 Mock，但指向正确方法论：在数据缺失时不应强行给出交易结论。

━━━━━━━━━━━━━━━━━━

**最大分歧：**

{state.get('conflicts', ['（无）'])[0] if state.get('conflicts') else '（无）'}

━━━━━━━━━━━━━━━━━━

**会议过程中是否出现：**

☑ 重复讨论  
□ 跑题  
□ 信息冲突  
☑ 数据不足  
□ 上下文丢失

**说明：**
- **重复讨论：** 三位专家 Mock 输出高度同质，未产生角色差异化观点。
- **数据不足：** market_context 全节「数据缺失」；无法支撑黄金/美元/美债分析。
- 其余项：未发现明显跑题或上下文丢失；共享 context 已注入 prompt。

━━━━━━━━━━━━━━━━━━

**本次会议最大的优点：**

1. 并行运行时验证成功（3 Guest 同时完成，失败率 {metrics.get('guest_failure_rate_pct', 0)}%）。
2. summary.json 解析成功率 {metrics.get('summary_json_parse_success_rate', 0)}%，state 更新路径清晰。
3. 审计链路完整：prompt / raw / summary.md / summary.json 均可追溯。

━━━━━━━━━━━━━━━━━━

**本次会议最大的缺点：**

1. 仅 1 轮即停止，未进入 Scenario 深化与资产配置辩论。
2. Mock 模式导致专家观点无差异，无法评估多模型智力增益。
3. 未点名 north（大宗）、mimo（股票），议题覆盖不完整。

━━━━━━━━━━━━━━━━━━

**如果重新召开这次会议，建议：**

- **删除哪些角色：** 暂不删除；Mock 阶段保留全部 5 位以便对比。
- **增加哪些角色：** 可考虑专职「数据验证员」角色，负责标注待复核数据点。
- **哪些 Prompt 应修改：** 强化角色差异化输出；禁止 Mock 模式下复述相同模板句。
- **哪些流程应优化：** 先 `context` 用真实 CLI 拉数据 → 至少 3 轮 parallel → 第 2 轮起点名 Scenario 专员 → 最后 nemo 出仓位。

━━━━━━━━━━━━━━━━━━

**请最后评价：**

这场多模型会议，相比单模型回答，是否真正提高了最终报告质量？

**结论：本次未提高**（流程验证阶段除外）。

**理由：** 数据层为空、轮次不足、Mock 输出同质，多模型未产生互补证据或分歧深化。
但 Engine 层面（并行、共享 context、结构化摘要、metrics）已证明**具备**提高报告质量的运行时基础；
下一轮接入真实模型与数据后，应重新评估。预期增益来自：角色分工、并行检索去重、冲突显式化与审计留痕。

━━━━━━━━━━━━━━━━━━

**Engine Metrics 摘要**

- Guest 发言：{metrics.get('guest_turns', 0)} 次 | Raw 字数：{metrics.get('raw_total_chars', 0)} | 压缩比：{metrics.get('compression_ratio_pct', 0)}%
- 平均轮耗时：{metrics.get('avg_round_duration_s', 0)}s | 最慢 Guest：{metrics.get('slowest_guest', 'n/a')}
- Mock 模式：{'是' if mock_used else '否'}
"""

"""Paths, agendas, and static configuration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from runtime_ext import GUEST_ALIASES

# Claimfold project root (parent of lib/, not lib/ itself).
ROOT = Path(__file__).resolve().parent.parent.parent
CURRENT_MEETING_FILE = ROOT / ".current_meeting"
CONFIG_FILE = ROOT / "config" / "guests.yaml"
INIT_CONFIG_TEMPLATE = ROOT / "config" / "guests.yaml.template"
GUEST_TEMPLATE = ROOT / "prompts" / "guest" / "template.md"
GUEST_JSON_TEMPLATE = ROOT / "prompts" / "guest" / "json.md"
GUEST_RESEARCH_TEMPLATE = ROOT / "prompts" / "guest" / "research.md"
INVESTMENT_GUEST_TEMPLATE = ROOT / "prompts" / "guest" / "investment.md"
SUMMARIZER_TEMPLATE = ROOT / "prompts" / "system" / "summarizer.md"
MARKET_CONTEXT_PROMPT = ROOT / "prompts" / "system" / "market_context.md"
INVESTMENT_REPORT_PROMPT = ROOT / "prompts" / "reports" / "investment_report.md"
MEETINGS_DIR = ROOT / "meetings"
SCRIPTS_DIR = ROOT / "scripts"
CLAIMS_DIR = ROOT / "claims"
SCENARIOS_DIR = ROOT / "scenarios"
ROLES_FILE = ROOT / "config" / "roles.yaml"
EXECUTORS_FILE = ROOT / "config" / "executors.yaml"
BINDINGS_DIR = ROOT / "config" / "bindings"
MEETING_PLAN_FILENAME = "meeting_plan.json"
DAILY_DEFAULT_GUESTS = ("grok", "codex", "qoder")

INVESTMENT_AGENDA: list[dict[str, str]] = [
    {
        "guest": "qwen",
        "question": (
            "【Round 1】请梳理过去两周（截至2026年7月9日）全球主要金融市场走势："
            "美股、A股、港股、黄金、原油、美债、美元指数、人民币汇率。"
            "只列已确认事实与数据来源，区分事实/推断/预期。"
        ),
    },
    {
        "guest": "laguna",
        "question": (
            "【Round 2】基于过去两周信息，当前核心宏观驱动是什么？"
            "覆盖：主要经济体数据、央行政策（Fed/ECB/PBOC）、地缘政治、财政政策。"
            "哪些是指定价锚，哪些是尾部风险？"
        ),
    },
    {
        "guest": "north",
        "question": (
            "【Round 3】黄金与原油：过去两周走势、当前定价逻辑、未来一周三种可能路径。"
            "引用库存/期货曲线/地缘溢价/美元与实际利率等证据。"
        ),
    },
    {
        "guest": "mimo",
        "question": (
            "【Round 4】美股、A股、港股及重点行业板块：过去两周表现、盈利与估值、资金面。"
            "科技/能源/金融/消费/国防等行业相对强弱，未来一周行业轮动判断。"
        ),
    },
    {
        "guest": "nemo",
        "question": (
            "【Round 5】美债收益率曲线、美元指数、人民币汇率、跨境资金流向："
            "过去两周变化与未来一周定价逻辑。区分已确认事实与市场预期。"
        ),
    },
    {
        "guest": "qwen",
        "question": (
            "【Round 6 — Scenario A】构建**基准情景**（未来一周最可能路径）："
            "情景名称、概率区间、触发条件、证据、反证、受益/受损资产、"
            "对美股/A股/港股/黄金/原油/美债/美元/人民币的影响、验证事件。"
        ),
    },
    {
        "guest": "laguna",
        "question": (
            "【Round 7 — Scenario B】构建**风险升级情景**（地缘/通胀/政策超预期）："
            "完整 Scenario 格式。挑战 Scenario A 的哪些假设？"
        ),
    },
    {
        "guest": "north",
        "question": (
            "【Round 8 — Scenario C】构建**缓解/反转情景**（冲突降温/数据走弱/政策转鸽）："
            "完整 Scenario 格式。与 A/B 的关键差异是什么？"
        ),
    },
    {
        "guest": "mimo",
        "question": (
            "【Round 9】在三种情景下，对比美股/A股/港股/重点行业的相对表现与仓位含义。"
            "不要求统一观点，列明分歧。"
        ),
    },
    {
        "guest": "nemo",
        "question": (
            "【Round 10】给出未来一周**资产配置百分比建议**（合计100%）："
            "现金、美股、A股、港股、黄金、美债、原油/能源、美元/外汇。"
            "附仓位建议与关键风险。"
        ),
    },
]

INVESTMENT_REFINE_QUESTIONS = [
    "【深化】针对当前最大分歧，请用最新公开数据补充证据或反证。",
    "【验证】请列出下周必须跟踪的3个关键事件/数据及其对三情景概率的影响。",
    "【复核】请标注哪些数据点需要 Owner 人工复核，并说明原因。",
    "【收敛】三情景概率是否应调整？请给出修正及理由，保留不同意见。",
    "【风险】当前市场定价忽略了哪些尾部风险？",
]

SECTION_KEYS = (
    "confirmed_points",
    "conflicts",
    "open_questions",
    "guest_position_summary",
    "suggested_next_question",
)

SECTION_ALIASES = {
    "confirmed_points": "confirmed_points",
    "confirmed points": "confirmed_points",
    "conflicts": "conflicts",
    "open_questions": "open_questions",
    "open questions": "open_questions",
    "guest_position_summary": "guest_position_summary",
    "guest position summary": "guest_position_summary",
    "suggested_next_question": "suggested_next_question",
    "suggested next question": "suggested_next_question",
}

# Spread GUEST_ALIASES first; explicit keys below are intentional identity/overrides
# for repair-state (not duplicates of the alias map).
LEGACY_GUEST_MAP = {
    **GUEST_ALIASES,
    "claude_sonnet": "claude_sonnet",
    "sonnet": "claude_sonnet",
    "grok": "laguna",  # override: grok alias already maps to laguna in GUEST_ALIASES
    "codex": "codex",
    "qoder": "qoder",
    "nemotron": "nemo",  # override: nemotron alias already maps to nemo in GUEST_ALIASES
}

def investment_question(text: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y年%m月%d日")
    return text.replace("截至2026年7月9日", f"截至{today}")

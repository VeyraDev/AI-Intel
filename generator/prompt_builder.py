"""Build prompt string for daily report from update list."""
from typing import Any, Sequence


def _title(u: Any) -> str:
    return getattr(u, "title", None) or (u.get("title") if isinstance(u, dict) else "") or ""


def _url(u: Any) -> str:
    return getattr(u, "url", None) or (u.get("url") if isinstance(u, dict) else "") or ""


def _source(u: Any) -> str:
    return getattr(u, "source", None) or (u.get("source") if isinstance(u, dict) else "") or ""


def _score(u: Any) -> float:
    return getattr(u, "score", None) or (u.get("score") if isinstance(u, dict) else 0) or 0


class PromptBuilder:
    """Build structured prompt for daily report LLM."""

    def build_daily(self, updates: Sequence[Any]) -> str:
        """Return a single prompt string summarizing the top updates for the model."""
        lines: list[str] = [
            "你是一名资深技术分析师，需要为清华大学人工智能学院的教授提供科研和产品开发的信息增量，生成每日深度前沿技术分析日报。",
            "",
            "下面提供的是今天从多个平台抓取到的科技/开源相关更新，可能来自博客文章、GitHub 项目更新、技术视频内容等。",
            "请对这些内容进行**语义理解与综合分析**，而不是简单摘抄标题。",
            "",
            "【写作目标】",
            "1. 生成一篇 **约 3500 字左右的中文日报**（可以略有上下浮动，以内容完整为主）。",
            "2. 基于抓取内容做 **深度理解与二次加工**，给出有洞见的总结，而不是罗列清单。",
            "3. 帮读者回答：今天技术圈有哪些值得关注的趋势、项目和观点？为什么重要？",
            "",
            "【写作结构建议（可微调，但需结构清晰）】",
            "1. 今日概览：用 1~2 段，对整体趋势做高层总结。",
            "2. 关键主题：按照 2~4 个主题组织（例如：大模型与 Agent、开发者工具链、编程语言/运行时、开源生态等），",
            "   - 每个主题先给出一句话主题总结；",
            "   - 再结合下面的更新条目，说明这些信息在该主题下分别代表了什么动向或机会。",
            "3. 深度点评：选择 2~3 条最有代表性的内容（可以是文章、项目或视频），",
            "   - 解释其核心贡献或观点；",
            "   - 分析其对开发者/团队可能带来的影响（如生产力提升、架构演进、新能力等）；",
            "   - 如有合适，可给出实践建议或注意事项。",
            "4. 行动建议：给出 3~5 条面向开发者的可执行建议（例如「建议关注/试用某项目」「适合哪些团队场景」等）。",
            "",
            "【写作要求】",
            "- 语言风格：理性、克制、偏专业点评，而不是营销文案。",
            "- 信息来源：分析必须 **严格基于下方提供的更新内容**，可以做合理推理，但不要凭空捏造具体事实。",
            "- 引用方式：在正文中适当引用项目/文章名称即可，不必堆砌所有链接；可以在需要时提及「某 GitHub 仓库」「某技术博客」等。",
            "- 读者画像：清华大学人工智能学院的教授，需要获取科研和产品开发的信息增量，希望快速把握趋势与重点。",
            "",
            "下面是「今日抓取到的更新列表」（供你理解与引用）：",
            "",
            "=== 更新列表（供分析使用，不要原样照搬成清单） ===",
        ]
        for i, u in enumerate(updates, 1):
            title = _title(u)
            url = _url(u)
            source = _source(u)
            score = _score(u)
            lines.append(f"{i}. 标题: {title}")
            if source:
                lines.append(f"   来源: {source}")
            if url:
                lines.append(f"   链接: {url}")
            lines.append(f"   相关性得分: {score:.1f}")
        lines.append("")
        lines.append("=== 请根据以上更新，生成一篇结构清晰、约 3500 字的中文技术情报日报 ===")
        return "\n".join(lines)

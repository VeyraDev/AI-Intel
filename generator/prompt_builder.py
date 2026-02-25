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
            "1. 生成一篇 **约 3000 字左右的中文日报**（可以略有上下浮动，以内容完整为主）。",
            "2. 基于抓取内容做 **深度理解与二次加工**，给出有洞见的总结，而不是罗列清单。",
            "3. 帮读者回答：今天技术圈有哪些值得关注的趋势、项目和观点？为什么重要？",
            "",
            "【写作结构建议（可微调，但需结构清晰）】",
            "1. 今日概览：用 1~2 段，对整体趋势做高层总结。",
            "2. 主题聚类分析：按照 2~4 个**具体且可验证**的主题组织（例如：\"系统提示词与技能编排工具\"、\"金融数据分析开源终端\"、\"RAG 知识索引组件\" 等），而不是泛泛的\"AI 应用工程化\"这类大而空的口号。",
            "   - 每个主题必须由 **至少 2 条以上更新** 共同支撑；如果某条更新比较孤立，请放入最后的「其他值得关注的散点」小节，而不是强行单独立一个大主题。",
            "   - 在每个主题下，请明确指出该主题主要由哪些更新条目支撑（可以用「对应条目：#1、#3、#5」这种方式引用列表编号），解释它们之间的内在联系。",
            "   - 主题命名请尽量具体、贴近实际技术/场景，控制在 8~15 个汉字，例如「GitHub 项目协作智能分析工具」而不是「开发者工具链智能化」。",
            "3. 深度点评：选择 2~3 条最有代表性的内容（可以是文章、项目或视频），",
            "   - 解释其核心贡献或观点；",
            "   - 分析其对开发者/团队可能带来的影响（如生产力提升、架构演进、新能力等）；",
            "   - 如有合适，可给出实践建议或注意事项。",
            "4. 行动建议：给出 3~5 条面向开发者的可执行建议（例如「建议关注/试用某项目」「适合哪些团队场景」等）。",
            "",
            "【写作要求】",
            "- 语言风格：理性、克制、偏专业点评，而不是营销文案。",
            "- 主题粒度：禁止只给出抽象、泛化的主题（如「AI 工程化」「垂直领域与工作流重构」而缺乏具体支撑），每个主题都要能够从具体的更新条目中直接抽象出来。",
            "- 信息来源：分析必须 **严格基于下方提供的更新内容**，可以做合理推理，但不要凭空捏造具体事实或虚构不存在的项目。",
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
        lines.append("=== 请根据以上更新，生成一篇结构清晰、主题聚类具体且有据可依、约 3000 字的中文技术情报日报 ===")
        return "\n".join(lines)

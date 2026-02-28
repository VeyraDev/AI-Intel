"""Build prompt string for daily report.

兼容两种输入：
- 旧版：直接基于 updates 列表（dict 或 Update 对象）构造 prompt；
- 新版：基于统一的 Signal 列表构造更结构化、贴合需求文档的日报 prompt。
"""
from typing import Any, Iterable, Sequence

from models.signal import Signal


def _title(u: Any) -> str:
    return getattr(u, "title", None) or (u.get("title") if isinstance(u, dict) else "") or ""


def _url(u: Any) -> str:
    return getattr(u, "url", None) or (u.get("url") if isinstance(u, dict) else "") or ""


def _source(u: Any) -> str:
    return getattr(u, "source", None) or (u.get("source") if isinstance(u, dict) else "") or ""


def _score(u: Any) -> float:
    return getattr(u, "score", None) or (u.get("score") if isinstance(u, dict) else 0) or 0


def _summary(u: Any) -> str:
    return getattr(u, "summary", None) or (u.get("summary") if isinstance(u, dict) else "") or ""


def _topics(u: Any) -> str:
    topics = getattr(u, "topics", None) or (u.get("topics") if isinstance(u, dict) else []) or []
    if not isinstance(topics, (list, tuple)):
        return ""
    return ", ".join(str(t) for t in topics if t)


def _metrics(u: Any) -> dict:
    metrics = getattr(u, "metrics", None) or (u.get("metrics") if isinstance(u, dict) else {}) or {}
    return metrics if isinstance(metrics, dict) else {}


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

    def build_daily_from_signals(
        self,
        signals: Iterable[Signal],
        trend_stats: dict | None = None,
        context: dict | None = None,
    ) -> str:
        """基于统一 Signal 列表构造新版日报 Prompt。

        结构严格对齐 docs/requirements-daily-report.md 中约定的 5 大部分。
        """
        trend_stats = trend_stats or {}
        context = context or {}

        today = (context or {}).get("today") or ""
        lines: list[str] = [
            "你是一名资深技术分析师，需要为人工智能方向的科研人员与产品/工程负责人生成每日深度前沿技术分析日报。",
            "",
            "【输出规范（必须遵守）】",
            "1. **不要**以「好的，我将……」、「下面为您生成……」等任何开场白开头，**直接**从日报标题开始输出正文。",
            "2. 日报**第一行**必须是标题，格式严格为：**# AI-Intel 日报 · " + (today or "YYYY-MM-DD") + "**（若下方提供了「今日日期」则使用该日期，否则用 YYYY-MM-DD 占位）。",
            "3. 从第二行起即为正文内容，无需任何前缀或寒暄。",
            "",
            "【写作目标】",
            "1. 生成一篇结构清晰、可直接用于决策参考的中文技术日报，而不是简单的信息清单，",
            "   全文字数目标为 **约 3000 字左右**（可以略有浮动，但不要明显少于 2500 字）。",
            "2. 基于输入的多源信号（GitHub 项目、论文/博客、视频等），总结今日/近期的关键主题、重要进展和可执行的行动建议。",
            "3. 日报应同时服务于：科研选题与跟进、工程实践方向选择、产品/功能灵感捕捉。",
            "",
            "【篇幅与信号比例（必须遵守）】",
            "- **今日总览、关键进展清单、趋势与判断、今日可实践清单**等正文分析**不得引用或分析视频内容**；",
            "  视频**仅**在最后第 5 部分「视频精选区」中介绍，正文其他小节不要出现对视频的点评或引用。",
            "- 主体分析（今日总览、关键进展、趋势与判断）的篇幅须与下方**非视频**信号（code/blog/paper）的数量比例一致，围绕 GitHub/论文/博客展开。",
            "- 禁止在「今日总览」「关键进展」「趋势与判断」中提及或分析任何 type=video 的条目。",
            "",
            "【整体结构（请严格按照以下 5 个部分输出，使用 Markdown 二级/三级标题）】",
            "1. 今日总览：用 1~2 段总结今天（或最近数日）最值得关注的 3~5 个主题（**仅基于非视频信号**）。",
            "2. 关键进展清单：分为「科研向」与「工程 & 产品向」两小节，列出各 3~7 条重点进展（**不包含视频**）。",
            "3. 趋势与判断：结合近 7/30 天的信号，指出哪些主题在升温/降温（**不引用视频**）。",
            "4. 今日可实践清单：输出 3~5 条明确的、可在 0.5~2 小时内开始执行的行动项（标明 [科研]/[工程]/[产品]）。",
            "5. 视频精选区：**仅在此小节**从视频类信号中挑选若干条，逐条介绍「看完这一条大致能收获什么」。",
            "",
            "【写作要求】",
            "- 语言风格：理性、克制、以专业分析为主，避免营销腔和空洞口号。",
            "- 主题和判断必须能在输入信号中找到直接或间接依据，禁止凭空捏造具体项目/论文/产品。",
            "- 引用具体项目 / 论文 / 视频时，请尽量使用 **Markdown 链接形式** `[标题](URL)`，",
            "  其中 URL 必须来自下面输入信号中的链接字段，这样前端渲染后可以点击跳转。",
            "- 每个推荐条目都要尽量回答：它解决什么问题？适合谁？对科研/工程/产品有什么潜在影响？",
            "- 行动建议要具体，例如「阅读某论文并思考是否可替换当前模块」、「尝试某 GitHub 项目作为内部工具原型」等。",
            "",
            "【输入数据说明】",
            "下面提供的是结构化的「信号列表」，每一条代表一条来自 GitHub/论文/博客/视频等的数据点，字段含义如下：",
            "- id: 唯一标识；",
            "- type: 信号类型（paper/code/video/blog/news/other 等）；",
            "- source: 来源平台（github/arxiv/rss/bilibili/other 等）；",
            "- title: 标题；",
            "- summary: 简要摘要（如有）；",
            "- url: 链接地址；",
            "- published_at: 发布时间；",
            "- topics: 主题标签列表；",
            "- score: 综合得分（相关度/热度/时效性等）；",
            "- metrics: 其他指标（如 stars_today、views、github_refs 等）。",
            "",
            "**今日日期（日报标题必须使用此日期）**：" + (today or "未提供，请用当前日期 YYYY-MM-DD") + "",
            "",
            "=== 信号列表（供分析使用，不要原样照搬成清单） ===",
        ]

        for i, sig in enumerate(signals, 1):
            sig_dict = sig.to_dict()
            title = sig_dict.get("title") or ""
            url = sig_dict.get("url") or ""
            sig_type = sig_dict.get("type") or ""
            source = sig_dict.get("source") or ""
            published_at = sig_dict.get("published_at") or ""
            score = float(sig_dict.get("score") or 0.0)
            topics_str = ", ".join(sig_dict.get("topics") or [])
            summary = sig_dict.get("summary") or ""
            metrics = sig_dict.get("metrics") or {}

            lines.append(f"{i}. 标题: {title}")
            if sig_type:
                lines.append(f"   类型: {sig_type}")
            if source:
                lines.append(f"   来源: {source}")
            if topics_str:
                lines.append(f"   主题: {topics_str}")
            if published_at:
                lines.append(f"   时间: {published_at}")
            if url:
                lines.append(f"   链接: {url}")
            if summary:
                s = str(summary).strip()
                if len(s) > 420:
                    s = s[:420].rstrip() + "…"
                lines.append(f"   摘要: {s}")
            if metrics:
                # 只展示对理解价值较高的核心指标
                metrics_str_parts: list[str] = []
                if "stars_today" in metrics:
                    metrics_str_parts.append(f"stars_today={metrics['stars_today']}")
                if "github_refs" in metrics and metrics["github_refs"]:
                    metrics_str_parts.append(f"github_refs={len(metrics['github_refs'])} 个")
                extra = [k for k in metrics.keys() if k not in {"stars_today", "github_refs"}]
                if extra:
                    metrics_str_parts.append("其他=" + ", ".join(extra))
                if metrics_str_parts:
                    lines.append(f"   指标: " + "；".join(metrics_str_parts))
            lines.append(f"   综合得分: {score:.1f}")

        if trend_stats:
            lines.append("")
            lines.append("=== 趋势统计（供参考使用） ===")
            rising = trend_stats.get("rising_topics") or []
            falling = trend_stats.get("falling_topics") or []
            stable = trend_stats.get("stable_topics") or []
            if rising:
                lines.append(f"- 升温主题: {', '.join(rising)}")
            if falling:
                lines.append(f"- 降温主题: {', '.join(falling)}")
            if stable:
                lines.append(f"- 相对稳定: {', '.join(stable)}")

        lines.append("")
        lines.append("=== 请基于上述信号与趋势信息，按照约定的 5 个部分，生成一篇结构化的中文技术日报 ===")
        return "\n".join(lines)

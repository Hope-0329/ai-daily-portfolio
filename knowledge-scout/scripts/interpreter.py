"""深度解读引擎 v2.0

对精选文章进行结构化解读。
v2.0 改进：
1. 输入清洗：进入解读前先过滤 CSS/JS/HTML 残片
2. 框架提取：增加置信度校验，降低误匹配
3. 错误处理：每个子函数都防崩溃
"""

import re
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class DeepInsight:
    """深度解读结果"""
    title: str
    source: str
    url: str = ""
    thesis: str = ""
    frameworks: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    takeaways: list[str] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    content_length: int = 0
    quality_score: float = 0.0
    category: str = ""
    interpreted_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ── 输入清洗 ──

def _sanitize_content(text: str) -> str:
    """
    清洗输入正文，移除 CSS/JS/HTML 残留。
    这些残片会在框架提取、洞察提取中被误匹配。
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned = []

    # CSS/JS/HTML 噪声特征
    noise_patterns = [
        r"^\s*[.#@]?\w+[\w-]*\s*\{",          # CSS规则
        r"^\s*(function|const|let|var|import|export)\s",  # JS
        r"^\s*(window|document|console|navigator)\.", # DOM
        r"^\s*\{\s*$",                          # 裸花括号
        r"^\s*\}\s*$",
        r"^\s*\/\/",                            # 注释
        r"^\s*\/\*|\*\/",
        r"^\s*@media|@import|@keyframes",
        r"^\s*<\w+[^>]*>",                      # HTML标签
        r"^\s*;[^;]{0,10}$",                    # 裸分号
        r"^\s*\)\s*$",                          # 裸括号
        r"^\s*}\s*\)\s*$",
        r"^\s*catch\b|try\b|finally\b",
        r"^\s*\.then\(|\.catch\(|\.finally\(",
        r"^\s*async\s+function",
        r"^\s*useState|useEffect|useCallback|useMemo",
        r"^\s*return\s+\{",
        r"^\s*export\s+default",
        r"^\s*Promise\.resolve|Promise\.reject",
        r"^\s*addEventListener\(",
        r"^\s*removeEventListener\(",
        r"^\s*setTimeout|setInterval|clearTimeout",
        r"^\s*\w+\.prototype\.",
        r"^\s*Object\.defineProperty",
        r"^\s*Array\.prototype|String\.prototype",
        r"^\s*JSON\.parse|JSON\.stringify",
        r"^\s*border-radius|background-color|font-size|text-align",
        r"^\s*position:\s*(absolute|relative|fixed)",
        r"^\s*display:\s*(flex|grid|block|none)",
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 连续空行压缩
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        # 过短 + 无中文 → 大概率噪声
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", stripped))
        if cn_chars == 0 and len(stripped) < 15:
            continue

        # 噪声模式匹配
        is_noise = False
        for pattern in noise_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                is_noise = True
                break

        if not is_noise:
            cleaned.append(line)

    return "\n".join(cleaned)


# ── 文章结构解析 ──

def parse_article_structure(text: str) -> dict:
    """解析文章基本结构"""
    try:
        h2_matches = re.findall(r'(?:^|\n)#{1,3}\s+(.+)', text, re.MULTILINE)
        signals = {
            "is_long_form": len(text) > 3000,
            "is_deep": len(text) > 5000,
            "section_count": len(h2_matches),
            "paragraph_count": len(re.findall(r'\n\n+', text)) + 1,
            "has_methodology": bool(re.search(r'方法[论轮]|框架|模型|体系|步骤|流程', text)),
            "has_framework": bool(re.search(r'框架|架构|体系|全景|路线图', text)),
            "has_summary": bool(re.search(r'总结|小结|回顾|概括|综上所述', text)),
            "has_case": bool(re.search(r'案例|实践|落地|实施|部署|应用', text)),
            "has_data": bool(re.search(r'\d+%|\d+亿|\d+万|\d+倍', text)),
            "has_quote": bool(re.search(r'"[^"]{20,}"', text)),
            "has_comparison": bool(re.search(r'对比|VS|相比|不同于|区别于', text)),
            "has_action": bool(re.search(r'建议|推荐|最好|应该|可以尝试|不妨', text)),
        }
        return {"structure": {}, "signals": signals}
    except Exception:
        return {"structure": {}, "signals": {}}


def score_article_depth(text: str, title: str, source: str, url: str) -> float:
    """对文章进行深度评分 (0-10)"""
    try:
        structure = parse_article_structure(text)
        sig = structure.get("signals", {})
        score = 0.0

        if sig.get("is_deep"):
            score += 1.5
        elif sig.get("is_long_form"):
            score += 0.8
        sc = sig.get("section_count", 0)
        if sc >= 3:
            score += 0.5
        if sc >= 5:
            score += 0.5
        if sig.get("paragraph_count", 0) >= 15:
            score += 0.5
        if sig.get("has_framework"):
            score += 1.0
        if sig.get("has_methodology"):
            score += 1.0
        if sig.get("has_summary"):
            score += 0.5
        if sig.get("has_comparison"):
            score += 0.5
        if sig.get("has_data"):
            score += 1.0
        if sig.get("has_case"):
            score += 0.5
        if sig.get("has_quote"):
            score += 0.5
        if sig.get("has_action"):
            score += 1.0

        ai_keywords = [
            "AI", "Agent", "大模型", "LLM", "GPT", "人工智能",
            "智能体", "深度学习", "机器学习", "机器人", "自动化",
            "Copilot", "AIGC", "生成式", "提示词", "RAG",
        ]
        ai_score = min(1.0, sum(0.1 for kw in ai_keywords if kw.lower() in text.lower()))
        score += ai_score

        return min(10.0, score)
    except Exception:
        return 1.0


# ── 句子筛选 ──

def is_garbage_sentence(s: str) -> bool:
    """判断一句话是否无效"""
    s = s.strip()
    if len(s) < 15 or len(s) > 150:
        return True
    # URL/HTML残留
    if re.search(r'[<>]', s):
        return True
    if any(n in s.lower() for n in ['https', 'www.', '.com/', '.html', 'index.', 'cdn-', '.js', '.css', '.png', '.svg']):
        return True
    # 纯英文/数字
    if re.match(r'^[a-zA-Z0-9\s\.\,\!\?\-\(\)\[\]\{\}\;\:]+$', s):
        return True
    # 无中文
    if not re.search(r'[\u4e00-\u9fff]', s):
        return True
    # CSS/JS 关键词
    cs_noise = ['function', 'const', 'let', 'var', 'return', 'export', 'import', 'require',
                'border', 'padding', 'margin', 'display', 'position', 'font-size', 'color:',
                'background', 'width:', 'height:', 'z-index', 'opacity']
    for kw in cs_noise:
        if kw.lower() in s.lower():
            return True
    return False


def _is_valid_framework_name(name: str) -> bool:
    """校验框架名称是否像真的框架名（而非 CSS/JS 残片）"""
    if not name or len(name) < 4 or len(name) > 30:
        return False
    # 必须包含中文
    if not re.search(r'[\u4e00-\u9fff]', name):
        return False
    # 不含噪声字符串
    noise_tokens = [
        'http', 'www', '.com', '.cn', '.org',
        'function', 'const', 'var', 'let', 'return',
        'css', 'html', 'javascript', 'react', 'vue',
        'style', 'script', 'div', 'span', 'class',
        'window', 'document', 'console', 'element',
        'border', 'padding', 'margin', 'display',
        'font', 'color', 'background', 'width', 'height',
        'position', 'absolute', 'relative',
        '{', '}', '()', '=>',
    ]
    lower = name.lower()
    return not any(t in lower for t in noise_tokens)


def _is_proper_noun_prefix(prefix: str) -> bool:
    """前缀必须像专有名词：不能是量词、代词、通用形容词"""
    # 排除：含引号、括号、斜杠
    if any(c in prefix for c in '"''「」《》（）()/'):
        return False
    # 排除：以动词/副词开头的
    starts_bad = ['是', '在', '会', '要', '就', '也', '还', '可', '能',
                  '有', '被', '把', '让', '给', '对', '比', '从', '到',
                  '为', '因', '向', '按', '照', '据', '由', '与', '或',
                  '但', '而', '且', '不过', '只是', '然后', '最后',
                  '这个', '那个', '一个', '某个', '哪个', '什么',
                  '推出', '发布', '采用', '宣布', '表示', '认为',
                  '首个', '首个', '另一', '独特', '最新', '新型',
                  '可能', '应该', '需要', '准备', '正在']
    for b in starts_bad:
        if prefix.startswith(b):
            return False
    # 排除：纯数字开头（如 "3D模型" 可以，但 "123模型" 不行）
    if re.match(r'^\d{3,}', prefix):
        return False
    return True


def extract_frameworks(text: str, title: str) -> list[str]:
    """
    提取方法论框架名称。
    v2.1: 严格上下文校验，只有引入性语境中出现的才匹配。
    示例语境："提出了X模型"、"基于X框架"、"称为X体系"
    """
    try:
        frameworks = []
        fw_suffix = r'(?:框架|模型|体系|方法论|模式|架构|矩阵|公式|飞轮|漏斗|画布|地图|定律|法则|效应)'

        # 模式1: 引入语境 + 框架名
        # "提出了X模型"、"基于X框架"、"称为X方法论"
        intro_words = r'(?:提出|建立|构建|形成|打造|首创|开创|称为|称之为|称作)'
        pattern1 = re.compile(
            intro_words + r'[的]?[^。！？，,\n]{0,10}'
            r'([^\s，,。！？；;]{2,10}' + fw_suffix + r')'
        )
        for m in pattern1.finditer(text):
            fw = m.group(1).strip()
            if _is_valid_framework_name(fw) and _is_proper_noun_prefix(fw):
                frameworks.append(fw)

        # 模式2: 书名号/引号内的框架名（"《X模型》"、"X体系"）
        quoted = re.findall(
            r'[《「"](.{2,15}' + fw_suffix + r')[》」"]', text)
        for fw in quoted:
            if _is_valid_framework_name(fw):
                frameworks.append(fw)

        # 模式3: N步/N大/N阶段 方法论（这些本身就是框架性术语）
        step_pattern = re.compile(
            r'([一二两三四五六七八九十百千万\d]+'
            r'(?:个|大|步|条|项|阶段|层|维度|要素|原则|策略)'
            r'(?:[^\s，。]{0,20}' + fw_suffix + r')?)'
        )
        for m in step_pattern.finditer(text):
            fw = m.group(0).strip()
            if len(fw) >= 6 and _is_valid_framework_name(fw):
                frameworks.append(fw)

        # 模式4: "从X到Y" 转化（但要求是从概念到概念）
        transforms = re.findall(
            r'(从[\u4e00-\u9fff]{2,10}到[\u4e00-\u9fff]{2,20})', text)
        for t in transforms[:3]:
            if len(t) >= 8:
                frameworks.append(t)

        # 去重 + 最终过滤
        seen = set()
        unique = []
        for fw in frameworks:
            fw = fw.strip()
            if not _is_valid_framework_name(fw):
                continue
            if not _is_proper_noun_prefix(fw):
                continue
            # 额外：排除以"的"结尾的残片
            if fw.endswith('的'):
                continue
            key = fw[:8]
            if key not in seen:
                seen.add(key)
                unique.append(fw)

        return unique[:5]
    except Exception:
        return []


def extract_insights(text: str, title: str) -> list[str]:
    """提取关键洞察（完整、有深度的句子）"""
    try:
        clean = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'[。！？]', clean)
        candidates = []

        for sent in sentences:
            if is_garbage_sentence(sent):
                continue

            weight = 0
            for kw in ['但是', '然而', '不过', '却', '反而', '并不', '并非', '本质上']:
                if kw in sent:
                    weight += 3
            for kw in ['不是', '与其', '相比', '区别于', '不同于']:
                if kw in sent:
                    weight += 2
            for kw in ['关键', '核心', '本质', '真正', '其实', '最重要', '根本原因']:
                if kw in sent:
                    weight += 2
            for kw in ['在于', '意味着', '原因是', '背后是']:
                if kw in sent:
                    weight += 1

            if weight >= 2:
                candidates.append((sent, weight))

        candidates.sort(key=lambda x: -x[1])
        return [c[0] for c in candidates[:5]]
    except Exception:
        return []


def generate_takeaways(frameworks: list[str], insights: list[str], text: str, title: str) -> list[str]:
    """生成行动启发"""
    try:
        takeaways = []

        for fw in frameworks[:3]:
            if re.search(r'[三一二三四五\d]步', fw):
                takeaways.append(f"📋 方法论复制: {fw}，可直接套用到工作流程设计")
            elif ('框架' in fw or '模型' in fw or '体系' in fw) and len(fw) >= 6:
                takeaways.append(f"🧩 知识入库: 「{fw}」可作为分析工具")
            elif '从' in fw and '到' in fw:
                takeaways.append(f"🔄 转化思路: {fw}")

        for ins in insights[:3]:
            if any(kw in ins for kw in ['Agent', '智能体', 'AI', '大模型', '自动化', '工作流']):
                takeaways.append(f"💡 {ins}")
            elif any(kw in ins for kw in ['管理', '组织', '团队', '流程', '效率', '产品', '用户']):
                takeaways.append(f"👥 {ins}")

        return takeaways[:3]
    except Exception:
        return []


def find_connections(text: str, title: str, source: str) -> list[str]:
    """找到与已有知识的关联"""
    connections = []
    if any(kw in title for kw in ['Agent', '智能体']):
        connections.append("🔗 关联知识: AI Agent 落地方法论 → 可对照 Skill 设计经验")
    if any(kw in title for kw in ['模型', '大模型', 'LLM', 'GPT']):
        connections.append("🔗 关联知识: 大模型产品矩阵 → 可更新工具选型笔记")
    if any(kw in text for kw in ['短剧', 'AIGC', '视频生成']):
        connections.append("🔗 关联知识: AI 短剧制作 → 可补充到制作方案中")
    return connections[:3]


def classify_article(text: str, title: str) -> str:
    """对文章进行主题分类"""
    try:
        categories = {
            "AI Agent与工程": ["Agent", "智能体", "Skill", "Claude", "Copilot", "自动化", "SOP"],
            "AI 商业与趋势": ["融资", "IPO", "上市", "估值", "赛道", "创投", "DeepSeek",
                            "OpenAI", "Anthropic", "月之暗面", "阶跃", "智谱"],
            "企业数字化转型": ["数字化", "转型", "企业", "组织", "管理", "流程", "供应链"],
            "AI 创作与内容": ["短剧", "AIGC", "视频生成", "绘画", "音乐", "创作", "内容"],
            "知识管理与效率": ["知识管理", "Obsidian", "效率", "工作流", "工具", "笔记"],
            "人形机器人与硬件": ["机器人", "人形", "硬件", "具身智能", "AI眼镜", "触觉"],
        }
        full_text = f"{title} {text[:2000]}"
        scores = {}
        for cat, keywords in categories.items():
            sc = sum(1 for kw in keywords if kw.lower() in full_text.lower())
            if sc > 0:
                scores[cat] = sc
        if not scores:
            return "跨领域综合"
        return max(scores, key=scores.get)
    except Exception:
        return "跨领域综合"


def extract_thesis(text: str, title: str) -> str:
    """提取一句话核心观点"""
    try:
        clean = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'[。！？]', clean)

        best = ""
        best_score = 0
        for sent in sentences:
            if is_garbage_sentence(sent):
                continue
            score = 0
            for kw in ['核心', '本质', '关键在于', '最重要', '根本', '这意味着']:
                if kw in sent:
                    score += 3
            for kw in ['不是', '而是', '其实', '真正', '本质上']:
                if kw in sent:
                    score += 2
            tech_words = sum(1 for t in ['参数', '代码', 'API', 'SDK', '安装', '配置', '下载'] if t in sent)
            score -= tech_words * 2

            if score > best_score and len(sent) >= 20:
                best_score = score
                best = sent

        return best if best else f"📄 {title}"
    except Exception:
        return f"📄 {title}"


# ── 主入口 ──

def interpret_article(article: dict) -> DeepInsight | None:
    """
    对单篇文章进行深度解读

    v2.0: 输入先清洗，防止 CSS/JS 残片污染结果
    """
    title = article.get("title", "无标题")
    content = article.get("content", "")
    source = article.get("source", "")
    url = article.get("url", "")

    if not content:
        return None

    # ── 输入清洗：关键步骤！──
    cleaned = _sanitize_content(content)

    if not cleaned or len(cleaned) < 200:
        return None

    depth_score = score_article_depth(cleaned, title, source, url)
    if depth_score < 1.0:  # 降低阈值，清洗后有效内容可能偏短但仍可用
        return None

    try:
        return DeepInsight(
            title=title,
            source=source,
            url=url,
            thesis=extract_thesis(cleaned, title),
            frameworks=extract_frameworks(cleaned, title),
            insights=extract_insights(cleaned, title),
            takeaways=generate_takeaways(
                extract_frameworks(cleaned, title),
                extract_insights(cleaned, title),
                cleaned, title
            ),
            connections=find_connections(cleaned, title, source),
            content_length=len(content),
            quality_score=round(depth_score, 1),
            category=classify_article(cleaned, title),
        )
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    test_text = """
Agent 可靠性的工程解法：从 Skillify 看持续改进机制

在企业级 AI Agent 的落地过程中，可靠性是最被忽视但也最致命的瓶颈。

本文提出了 Agent 可靠性治理的三步法框架：
第一步：定义成功标准，建立可量化的质量门禁
第二步：持续监控与反馈循环，通过 Skillify 实现自动化测试
第三步：增量改进与版本管理，确保每次更新都不退化

关键洞察：Agent 的可靠性问题本质上是工程问题，不是模型问题。
大多数团队失败的原因，不是模型不够强，而是没有建立系统化的质量保障体系。

对于企业来说，Agent 可靠性治理不是可选项，而是规模化部署的前提。
"""
    article = {
        "title": "Agent 可靠性的工程解法",
        "content": test_text,
        "source": "AI前线",
        "url": "https://example.com/test"
    }
    result = interpret_article(article)
    if result:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print("评分不足，跳过")

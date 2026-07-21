# -*- coding: utf-8 -*-
"""
knowledge-scout v4.0 — 深度解读引擎
=====================================
将一篇文章转化为深度解读笔记，写入 Obsidian 知识库。

流程:
  1. ContentFetcher    — 抓取原文全文（带重试/降级）
  2. ArticleClassifier — 判断类型→选模板 + 知识域→定路径
  3. YAMLBuilder       — 构建 frontmatter（knowledge_id, tags, domain...）
  4. PromptBuilder     — 构建 LLM 提示词
  5. ObsidianWriter    — 写入笔记 + 建双链
  6. MOCUpdater        — 更新知识地图索引

设计原则:
  - 所有 LLM 生成由 Agent 完成，本模块只做"准备"和"写入"
  - 容错：任何一步失败不阻塞整体
  - 幂等：重复运行不产生重复笔记
"""

import io
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 编码 ──
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# ── 配置 ──
CONFIG = {
    "obsidian_vault": r"D:\肠肠的Obsidian\肠肠的obsidian",
    "template_dir": "20-知识资产/模板/21-AI与智能体/日报模板",
    "knowledge_base": "20-知识资产",
    "moc_dir": "20-知识资产",
    "fetch_timeout": 12,
    "max_content_chars": 8000,
    "max_retries": 2,
}

# ── HTTP 会话 ──
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})
retry = Retry(total=2, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503])
_session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=10))

# ═══════════════════════════════════════════
# 分类映射表
# ═══════════════════════════════════════════

# 模板类型关键词（用于自动分类）
TEMPLATE_PATTERNS = {
    "C01-CASE": {
        "keywords": [
            "发布", "融资", "收购", "上市", "IPO", "裁员", "重组", "任命",
            "战略", "布局", "押注", "转型", "拆分", "合并", "合作",
            "宣布", "推出", "上线", "公测", "内测", "闭源", "开源",
        ],
        "type_cn": "案例",
        "folder": "案例",
    },
    "C02-INDUSTRY": {
        "keywords": [
            "趋势", "风向", "格局", "赛道", "展会", "大会", "峰会",
            "对比", "竞争", "混战", "三国杀", "谁才是", "终极",
            "新风向", "探展", "直击", "观察", "盘点", "年",
        ],
        "type_cn": "动态",
        "folder": "动态",
    },
    "C03-METHOD": {
        "keywords": [
            "方法论", "框架", "模型", "范式", "原理", "机制",
            "如何", "怎么", "指南", "教程", "最佳实践", "工作流",
            "思维模型", "公式", "架构", "设计模式", "算法详解",
        ],
        "type_cn": "方法",
        "folder": "方法",
    },
    "C04-PRODUCT": {
        "keywords": [
            "评测", "体验", "上手", "开箱", "测评", "实测",
            "工具", "插件", "App", "软件", "硬件", "设备",
            "产品", "参数", "性能", "跑分", "对比评测",
        ],
        "type_cn": "案例",
        "folder": "案例",
    },
}

# 知识域关键词（编号对应 Obsidian 目录）
DOMAIN_PATTERNS = {
    "21-AI与智能体": [
        "AI", "人工智能", "大模型", "LLM", "GPT", "Claude", "Agent",
        "智能体", "具身智能", "机器人", "深度学习", "机器学习",
        "神经网络", "Transformer", "AIGC", "多模态", "RLHF",
    ],
    "22-内容创作": [
        "短视频", "抖音", "小红书", "B站", "内容", "创作",
        "写作", "视频", "剪辑", "文案", "自媒体", "IP",
        "直播", "编剧", "剧本", "小说", "短剧",
    ],
    "23-商业与管理": [
        "商业模式", "战略", "管理", "组织", "OKR", "KPI",
        "增长", "营销", "品牌", "产品经理", "运营", "SaaS",
        "创业", "融资", "IPO", "上市", "独角兽", "估值",
    ],
    "24-金融与投资": [
        "投资", "基金", "股票", "A股", "港股", "美股",
        "量化", "交易", "理财", "保险", "银行", "支付",
        "加密货币", "比特币", "DeFi", "央行", "利率",
    ],
    "26-信息科学与技术": [
        "芯片", "GPU", "算力", "云计算", "数据库", "开源",
        "GitHub", "编程", "代码", "架构", "系统", "网络",
        "安全", "隐私", "加密", "边缘计算", "IoT",
    ],
}


# ═══════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════

@dataclass
class DeepCandidate:
    """深度解读候选条目"""
    title: str
    url: str
    summary: str = ""
    platform: str = ""
    score: float = 0.0
    # 分类结果
    template_id: str = ""
    knowledge_type: str = ""   # 动态/案例/方法
    domain: str = ""           # 21-AI与智能体
    domain_name: str = ""      # AI与智能体
    subdomains: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    # 内容
    full_content: str = ""
    content_fetched: bool = False
    # 元数据
    knowledge_id: str = ""
    yaml_frontmatter: str = ""
    prompt: str = ""
    # 输出
    interpretation: str = ""
    output_path: str = ""


# ═══════════════════════════════════════════
# 1. 内容获取器
# ═══════════════════════════════════════════

class ContentFetcher:
    """抓取文章全文"""

    SKIP_DOMAINS = [
        "zhihu.com", "weixin.qq.com", "mp.weixin.qq.com",
    ]

    def __init__(self, timeout: int = None, max_chars: int = None):
        self.timeout = timeout or CONFIG["fetch_timeout"]
        self.max_chars = max_chars or CONFIG["max_content_chars"]

    def fetch(self, url: str) -> tuple[str, bool]:
        """
        获取文章全文。
        Returns: (content, success)
        """
        if not url or any(d in url for d in self.SKIP_DOMAINS):
            return "", False

        for attempt in range(CONFIG["max_retries"]):
            try:
                resp = _session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    stream=True,
                )
                resp.raise_for_status()

                ct = resp.headers.get("content-type", "")
                if "html" not in ct and "text" not in ct:
                    return "", False

                # 流式读取，限制大小
                body = b""
                for chunk in resp.iter_content(chunk_size=8192):
                    body += chunk
                    if len(body) > self.max_chars * 4:
                        break
                resp.close()

                # 解码
                text = self._decode_body(body, resp)
                if not text:
                    return "", False

                # 提取正文
                clean = self._extract_text(text)
                clean = clean[:self.max_chars]

                if len(clean) < 100:
                    return "", False

                return clean, True

            except requests.Timeout:
                print(f"    ⚠ 超时 (尝试 {attempt+1}/{CONFIG['max_retries']})")
            except requests.ConnectionError:
                print(f"    ⚠ 连接失败 (尝试 {attempt+1}/{CONFIG['max_retries']})")
                break  # 连接错误不重试
            except Exception as e:
                print(f"    ⚠ 抓取失败: {e}")
                break

        return "", False

    def _decode_body(self, body: bytes, resp) -> str:
        """智能解码"""
        ct = resp.headers.get("content-type", "")
        # 尝试从响应头获取编码
        enc_match = re.search(r'charset[=]\s*([\w-]+)', ct)
        encoding = enc_match.group(1) if enc_match else None

        if encoding:
            try:
                return body.decode(encoding, errors="ignore")
            except Exception:
                pass

        # 尝试从 HTML meta 获取
        head = body[:2000]
        head_text = head.decode("utf-8", errors="ignore")
        meta_enc = re.search(
            r'<meta[^>]+charset[=]["\']?([\w-]+)', head_text, re.IGNORECASE
        )
        if meta_enc:
            try:
                return body.decode(meta_enc.group(1), errors="ignore")
            except Exception:
                pass

        # fallback
        for enc in ["utf-8", "gbk", "gb2312", "gb18030"]:
            try:
                decoded = body.decode(enc)
                if len(decoded) > 100:
                    return decoded
            except Exception:
                continue

        return body.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_text(html: str) -> str:
        """从 HTML 提取正文"""
        # 移除 script/style
        html = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # 移除 HTML 注释
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        # 移除标签
        text = re.sub(r'<[^>]+>', ' ', html)
        # 解码 HTML 实体
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
        text = text.replace('&ldquo;', '"').replace('&rdquo;', '"')
        text = text.replace('&mdash;', '—').replace('&ndash;', '–')
        # 合并空白
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        # 移除空行开头的空白
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        return text.strip()


# ═══════════════════════════════════════════
# 2. 文章分类器
# ═══════════════════════════════════════════

class ArticleClassifier:
    """判断文章类型→选模板 + 知识域→定路径"""

    def classify(self, candidate: DeepCandidate) -> DeepCandidate:
        """对候选条目进行分类"""
        text = f"{candidate.title} {candidate.summary} {candidate.full_content[:2000]}"

        # 模板类型
        candidate.template_id = self._classify_template(text)
        candidate.knowledge_type = self._get_knowledge_type(candidate.template_id)

        # 知识域
        candidate.domain, candidate.domain_name = self._classify_domain(text)

        # 子域（从正文提取具体领域）
        candidate.subdomains = self._extract_subdomains(text, candidate.domain)

        # 标签
        candidate.tags = self._extract_tags(text, candidate)

        # knowledge_id
        candidate.knowledge_id = self._make_knowledge_id(candidate)

        return candidate

    def _classify_template(self, text: str) -> str:
        """基于关键词打分选择模板"""
        scores = {}
        for tid, cfg in TEMPLATE_PATTERNS.items():
            score = sum(1 for kw in cfg["keywords"] if kw in text)
            scores[tid] = score

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "C02-INDUSTRY"  # 默认行业分析
        return best

    def _get_knowledge_type(self, template_id: str) -> str:
        return TEMPLATE_PATTERNS.get(template_id, {}).get("type_cn", "动态")

    def _classify_domain(self, text: str) -> tuple:
        """返回 (domain_code, domain_name)"""
        scores = {}
        for dname, keywords in DOMAIN_PATTERNS.items():
            scores[dname] = sum(1 for kw in keywords if kw in text)

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "21-AI与智能体", "AI与智能体"
        return best, best.split("-", 1)[1]

    def _extract_subdomains(self, text: str, domain: str) -> list:
        """从正文提取子域"""
        if domain == "21-AI与智能体":
            sub_map = {
                "大模型": ["大模型", "LLM", "GPT", "Claude", "语言模型"],
                "具身智能": ["具身智能", "机器人", "人形", "四足"],
                "AI Agent": ["Agent", "智能体", "Multi-Agent"],
                "AIGC": ["AIGC", "生成", "文生图", "文生视频"],
                "AI硬件": ["芯片", "GPU", "算力", "传感器", "硬件"],
                "多模态": ["多模态", "视觉", "语音", "图像"],
                "AI+医疗": ["医疗", "诊断", "中医", "健康"],
                "AI安全": ["安全", "对齐", "红队", "越狱"],
            }
        elif domain == "23-商业与管理":
            sub_map = {
                "战略管理": ["战略", "转型", "布局", "竞争"],
                "组织管理": ["组织", "团队", "OKR", "管理"],
                "产品管理": ["产品", "PMF", "MVP", "迭代"],
            }
        else:
            return []

        matched = [name for name, kws in sub_map.items()
                    if any(kw in text for kw in kws)]
        return matched[:3]

    def _extract_tags(self, text: str, candidate: DeepCandidate) -> list:
        """提取标签"""
        tags_set = set()

        # 实体标签
        entities = [
            "OpenAI", "Anthropic", "Google", "Meta", "微软", "腾讯",
            "阿里", "字节", "百度", "华为", "宇树", "智元", "阶跃",
            "月之暗面", "百川", "智谱", "DeepSeek", "豆包", "通义",
            "WAIC", "ICML", "NeurIPS", "CVPR",
        ]
        for e in entities:
            if e.lower() in text.lower():
                tags_set.add(e)

        # 来源标签
        tags_set.add(candidate.platform)

        # 模板类型标签
        for tid, cfg in TEMPLATE_PATTERNS.items():
            if candidate.template_id == tid:
                tags_set.add(cfg["type_cn"])
                break

        return sorted(tags_set)[:10]

    def _make_knowledge_id(self, c: DeepCandidate) -> str:
        """生成唯一 knowledge_id"""
        date = datetime.now().strftime("%Y")
        domain_short = c.domain.split("-")[1][:6] if "-" in c.domain else c.domain[:6]
        # 用标题 hash 确保唯一
        title_hash = hashlib.md5(c.title.encode("utf-8")).hexdigest()[:6]
        return f"{date}-{domain_short}-{title_hash}"


# ═══════════════════════════════════════════
# 3. YAML 构建器
# ═══════════════════════════════════════════

class YAMLBuilder:
    """构建 Obsidian 笔记的 YAML frontmatter"""

    def build(self, c: DeepCandidate) -> str:
        """生成完整的 YAML frontmatter"""
        today = datetime.now().strftime("%Y-%m-%d")

        lines = [
            "---",
            f'knowledge_id: "{c.knowledge_id}"',
            f'type: "{c.knowledge_type}"',
            f'domain: "{c.domain_name}"',
            f"subdomain: {json.dumps(c.subdomains, ensure_ascii=False)}",
            f"tags: {json.dumps(c.tags, ensure_ascii=False)}",
            f'created: "{today}"',
            f'updated: "{today}"',
            f'source: "{c.url}"',
            f'source_type: "行业媒体-{c.platform}"',
            f"depth_score: {c.score:.1f}",
            "---",
            "",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 4. 双链建议引擎
# ═══════════════════════════════════════════

class LinkSuggester:
    """
    扫描 Obsidian 知识库中已有笔记，为 DeepCandidate 推荐 [[双链]]。

    三层匹配策略:
      1. 标题关键词匹配 — 候选标题/标签 vs 已有笔记标题
      2. 知识域匹配 — 同域笔记优先
      3. 标签共现 — 标签重合度高的笔记
    """

    MAX_SUGGESTIONS = 8  # 最多推荐 8 条双链

    def __init__(self, vault_path: str = None):
        self.vault = Path(vault_path or CONFIG["obsidian_vault"])
        self._cache: dict = {}  # title → (path, frontmatter_tags)
        self._loaded = False

    def _load_index(self):
        """懒加载：遍历知识库建立标题索引"""
        if self._loaded:
            return

        kb = self.vault / CONFIG["knowledge_base"]
        if not kb.exists():
            self._loaded = True
            return

        for md_file in kb.rglob("*.md"):
            # 跳过 MOC 和索引文件（以 _ 开头）
            if md_file.stem.startswith("_"):
                continue
            # 跳过模板目录
            if "模板" in str(md_file):
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
                # 提取 YAML frontmatter 中的 tags
                tags = []
                yaml_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if yaml_match:
                    yaml_text = yaml_match.group(1)
                    tag_match = re.search(r'tags:\s*\[(.*?)\]', yaml_text)
                    if tag_match:
                        tags = [t.strip().strip('"\'') for t in tag_match.group(1).split(",")]

                rel_path = str(md_file.relative_to(self.vault)).replace("\\", "/")
                # 标题 = 文件名去掉 .md 和版本号后缀
                title = re.sub(r'_v\d+$', '', md_file.stem)
                self._cache[title] = {
                    "rel_path": rel_path,
                    "tags": tags,
                    "stem": md_file.stem,
                }
            except Exception:
                continue

        self._loaded = True

    def suggest(self, c: "DeepCandidate") -> list[dict]:
        """
        为候选文章推荐 [[双链]]。

        Returns:
            [{title, rel_path, stem, score, reason}, ...]
        """
        self._load_index()

        if not self._cache:
            return []

        scored = []

        # 候选的搜索词
        candidate_terms = self._tokenize(c.title)
        candidate_tags = set(c.tags)

        for title, info in self._cache.items():
            score = 0
            reasons = []

            # 1. 标题关键词匹配
            note_terms = self._tokenize(title)
            common_terms = candidate_terms & note_terms
            if common_terms:
                score += len(common_terms) * 3
                reasons.append(f"关键词匹配: {', '.join(sorted(common_terms)[:3])}")

            # 2. 知识域匹配（同域加分）
            if c.domain_name and c.domain_name in info["rel_path"]:
                score += 5
                reasons.append(f"同域: {c.domain_name}")

            # 3. 标签共现
            note_tags = set(info["tags"])
            shared_tags = candidate_tags & note_tags
            if shared_tags:
                score += len(shared_tags) * 2
                reasons.append(f"共享标签: {', '.join(sorted(shared_tags)[:3])}")

            # 4. 子域匹配（更精准）
            if c.subdomains:
                for sd in c.subdomains:
                    if sd in title or sd in info.get("rel_path", ""):
                        score += 4
                        reasons.append(f"子域: {sd}")
                        break

            if score > 0:
                scored.append({
                    "title": title,
                    "stem": info["stem"],
                    "rel_path": info["rel_path"],
                    "score": score,
                    "reason": " | ".join(reasons),
                })

        # 排序取 TOP
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:self.MAX_SUGGESTIONS]

    @staticmethod
    def _tokenize(text: str) -> set:
        """中文分词（简单版：2-4 字 n-gram + 英文词）"""
        tokens = set()
        # 英文词
        for w in re.findall(r'[A-Za-z]+', text):
            if len(w) >= 2:
                tokens.add(w.lower())
        # 中文 2-4 gram
        chinese = re.sub(r'[^\u4e00-\u9fff]', '', text)
        for n in [2, 3, 4]:
            for i in range(len(chinese) - n + 1):
                token = chinese[i:i+n]
                # 过滤纯虚词
                if not all(ch in '的了在是和有我这那不' for ch in token):
                    tokens.add(token)
        return tokens


# ═══════════════════════════════════════════
# 5. 提示词构建器
# ═══════════════════════════════════════════

class PromptBuilder:
    """构建 LLM 解读提示词"""

    TEMPLATE_HINTS = {
        "C01-CASE": (
            "类型：公司/事件案例。聚焦单一主体（一家公司/一个事件），"
            "分析其战略决策、时机选择、对行业的影响。"
        ),
        "C02-INDUSTRY": (
            "类型：行业趋势。覆盖多个主体/事件的综合判断，"
            "分析趋势确定性、多方信号交叉验证、产业结构变化。"
        ),
        "C03-METHOD": (
            "类型：方法论/框架。以可迁移的知识为主，"
            "清晰展示框架结构、应用步骤、局限性、与其他方法的关系。"
        ),
        "C04-PRODUCT": (
            "类型：产品/工具。聚焦单一产品，"
            "分析其解决的问题、技术壁垒、竞品对比、市场前景。"
        ),
    }

    def build(self, c: DeepCandidate, link_suggestions: list = None) -> str:
        """构建完整 prompt，可选附带 [[双链]] 建议"""
        hint = self.TEMPLATE_HINTS.get(c.template_id, "")

        # 构建双链建议区
        links_section = ""
        if link_suggestions:
            links_section = "## 🔗 可关联的已有笔记（请在正文中用 [[笔记名]] 建立双链）\n\n"
            links_section += "你的解读中，在提到相关概念/公司/人物时，应使用 Obsidian 双链语法 `[[笔记名]]` 链接到以下已有笔记：\n\n"
            for ls in link_suggestions[:8]:
                links_section += f"- **[[{ls['stem']}]]** — {ls['reason']}\n"
            links_section += "\n**规则**：\n"
            links_section += "- 正文中首次提及某个可关联概念时，使用 `[[笔记名]]` 建立双链\n"
            links_section += "- 不要强行链接不相关的内容\n"
            links_section += "- 每篇至少建立 3 条双链，尽量建立 5 条以上\n\n"
        else:
            links_section = "## 🔗 双链要求\n\n"
            links_section += "知识库中暂无强关联笔记，但仍请在正文中对关键概念使用 `[[概念名]]` 形式\n"
            links_section += "标注，未来补充笔记时会自动形成双向链接。\n\n"

        prompt = f"""# 深度解读任务

## 文章信息
- **标题**: {c.title}
- **来源**: {c.platform}
- **链接**: {c.url}
- **评分**: {c.score:.1f}/10

## 分类信息
- **模板**: {c.template_id}
- **解读类型**: {hint}
- **知识域**: {c.domain_name}
- **子域**: {', '.join(c.subdomains) if c.subdomains else '自动判断'}
- **建议标签**: {', '.join(c.tags)}

{links_section}

## 原文内容

{c.full_content if c.full_content else c.summary}

---

## 生成要求

请生成一份深度解读笔记，使用 Markdown 格式，包含以下结构：

### YAML frontmatter (已提供，请保持)
```
{c.yaml_frontmatter}
```

### 📝 核心要点 (必填)
用 3-5 个完整段落（不是短语罗列！）叙述本文最核心的发现和判断。
每个段落都必须是完整句子、连贯叙述。
让读者不需要点开原文链接也能完整理解核心内容。
字数：500-800 字。

### 🎯 深度分析 (必填)
用完整句子的叙事体，而非短语列表。
分析文章的深层含义，包含：
- 发现了什么、为什么重要、背后的驱动力
- 与之前已知信息的对比/验证/矛盾
- 多方视角的交叉验证

### 🔍 风险与不确定性 (必填)
这个判断可能错在哪里？什么信号可以证伪？

### 💡 行动启示 (必填)
对创业/产品/投资/职业的具体启示（至少 2 条）

### 文末脚注
*解读模板: {c.template_id} | 解读日期: {datetime.now().strftime('%Y-%m-%d')} | 原始来源: {c.url}*

---

重要规则：
1. 所有分析用完整句子写，禁止短语罗列
2. 📝 核心要点段落独立完整，可脱离原文阅读
3. 深度分析要有洞察，不要摘要原文
4. 保持专业分析语气，但通俗易懂
5. 直接输出笔记内容，不要加"好的""以下是""让我来"等前缀
6. ⚠️ 必须使用 [[笔记名]] 建立双向链接！首次提到关键概念/公司/人物时使用双链"""

        return prompt


# ═══════════════════════════════════════════
# 6. Obsidian 写入器
# ═══════════════════════════════════════════

class ObsidianWriter:
    """写入深度解读笔记到 Obsidian"""

    def __init__(self, vault_path: str = None):
        self.vault = Path(vault_path or CONFIG["obsidian_vault"])

    def get_output_path(self, c: DeepCandidate) -> Path:
        """计算输出路径"""
        template_cfg = TEMPLATE_PATTERNS.get(c.template_id, {})
        folder = template_cfg.get("folder", "动态")

        base = self.vault / CONFIG["knowledge_base"] / folder / c.domain
        base.mkdir(parents=True, exist_ok=True)

        # 安全文件名
        safe_title = re.sub(r'[\\/:*?"<>|]', '-', c.title)[:60]
        filename = f"{safe_title}.md"
        return base / filename

    def write(self, c: DeepCandidate) -> str:
        """
        将解读写入 Obsidian。
        如果已存在同名文件，追加版本号避免覆盖。
        """
        path = self.get_output_path(c)

        # 幂等：如果已存在，加序号
        if path.exists():
            stem = path.stem
            for i in range(2, 100):
                new_path = path.with_name(f"{stem}_v{i}.md")
                if not new_path.exists():
                    path = new_path
                    break

        path.write_text(c.interpretation, encoding="utf-8")
        c.output_path = str(path)
        return str(path)

    def get_relative_path(self, c: DeepCandidate) -> str:
        """获取相对于 vault 的路径（用于双链）"""
        abs_path = Path(c.output_path) if c.output_path else self.get_output_path(c)
        try:
            rel = abs_path.relative_to(self.vault)
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(abs_path)


# ═══════════════════════════════════════════
# 7. MOC 更新器
# ═══════════════════════════════════════════

class MOCUpdater:
    """更新知识地图索引文件"""

    def __init__(self, vault_path: str = None):
        self.vault = Path(vault_path or CONFIG["obsidian_vault"])

    def update(self, c: DeepCandidate):
        """将新笔记添加到对应的 MOC 索引文件"""
        writer = ObsidianWriter(str(self.vault))
        rel_path = writer.get_relative_path(c)

        # 1. 域级 MOC
        template_cfg = TEMPLATE_PATTERNS.get(c.template_id, {})
        folder = template_cfg.get("folder", "动态")
        domain_moc = self.vault / CONFIG["knowledge_base"] / folder / c.domain / f"_{c.domain_name}_MOC.md"
        domain_moc.parent.mkdir(parents=True, exist_ok=True)
        self._append_to_moc(domain_moc, c, rel_path)

        # 2. 不再生成标签索引文件——用户自行在 Obsidian 中通过标签面板导航

    def _append_to_moc(self, moc_path: Path, c: DeepCandidate, rel_path: str):
        """追加条目到 MOC 文件（去重）"""
        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"- [{today}] [[{rel_path.replace('.md', '')}|{c.title}]]"

        if moc_path.exists():
            content = moc_path.read_text(encoding="utf-8")
            if rel_path in content or c.title in content:
                return  # 已存在
            content += f"\n{entry}"
        else:
            content = (
                f"# {moc_path.stem}\n\n"
                f"> 自动生成的知识索引，由 knowledge-scout v4.0 维护\n\n"
                f"{entry}\n"
            )

        moc_path.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════
# 8. 深度分析引擎（总控）
# ═══════════════════════════════════════════

class DeepAnalyzer:
    """
    深度解读引擎总控。

    使用方式:
      analyzer = DeepAnalyzer()
      candidates = analyzer.prepare(articles, top_n=5)
      # → 输出 candidate_queue.json，每个 candidate 包含完整 prompt
      # Agent 读取 queue，生成解读，回填 interpretation
      results = analyzer.ingest_from_queue("candidate_queue.json")
      # → 写入 Obsidian + 更新 MOC
    """

    def __init__(self, config: dict = None):
        self.cfg = {**CONFIG, **(config or {})}
        self.fetcher = ContentFetcher()
        self.classifier = ArticleClassifier()
        self.yaml_builder = YAMLBuilder()
        self.prompt_builder = PromptBuilder()
        self.link_suggester = LinkSuggester()
        self.writer = ObsidianWriter()
        self.moc = MOCUpdater()

    def prepare(self, articles: list, top_n: int = 5) -> list[DeepCandidate]:
        """
        准备深度解读候选队列。

        Args:
            articles: Reporter 输出的已评分文章列表
            top_n: 取前 N 篇做深度解读

        Returns:
            candidates 列表，每个的 .prompt 字段包含完整 LLM prompt
        """
        print(f"\n{'='*60}")
        print(f"🧠 DeepAnalyzer: 准备深度解读候选队列 (Top {top_n})")
        print(f"{'='*60}")

        # 按评分排序，取 Top N
        sorted_articles = sorted(
            articles,
            key=lambda a: getattr(a, 'raw_score', 0),
            reverse=True,
        )[:top_n]

        candidates = []
        for i, a in enumerate(sorted_articles):
            print(f"\n[{i+1}/{top_n}] {a.title[:60]}")

            c = DeepCandidate(
                title=a.title,
                url=a.url if hasattr(a, 'url') else '',
                summary=a.summary if hasattr(a, 'summary') else '',
                platform=a.platform if hasattr(a, 'platform') else '',
                score=getattr(a, 'raw_score', 0.0),
            )

            # Step 1: 抓取全文
            print(f"  📥 抓取全文...")
            c.full_content, c.content_fetched = self.fetcher.fetch(c.url)
            if c.content_fetched:
                print(f"  ✅ {len(c.full_content)} 字符")
            else:
                print(f"  ⚠ 使用摘要降级")

            # Step 2: 分类
            c = self.classifier.classify(c)
            print(f"  📂 {c.template_id} → {c.domain} ({', '.join(c.subdomains) if c.subdomains else '自动'})")

            # Step 3: YAML
            c.yaml_frontmatter = self.yaml_builder.build(c)

            # Step 4: 双链建议
            link_suggestions = self.link_suggester.suggest(c)
            n_links = len(link_suggestions)
            print(f"  🔗 推荐 {n_links} 条双链" + (f": {', '.join(ls['stem'][:20] for ls in link_suggestions[:5])}" if n_links else ""))

            # Step 5: 构建 prompt（含双链建议）
            c.prompt = self.prompt_builder.build(c, link_suggestions)

            candidates.append(c)

        print(f"\n✅ 候选队列准备完成: {len(candidates)} 篇")
        return candidates

    def export_queue(self, candidates: list[DeepCandidate], output_path: str = None) -> str:
        """导出候选队列为 JSON 文件"""
        if output_path is None:
            output_path = "candidate_queue.json"

        data = []
        for c in candidates:
            data.append({
                "title": c.title,
                "url": c.url,
                "summary": c.summary,
                "platform": c.platform,
                "score": c.score,
                "template_id": c.template_id,
                "knowledge_type": c.knowledge_type,
                "domain": c.domain,
                "domain_name": c.domain_name,
                "subdomains": c.subdomains,
                "tags": c.tags,
                "knowledge_id": c.knowledge_id,
                "yaml_frontmatter": c.yaml_frontmatter,
                "prompt": c.prompt,
                "content_fetched": c.content_fetched,
                "full_content_len": len(c.full_content),
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"📦 队列已导出: {output_path} ({len(data)} 条)")
        return output_path

    def load_queue(self, queue_path: str) -> list[DeepCandidate]:
        """从 JSON 加载候选队列"""
        with open(queue_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        candidates = []
        for item in data:
            c = DeepCandidate(
                title=item["title"],
                url=item["url"],
                summary=item.get("summary", ""),
                platform=item.get("platform", ""),
                score=item.get("score", 0.0),
                template_id=item.get("template_id", ""),
                knowledge_type=item.get("knowledge_type", ""),
                domain=item.get("domain", ""),
                domain_name=item.get("domain_name", ""),
                subdomains=item.get("subdomains", []),
                tags=item.get("tags", []),
                knowledge_id=item.get("knowledge_id", ""),
                yaml_frontmatter=item.get("yaml_frontmatter", ""),
                prompt=item.get("prompt", ""),
                interpretation=item.get("interpretation", ""),
            )
            candidates.append(c)

        return candidates

    def save_queue(self, candidates: list[DeepCandidate], queue_path: str):
        """保存更新后的队列（含 interpretation）"""
        self.export_queue(candidates, queue_path)

    def ingest_one(self, c: DeepCandidate) -> str:
        """
        将一篇已生成解读的候选写入 Obsidian。
        
        Returns: 输出文件路径
        """
        if not c.interpretation:
            raise ValueError("Candidate 缺少 interpretation 字段")

        # 拼接 YAML + interpretation
        full_note = c.yaml_frontmatter + "\n" + c.interpretation
        c.interpretation = full_note

        # 写入
        path = self.writer.write(c)
        print(f"  ✅ 已写入: {path}")

        # 更新 MOC
        self.moc.update(c)
        print(f"  📇 MOC 已更新")

        return path

    def ingest_all(self, candidates: list[DeepCandidate]) -> list[str]:
        """批量写入"""
        paths = []
        for c in candidates:
            if c.interpretation:
                try:
                    path = self.ingest_one(c)
                    paths.append(path)
                except Exception as e:
                    print(f"  ❌ 写入失败: {e}")
        return paths


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="知识侦察兵 v4 深度解读引擎")
    sub = parser.add_subparsers(dest="command")

    # prepare: 生成候选队列
    prep = sub.add_parser("prepare", help="从 reporter 输出准备深度解读队列")
    prep.add_argument("--queue", default="candidate_queue.json", help="队列输出路径")
    prep.add_argument("--top", type=int, default=5, help="Top N")

    # ingest: 写入已生成的解读
    ingest = sub.add_parser("ingest", help="将已有解读写入 Obsidian")
    ingest.add_argument("--queue", required=True, help="队列 JSON 路径")

    args = parser.parse_args()

    if args.command == "prepare":
        # 这个模式需要从 Reporter 获取文章列表
        # 通常由 report_v4.py 调用，此处为独立运行提供兜底
        print("请使用 report_v4.py --deep N 运行完整流程")
        print("或手动传入 articles 调用 DeepAnalyzer.prepare()")

    elif args.command == "ingest":
        analyzer = DeepAnalyzer()
        candidates = analyzer.load_queue(args.queue)
        paths = analyzer.ingest_all(candidates)
        print(f"\n✅ 完成: {len(paths)} 篇已写入 Obsidian")

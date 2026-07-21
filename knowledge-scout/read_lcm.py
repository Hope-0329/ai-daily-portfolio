"""从 LCM 文件读取文章内容，测试深度解读引擎"""
import sys, json, re, html
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')

from scripts.interpreter import interpret_article, score_article_depth, extract_frameworks, extract_insights
from dataclasses import asdict

# LCM 文件路径
lcm_dir = r"C:\Users\22867\.qclaw\canvas\documents"
import os
files = [f for f in os.listdir(lcm_dir) if f.startswith("file_c88bcdc373cc43dd")]
print(f"LCM files: {files}")

# 从 qclaw_read_ima_content 的 LCM 输出中，内容就是一个 JSON 字符串
# {"content":"<xml>..."}
# 我们先手动解析已知的内容片段
# 实际上，lcm_describe 已经显示了完整内容
# 我们直接从工作区的 palantir_test.txt 读取

# 或者直接用 lcm_expand 获取内容
print("尝试从 LCM 读取...")

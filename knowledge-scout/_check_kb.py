import os
root = r"D:\肠肠的Obsidian\肠肠的obsidian\20-知识资产"
for dp, dn, fn in os.walk(root):
    md_files = [f for f in fn if f.endswith('.md')]
    if md_files:
        rel = dp.replace(root, "").lstrip("\\")
        if not rel:
            rel = "(root)"
        print(f"{rel} ({len(md_files)} md)")

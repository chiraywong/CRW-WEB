"""
从商业分析 Markdown 文件的"结构化参数"YAML 块中提取关键指标，
并在文件第一个 ## 标题之前插入 Quality Snapshot 卡片。
用法：python inject_snapshot.py
"""

import re
import os

CONTENT_DIR = os.path.join(os.path.dirname(__file__), "..", "content", "Business")

COLOR_MAP = {
    "roe":            "card-blue",
    "moat":           "card-green",
    "sustainability": "card-yellow",
    "mgmt":           "card-peach",
    "cycle":          "card-blue",
    "capital":        "card-green",
    "barrier":        "card-yellow",
    "advantage":      "card-peach",
}

def yaml_val(text, key):
    """从 YAML 或 Markdown 表格中提取指定 key 的值"""
    # YAML 格式: key: value  # comment
    m = re.search(rf'^\s*{re.escape(key)}\s*:\s*["\']?([^"\'#\n\r]+?)["\']?\s*(?:#.*)?[\r\n]',
                  text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # 表格格式（精确）: | key | value |
    m = re.search(rf'^\|\s*\*{{0,2}}{re.escape(key)}\*{{0,2}}\s*\|\s*([^|\n\r]+?)\s*\|',
                  text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # 表格格式（带前缀）: | D2.1 key | value |
    m = re.search(rf'^\|\s*\*{{0,2}}[^\|]*?{re.escape(key)}\*{{0,2}}\s*\|\s*([^|\n\r]+?)\s*\|',
                  text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return "—"

def extract_params_block(content):
    """提取 YAML 代码块 或 结构化参数表格区域"""
    # 优先 YAML 代码块
    m = re.search(r'```yaml\s*\r?\n(.*?)```', content, re.DOTALL)
    if m:
        return m.group(1)
    # 表格格式：取"结构化参数"或末尾大段表格
    m = re.search(r'(?:结构化参数|##\s*结构化参数)(.*?)(?:^---|\Z)', content, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(1)
    # 最后兜底：取全文（表格散布在各处）
    return content

def parse_file(content):
    block = extract_params_block(content)

    data = {}

    # ROE
    raw_roe = yaml_val(block, "roe_5y_avg")
    if raw_roe != "—":
        try:
            data["roe"] = str(float(raw_roe)).rstrip("0").rstrip(".") + "%"
        except ValueError:
            data["roe"] = raw_roe if "%" in raw_roe else raw_roe + "%"
    else:
        data["roe"] = "—"

    data["moat"]           = yaml_val(block, "moat_rating")
    data["sustainability"] = yaml_val(block, "moat_sustainability")
    data["mgmt"]           = yaml_val(block, "management_rating")
    data["cycle"]          = yaml_val(block, "cyclicality")
    data["cycle_sub"]      = yaml_val(block, "cycle_position")
    data["capital"]        = yaml_val(block, "capital_intensity")
    data["capital_sub"]    = ""
    data["barrier"]        = yaml_val(block, "entry_barrier")
    data["advantage"]      = yaml_val(block, "moat_existence")
    data["advantage_sub"]  = yaml_val(block, "moat_evidence_strength")

    # 任何字段都没提取到则跳过
    if all(v == "—" for v in data.values()):
        return None

    # 清理所有值：去掉 ** 和括号注释
    for k in data:
        if isinstance(data[k], str):
            data[k] = re.split(r'[（(【]', data[k])[0].strip().strip("*").strip()
    cap_map = {
        "capital-hungry": "重资产",
        "capital-light":  "轻资产",
        "moderate":       "中等",
        "asset-light":    "轻资产",
    }
    data["capital"] = cap_map.get(data["capital"], data["capital"])

    # cycle_position 可能很长，截断
    if len(data.get("cycle_sub", "")) > 20:
        data["cycle_sub"] = data["cycle_sub"][:20] + "…"

    return data

def build_card(label, value, color, sub=""):
    sub_html = f'\n<div class="card-sub">{sub}</div>' if sub and sub != "—" else ""
    return f'<div class="card {color}">\n<div class="card-label">{label}</div>\n<div class="card-value">{value}</div>{sub_html}\n</div>'

def build_snapshot(data):
    cards = "\n".join([
        build_card("5Y AVG ROE",  data["roe"],            COLOR_MAP["roe"]),
        build_card("护城河评级",   data["moat"],           COLOR_MAP["moat"]),
        build_card("可持续性",     data["sustainability"], COLOR_MAP["sustainability"]),
        build_card("管理层评价",   data["mgmt"],           COLOR_MAP["mgmt"]),
        build_card("周期性",       data["cycle"],          COLOR_MAP["cycle"],   data.get("cycle_sub", "")),
        build_card("资本强度",     data["capital"],        COLOR_MAP["capital"], data.get("capital_sub", "")),
        build_card("进入壁垒",     data["barrier"],        COLOR_MAP["barrier"]),
        build_card("优势存在性",   data["advantage"],      COLOR_MAP["advantage"], data.get("advantage_sub", "")),
    ])
    return f'<div class="quality-snapshot">\n<div class="snapshot-title">QUALITY SNAPSHOT</div>\n<div class="snapshot-grid">\n{cards}\n</div>\n</div>\n\n'

SNAPSHOT_RE = re.compile(
    r'<div class="quality-snapshot">.*?</div>\s*</div>\s*</div>\s*\n\n',
    re.DOTALL
)

def inject(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    data = parse_file(content)
    if not data:
        print(f"SKIP {os.path.basename(filepath)} — no YAML block found")
        return

    # 移除旧 snapshot
    content = SNAPSHOT_RE.sub("", content)

    snapshot = build_snapshot(data)

    # 插入到第一个 # 标题之后，空行之后，blockquote/--- 之前
    match = re.search(r'^# .+\n\n', content, re.MULTILINE)
    if match:
        pos = match.end()
        new_content = content[:pos] + snapshot + content[pos:]
    else:
        match = re.search(r'^# .+\n', content, re.MULTILINE)
        pos = match.end() if match else 0
        new_content = content[:pos] + '\n' + snapshot + content[pos:]

    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)

    print(f"OK  {os.path.basename(filepath)}")
    for k, v in data.items():
        print(f"    {k}: {v}")
    print()

if __name__ == "__main__":
    files = sorted(f for f in os.listdir(CONTENT_DIR) if f.endswith(".md"))
    print(f"Found {len(files)} files\n")
    for fname in files:
        inject(os.path.join(CONTENT_DIR, fname))
    print("Done.")

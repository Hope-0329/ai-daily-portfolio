import yaml

data = yaml.safe_load(open("data/sources.yaml", encoding="utf-8"))
sources = data["sources"]
total = len(sources)
enabled = [s for s in sources if s.get("enable", True)]
disabled = [s for s in sources if not s.get("enable", True)]

print(f"Total: {total} | Enabled: {len(enabled)} | Disabled: {len(disabled)}")

types = {}
for s in enabled:
    t = s.get("type", "?")
    types[t] = types.get(t, 0) + 1
print(f"Types: {types}")
print()

print("=== Enabled ===")
for s in enabled:
    print(f"  {s['id']:28s} {s.get('type',' ? '):6s}  {s.get('tier','')}")

print()
print("=== Disabled ===")
for s in disabled:
    notes = s.get('notes', '') or ''
    print(f"  {s['id']:28s} {s.get('type',' ? '):6s}  {notes[:50]}")

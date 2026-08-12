import json
from pathlib import Path

p = Path(r"C:\Users\Menny\.cursor\projects\d-Projects-Achim-AchimSales\agent-transcripts\da7df34d-1ca6-4500-a125-b7c7906dcbc5\da7df34d-1ca6-4500-a125-b7c7906dcbc5.jsonl")
# Print last ~15 user/assistant text snippets (not tool_use dumps)
count = 0
rows = []
with p.open(encoding="utf-8") as f:
    for line in f:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role = obj.get("role")
        if role not in ("user", "assistant"):
            continue
        msg = obj.get("message") or {}
        content = msg.get("content")
        texts = []
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text") or "")
        text = "\n".join(texts).strip()
        if not text:
            continue
        # strip system fluff
        if text.startswith("<mcp_meta_tools>") or text.startswith("<timestamp>") is False and "user_query" not in text and role == "user":
            # keep user_query extracts
            pass
        rows.append((role, text[:800]))

for role, text in rows[-20:]:
    print("=" * 60)
    print(role.upper())
    # Prefer user_query if present
    if "<user_query>" in text:
        start = text.index("<user_query>") + len("<user_query>")
        end = text.index("</user_query>") if "</user_query>" in text else None
        print(text[start:end].strip() if end else text[start:start+400])
    else:
        print(text[:500])

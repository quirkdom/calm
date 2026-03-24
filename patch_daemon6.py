with open("calmd/daemon.py", "r") as f:
    text = f.read()

search_sanitize = """    # Remove hidden reasoning tags if model emits them.
    for tag in ("think", "thought", "reasoning", "reflection"):
        cleaned = re.sub(rf"<{tag}>[\s\S]*?</{tag}>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"<{tag}>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"</{tag}>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()"""

replace_sanitize = """    # Remove hidden reasoning tags if model emits them.
    for tag in ("think", "thought", "reasoning", "reflection"):
        cleaned = re.sub(rf"<{tag}>[\\s\\S]*?</{tag}>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"<{tag}>[\\s\\S]*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"</{tag}>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()"""

text = text.replace(search_sanitize, replace_sanitize)

with open("calmd/daemon.py", "w") as f:
    f.write(text)

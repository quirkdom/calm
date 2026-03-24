with open("calmd/daemon.py", "r") as f:
    text = f.read()

search_stop = """                    ]
                    + ([] if self.config.enable_thinking else ["<think>", "</think>"]),"""

replace_stop = """                    ]
                    + (
                        []
                        if self.config.enable_thinking
                        else [
                            "<think>",
                            "</think>",
                            "<thought>",
                            "</thought>",
                            "<reasoning>",
                            "</reasoning>",
                            "<reflection>",
                            "</reflection>",
                        ]
                    ),"""

text = text.replace(search_stop, replace_stop)

with open("calmd/daemon.py", "w") as f:
    f.write(text)

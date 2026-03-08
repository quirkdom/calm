# `SPEC.md`

## Project

**calm — CLI Answers via Language Models**

`calm` is a terminal-native assistant that:

1. Suggests commands to accomplish a goal
2. Optionally executes those commands with user approval
3. Analyzes text piped to it

All inference runs locally via `calmd`.

---

# 1. Architecture

```text
calm CLI
 ├ stdin detection
 ├ shell history context
 ├ command execution
 └ daemon client

calmd daemon
 ├ inference backend
 ├ tokenizer
 ├ KV cached prompts
 ├ candidate generation
 ├ candidate scoring
 └ response formatter
```

---

# 2. CLI Usage

Primary command:

```bash
calm "<query>"
```

Examples:

```bash
calm "find files larger than 1GB"
calm "what's running on port 3567"
calm "how to extract a tar.gz"
```

---

# 3. Stdin Mode

If stdin is present:

```bash
ps aux | calm "largest memory"
git diff | calm "what changed"
```

Behavior:

```text
stdin detected → analysis mode
```

Output is textual analysis.

No command execution occurs.

---

# 4. Command Execution

If the LLM returns a runnable command:

Example:

```bash
calm "what's running on port 3567"
```

Output:

```text
lsof -i :3567

Run this command? [y/N]
```

User confirmation executes command.

---

# 5. CLI Flags

| Flag             | Meaning                   |
| ---------------- | ------------------------- |
| `-y` / `--yolo`  | run command automatically |
| `-f` / `--force` | allow dangerous commands  |

Example:

```bash
calm -y "what's running on port 3567"
```

---

# 6. Shell History Context

CLI should include the **last shell command** when available.

Example sources:

| Shell | File            |
| ----- | --------------- |
| bash  | ~/.bash_history |
| zsh   | ~/.zsh_history  |

Only the most recent command is used.

Example prompt snippet:

```text
Recent command:
docker ps
```

---

# 7. Request Protocol

CLI → daemon communication via **Unix socket**.

Socket path:

```text
~/.cache/calmd/socket
```

Request schema:

```json
{
 "query": "string",
 "mode": "command | analysis",
 "stdin": "optional text",
 "history": "optional command"
}
```

---

# 8. Response Schema

Daemon returns structured JSON.

Command response:

```json
{
 "type": "command",
 "command": "lsof -i :3567",
 "runnable": true
}
```

Analysis response:

```json
{
 "type": "analysis",
 "answer": "chrome (PID 3812) using ~1.8GB"
}
```

---

# 9. Backend Interface

File:

```
calmd/backend/interface.py
```

```python
class InferenceBackend:

    def load_model(self, model_path):
        pass

    def build_base_state(self, system_prompt):
        pass

    def clone_state(self, state):
        pass

    def prefill(self, state, tokens):
        pass

    def generate_completion(self, state, params):
        return text
```

---

# 10. MLX Backend

Implementation must use:

```
mlx_lm
```

Do not implement transformer inference manually.

Example loading:

```python
from mlx_lm import load

model, tokenizer = load("mlx-community/Qwen3.5-9B-OptiQ-4bit")
```

---

# 11. KV Cache Strategy

At daemon startup:

```
BASE_COMMAND_STATE
BASE_ANALYSIS_STATE
```

Created by pre-filling system prompts.

Requests clone the appropriate state.

---

# 12. Candidate Sampling

Generate **3 candidates**.

Parameters:

```
temperature = 0.3
max_tokens = 96
samples = 3
```

---

# 13. Candidate Scoring

Daemon scores candidates using heuristics.

Example scoring:

| Factor                            | Score |
| --------------------------------- | ----- |
| valid command syntax              | +3    |
| known CLI tool                    | +2    |
| analysis present in analysis mode | +2    |
| hallucinated flags                | -3    |

Highest score wins.

---

# 14. Command Safety Validation

Commands must be rejected if containing:

```
rm -rf /
mkfs
dd if=
shutdown
reboot
```

Unless `--force` flag provided.

---

# 15. Generation Settings

Recommended parameters:

```
max_tokens = 96
temperature = 0.1
top_p = 1.0
stop = ["\n\n"]
```

Candidate sampling uses:

```
temperature = 0.3
samples = 3
```

---

# 16. Stdin Limits

Prevent huge prompts.

Limits:

```
max stdin size: 64 KB
max lines: 200
```

---

# 17. Performance Targets

On Apple Silicon:

```
first token latency < 80 ms
full response < 150 ms
```

---

# 18. Default Model

Recommended:

```
mlx-community/Qwen3.5-9B-OptiQ-4bit
```

Fast mode option:

```
mlx-community/Qwen3.5-4B-OptiQ-4bit
```

---

# 19. v1 Scope

Implement:

✔ command synthesis
✔ stdin analysis
✔ daemon architecture
✔ MLX backend
✔ KV cached prompts
✔ candidate sampling
✔ candidate scoring
✔ command validation
✔ shell history context
✔ optional command execution

---

Exclude:

✖ rule engine
✖ embedding search
✖ autonomous agents
✖ pipeline reconstruction

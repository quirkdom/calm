# AGENTS.md - Agentic Coding Guidelines for Calm (Local Language Models CLI)

## Project Overview
`calm` is a CLI tool and daemon (`calmd`) designed to provide local language model answers directly in the terminal, optimized for **Apple Silicon Macs** using the **MLX** framework.

- **Purpose**: Answer questions, suggest shell commands, and analyze terminal data using a local LLM.
- **Architecture**: A CLI-Daemon split. The `calm` CLI communicates with the `calmd` daemon via a Unix socket (`~/.cache/calmd/socket`).
- **Core Features**:
    - **Smart Mode**: Automatically decides between providing an analysis (text) or a runnable command based on the query and context.
    - **Layered Security**: Validates suggested commands via both LLM tagging and hardcoded regex checks for dangerous operations.
    - **Daemon Management**: Supports Homebrew services, custom LaunchAgents, or unmanaged background processes.
    - **Efficiency**: Implements model warmup policies and automatic idle-offloading to save memory.

## Main Technologies
- **Language**: Python 3.10+
- **Inference Backend**: `mlx-lm` (Apple Silicon optimized)
- **Dependency Management**: `uv`
- **Formatting/Linting**: `ruff`
- **Type Checking**: `basedpyright` (Standard mode)
- **Testing**: `pytest`
- **Platform Support**: macOS (specifically Apple Silicon)

## Building and Running
The project uses `uv` for all development and execution tasks.

### Local Setup
```bash
uv sync
```

### Running the Daemon
```bash
uv run calmd
# Optional: --fast-model, --verbose
```

### Running the CLI
```bash
uv run calm "your query"
# Example with pipe:
ps aux | uv run calm "summarize high memory users"
```

### Testing and Evals
```bash
# Run evaluation tests
uv run pytest tests/eval_*.py

# Run with debug output
uv run pytest tests/eval_*.py --vv -s
```

### Quality Checks
```bash
# Linting and Formatting
uv run ruff check
uv run ruff format

# Type Checking
uv run basedpyright
```

### Benchmarking
```bash
uv run python benchmarks/bench.py
```

## Development Conventions
- **Tooling**: Always prefer `uv run` for executing project-related scripts and tools. Use `uv pip` instead of `pip` for package management within the `uv` environment.
- **Project Structure**:
    - `calm/`: CLI implementation.
    - `calmd/`: Daemon implementation, including the MLX backend.
    - `tests/`: Evaluation and unit tests.
    - `benchmarks/`: Performance benchmarking scripts.
- **Configuration**: Uses a shared configuration file at `~/.config/calm/config.toml`.
- **Environment Variables**: Use `CALMD_SOCKET` to override the default socket path and `CALM_DEBUG_DAEMON=1` for startup diagnostics.
- **Safety**: Changes to command execution logic must respect the dual-layered security check (LLM tagging + regex).
- **Architecture**: Refer to `ARCHITECTURE.md` for deep dives into the smart mode logic, daemon lifecycle, and crash recovery flows.

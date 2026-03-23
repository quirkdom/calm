# TODOs

## Bugs
- [x] Fix generation rails - the generated text is not in the correct format, hence mostly unparseable.
- [x] Improve Homebrew services detection and handling. Currently, when installed via brew, `calm` cannot detect a registered Homebrew service to trigger.
- [ ] `calm` starts up a new daemon if the daemon is already running but blocked on another request. Should backoff in this case.
- [ ] Investigate high RAM usage by `calmd` even after offload (> 400MB).
- [ ] Fix deviation from protocol. e.g. [Codex review discussion](https://github.com/quirkdom/calm/pull/1#discussion_r2943131416)
- [ ] `calm` should run commands in the exact same env/shell as the one it's running in [[needs repo]]
- [ ] Revisit guardrails (`-c` and `-a`).
  - [ ] For example, `uv run calm -a 'how to install git?'` gives `error: no analysis generated; command: brew install git`. This is in our [smart mode eval](tests/eval_smart_mode.py).
  - [ ] Another case: `calm -c 'find commits by Abhishek'` gives `error: no command generated; analysis: To find commits by Abhishek, use: git log --author="Abhishek" --pretty=format:"%H %s"`
- [x] Some `calm` commands are passing through into shell history context. e.g.
    ```
    Last Command:
    calm -c 'find commits by Abhishek. make it pipeable' | calm 'what\'s the most common word in this'
    
    Last 5 Commands:
    1. calm -c 'find commits by Abhishek. make it pipeable' | calm 'what\'s the most common word in this
    2. calm -c 'find commits by Abhishek' | calm 'what\'s the most common word in this?'
    3. calm -c 'find commits by Abhishek' | calm 'what\'s the most common word'
    4. cls
    5. calmd --verbose
    ```
- [ ] Qwen-3.5 generates a lot of commands with `runnable: no` annotation, even though they are perfectly runnable
  - `calm -y "what's on port 3000" | calm -y "kill this"`
  - `calm "list all my S3 buckets and what their size is"`
- [ ] Qwen-3.5 is oversmart / lazy when given previous commands context (more context is worse?). e.g.
    ```
    > git branch --merged
    * master
    > uv run calm 'list branches which are merged'
    The branches which are merged are listed in the output of the last command `git branch --merged`.         <-- should have just returned the command as runnable
    > uv run calm 'list branches which are merged' | uv run calm 'delete them'
    git branch --merged | grep -v "\*" | xargs git branch -D               <-- first invocation returns the analysis, second invocation returns non runnable command based on that
    ```
- [ ] Fix tokenizer stop tokens. Tokenizer stops at `[/CONTENT]` so content misses closing tags.

## Packaging
- [x] Make `calm` and `calmd` installable and distributable via Homebrew and other MacOS-oriented package managers.
  - refer: https://til.simonwillison.net/homebrew/packaging-python-cli-for-homebrew
- [x] Figure out release workflow with GHA Actions + Github releases + PyPI publish
- [x] Figure out homebrew release workflow
  - [ ] Update tap GHA workflows to make bottles for the calm formula. refer: https://brew.sh/2020/11/18/homebrew-tap-with-bottles-uploaded-to-github-releases/
- [x] Don't package unncessary docs, benchmarks or tests.

## `calmd` Daemon improvements
- [x] Implement custom KV caching for static system prompts.
  - [x] Check if we need to use `mlx_lm.generate_stream` to support this
  - [x] Ensure that the `clone cache state -> add user query part to prompt -> generate` flow works correctly.
- [x] Explore prompt prefilling benefits.
- [ ] Explore benefits of multi-sample generation.
- [ ] Improve prefill method naming and design in MLXBackend
  - The `prefill()` method is poorly named (accepts string, not tokens) and doesn't reflect LLM prefill phase
  - Consider renaming to `append_user_content()` and moving `_render_chat_tokens` calls from `generate_completion` to this step
  - This would create a clear separation: prefill step prepares tokenized prompt state, generate_completion handles (implicit) KV cache update and token generation
- [ ] Speed up inference
  - [x] Disable thinking, especially in Qwen-3.5 models.
  - [x] KV caching for static system prompts.
  - [ ] ~~Reuse prompt prefill across samples.~~
  - [x] Truncate / cap stdin for analysis use-case. (Possibly provide a flag / ENV var to override that)
- [ ] Implement our own version of `mlx_lm.generate` for use in [mlx_backend.py](calmd/backend/mlx_backend.py).
  - Should be able to use `mlx_lm.generate_stream` just like `mlx_lm.generate`.
  - Should be able to verbose log stats to our own logger.
  - Should be able to intercept and early-exit when our custom stop tokens are encountered.
- [x] Auto-load and offload of models in `calmd` + auto-recover after crashes.
- [x] Make `calmd` auto-start on system boot 
- [ ] Make `calmd` renice-able (give higher priority to CPU usage)
- [ ] Support multiple concurrent generations in `calmd`.

## UX / DX improvements
- [x] Make tool configurable with user dir config file. See [SPEC.md](SPEC.md)
- [x] Chain queries in `calm`. e.g. `calm 'whats running in port 3000' | calm 'kill this process'`
  - Partial support; needs better support once smart mode is implemented.
- [x] **Smart Mode:** Better situation-aware responses: give short analysis and/or command where possible. Depending on user intent, show one or both.
- [ ] **Smart Mode:** Handling multi-faceted responses: when both analysis and command are pertinent, provide them in a structured way.
      e.g. `uv run calm 'how to install git'` generates the `brew install git` command, and `uv run calm 'ways to install git'` generates an explanation of alternatives (homebrew or official website). 
      - `uv run calm 'install git'` should just give the `brew install git` command.
      - `uv run calm 'how to install git'` should offer to run the `brew install git` command and also note the alternative options available. Something like:
    ```
    $> uv run calm 'how to install git'
    On macOS (Darwin), you can install Git using Homebrew:
    
    brew install git [Run this command? [y/N]] <BLINKING CARET HERE>
    
    Alternatively, you can download the installer from the official website: https://git-scm.com/download/mac
    ```
- [ ] Detect commands in text / analysis output and offer to run them.
- [x] Improve prompt to give outputs in json format, and update daemon parsing logic. See [PROMPT.md](PROMPT.md)
- [ ] Add command sanity validation (e.g. check if flags are correct for MacOS versions of the tools). See [SPEC.md](SPEC.md)
- [ ] Default wait timeout needs to be revisited; currently set to 300s. For initial startup, model download can take much longer and subsequent model loads are much faster (< 10s)
- [ ] Formalize logging for both `calm` and `calmd`.
  - [ ] Replace ad hoc debug prints/env checks with a shared logging setup and explicit log levels.
  - [ ] Decide which logs belong on stderr vs LaunchAgent log files vs future structured logs.
  - [ ] Also need better messaging during that wait period (what's happeneing? Is a model being downloaded?)
- [ ] Support custom instructions from users via config file.
- [ ] Enable / Disable Thinking should be a configurable option.
  - [ ] With thinking enabled, we will need to handle <think> markers.
- [ ] Fast model path should be configurable.

## Chores
- [ ] Simplify repetitive `x = foo(); if x is not None: return x` patterns into direct fallback expressions like `return foo() or bar()` where no extra logic is needed.

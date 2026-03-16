# TODOs

## Bugs
- [x] Fix generation rails - the generated text is not in the correct format, hence mostly unparseable.
- [ ] `calm` starts up a new daemon if the daemon is already running but blocked on another request. Should backoff in this case.
- [ ] Fast model path should be configurable.
- [ ] Enable / Disable Thinking should be a configurable option.
  - [ ] With thinking enabled, we will need to handle <think> markers.
- [ ] Investigate high RAM usage by `calmd` even after offload (> 400MB).
- [ ] Fix deviation from protocol. e.g. [Codex review discussion](https://github.com/quirkdom/calm/pull/1#discussion_r2943131416)

## Packaging
- [ ] Make `calm` and `calmd` installable and distributable via Homebrew and other MacOS-oriented package managers.
  - refer: https://til.simonwillison.net/homebrew/packaging-python-cli-for-homebrew
- [ ] Figure out release workflow with GHA Actions + Github releases + PyPI publish
- [ ] Figure out homebrew release workflow
- [ ] Don't package unncessary docs, benchmarks or tests.

## `calmd` Daemon improvements
- [x] Implement custom KV caching for static system prompts.
  - [x] Check if we need to use `mlx_lm.generate_stream` to support this
  - [x] Ensure that the `clone cache state -> add user query part to prompt -> generate` flow works correctly.
- [ ] Explore prompt prefilling benefits.
- [ ] Speed up inference
  - [x] Disable thinking, especially in Qwen-3.5 models.
  - [x] KV caching for static system prompts.
  - [ ] Reuse prompt prefill across samples.
  - [ ] Truncate / cap stdin for analysis use-case. (Possibly provide a flag / ENV var to override that)
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

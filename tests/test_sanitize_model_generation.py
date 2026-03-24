import pytest

from calmd.daemon import _sanitize_model_text


@pytest.mark.parametrize("tag", ["think", "thinking", "thought", "reasoning", "reflection"])
def test_sanitize_removes_complete_tags(tag):
    input_text = f"<{tag}>Thinking about this...\nAnd that...</{tag}>\nFinal answer is 42."
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

@pytest.mark.parametrize("tag", ["think", "thinking", "thought", "reasoning", "reflection"])
def test_sanitize_removes_unclosed_tags_at_end(tag):
    input_text = f"Final answer is 42.<{tag}>Hmm, wait..."
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

@pytest.mark.parametrize("tag", ["think", "thinking", "thought", "reasoning", "reflection"])
def test_sanitize_removes_unopened_end_tags(tag):
    input_text = f"</{tag}>Final answer is 42."
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

def test_sanitize_removes_multiple_different_tags():
    input_text = "<think>A</think><reasoning>B</reasoning><thought>C</thought><reflection>D</reflection>\nFinal answer is 42."
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

def test_sanitize_removes_chat_tokens():
    input_text = "Final answer is 42.<|endoftext|>"
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

    input_text2 = "Final answer is 42.<|im_start|>user"
    expected2 = "Final answer is 42."
    assert _sanitize_model_text(input_text2) == expected2

    input_text3 = "Final answer is 42.<|im_end|>"
    expected3 = "Final answer is 42."
    assert _sanitize_model_text(input_text3) == expected3

def test_sanitize_ignores_case():
    input_text = "<THINK>Thinking...</think>\nFinal answer is 42."
    expected = "Final answer is 42."
    assert _sanitize_model_text(input_text) == expected

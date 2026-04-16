from app.lab.services.benchmark import parse_llama_timings


SAMPLE = """
...
llama_print_timings: prompt eval time = 240.00 ms /   12 tokens ( 20.00 ms per token,  50.00 tokens per second)
llama_print_timings:        eval time = 2000.00 ms /  100 tokens ( 20.00 ms per token,  50.00 tokens per second)
llama_print_timings:       total time = 2500.00 ms /  112 tokens
"""


def test_parse_valid_timings():
    r = parse_llama_timings(SAMPLE)
    assert r is not None
    assert abs(r.tokens_per_sec - 50.00) < 0.01
    assert abs(r.prompt_eval_tok_per_sec - 50.00) < 0.01
    assert abs(r.ttft_ms - 240.00) < 0.01


def test_parse_missing_returns_none():
    assert parse_llama_timings("nothing interesting") is None

import json

from agent.brain import decide, empty_plan, _normalize_plan


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


class FakeAnthropic:
    def __init__(self, text, stop_reason="end_turn"):
        self._text = text
        self._stop = stop_reason
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Resp(self._text, self._stop)


def test_decide_parses_plan(cfg):
    plan_json = json.dumps({
        "reflection": "Busy day.",
        "votes": [{"target_type": "post", "target_id": 1, "reason": "insightful"}],
        "comments": [{"post_id": 2, "parent_id": None, "body": "Nice.", "reason": "engage"}],
        "post": {"make": True, "title": "Hi", "body": "Body", "reason": "worth it"},
    })
    client = FakeAnthropic(plan_json)
    plan = decide({"budgets": {"posts": 1, "comments": 20, "votes": 50}}, cfg, client=client)
    assert plan["reflection"] == "Busy day."
    assert plan["votes"][0]["target_id"] == 1
    assert plan["post"]["make"] is True
    # Uses structured output + effort.
    assert client.last_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert client.last_kwargs["model"] == cfg.llm_model


def test_decide_handles_refusal(cfg):
    client = FakeAnthropic("whatever", stop_reason="refusal")
    plan = decide({}, cfg, client=client)
    assert plan == empty_plan("brain refused this input")


def test_decide_handles_bad_json(cfg):
    client = FakeAnthropic("not json at all")
    plan = decide({}, cfg, client=client)
    assert plan["votes"] == [] and plan["post"]["make"] is False


def test_normalize_fills_missing_fields():
    plan = _normalize_plan({"votes": "notalist", "post": {"make": True}})
    assert plan["votes"] == []
    assert plan["post"]["make"] is True
    assert plan["post"]["title"] == ""

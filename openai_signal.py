from __future__ import annotations

import json
from typing import Any, Callable

from openai import OpenAI

from models import AISignal, EntryType, MarketRegime, SignalAction


SignalLogger = Callable[[str, dict[str, Any]], None]


SIGNAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "WAIT"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "entry_type": {"type": "string", "enum": ["MARKET", "LIMIT", "NONE"]},
        "stop_loss_pips": {"type": ["number", "null"]},
        "take_profit_pips": {"type": ["number", "null"]},
        "risk_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "market_regime": {
            "type": "string",
            "enum": ["TRENDING", "RANGING", "HIGH_VOLATILITY", "UNCLEAR"],
        },
    },
    "required": [
        "action",
        "confidence",
        "reason",
        "entry_type",
        "stop_loss_pips",
        "take_profit_pips",
        "risk_notes",
        "market_regime",
    ],
    "additionalProperties": False,
}


class OpenAISignalEngine:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int = 20,
        logger: SignalLogger | None = None,
    ) -> None:
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self.logger = logger

    def _fallback_wait(self, reason: str) -> AISignal:
        return AISignal(
            action=SignalAction.WAIT,
            confidence=0.0,
            reason=reason,
            entry_type=EntryType.NONE,
            stop_loss_pips=None,
            take_profit_pips=None,
            risk_notes=["Fallback WAIT due to AI parsing/runtime error"],
            market_regime=MarketRegime.UNCLEAR,
        )

    def generate_signal(self, compact_payload: dict[str, Any]) -> AISignal:
        system_prompt = (
            "You are a trading analyst. You DO NOT place trades. "
            "Return only a JSON object that matches the schema exactly. "
            "Prefer WAIT when uncertainty is high. Use conservative confidence."
        )
        user_prompt = {
            "task": "Analyze compact market snapshot and return one signal.",
            "input": compact_payload,
            "constraints": {
                "must_be_schema_valid": True,
                "never_execute_trades": True,
                "use_action_wait_if_unclear": True,
            },
        }

        if self.logger:
            self.logger("ai_request", {"model": self.model, "payload": user_prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ai_trade_signal",
                        "schema": SIGNAL_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0.2,
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)

            if self.logger:
                self.logger("ai_response", {"raw": parsed})

            return AISignal.model_validate(parsed)
        except Exception as exc:  # noqa: BLE001
            fallback = self._fallback_wait(f"AI error: {exc}")
            if self.logger:
                self.logger("ai_response", {"error": str(exc), "fallback": fallback.model_dump()})
            return fallback

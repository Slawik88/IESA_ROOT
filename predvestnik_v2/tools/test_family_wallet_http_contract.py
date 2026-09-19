#!/usr/bin/env python3
"""Adapter contract for the public family-wallet HTTP writer."""
from __future__ import annotations

import asyncio
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

import FastAPI.routers.marriage as marriage_router
from infrastructure.repositories.family_wallet_v1 import FamilyTransfer


async def run() -> None:
    try:
        marriage_router.BankRequest.model_validate(
            {"amount": 1, "action": "deposit", "currency": "mora", "marriage_id": 99}
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("client-supplied marriage_id must be rejected")

    captured: dict[str, object] = {}

    async def fake_transfer(db, **kwargs):
        captured.update(kwargs)
        return FamilyTransfer(
            operation_id="family:test", marriage_id=77, currency="zarniki",
            amount=Decimal("3"), action="withdrawal", applied=True,
        )

    original = marriage_router.transfer_between_personal_and_family
    marriage_router.transfer_between_personal_and_family = fake_transfer
    try:
        response = await marriage_router.family_bank(
            marriage_router.BankRequest(amount=3, action="withdraw", currency="zarniki"),
            db=object(), user={"id": 123}, request_key="family-http-key",
        )
    finally:
        marriage_router.transfer_between_personal_and_family = original
    assert captured == {
        "actor_id": 123, "currency": "zarniki", "amount": 3.0,
        "action": "withdrawal", "idempotency_key": "family-http-key",
    }
    assert response["operation_id"] == "family:test" and response["replayed"] is False

    try:
        await marriage_router.family_bank(
            marriage_router.BankRequest(amount=1, action="deposit"),
            db=object(), user={"id": 123}, request_key=None,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("missing Idempotency-Key must fail")


asyncio.run(run())
print("family wallet HTTP adapter contract OK")

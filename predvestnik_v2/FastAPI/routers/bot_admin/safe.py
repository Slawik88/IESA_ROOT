"""Админка: неправильные данные в запросе — понятный отказ 400, а не «Ошибка 500».

Поле админки принимает любой текст («1e30», «abc», число больше BIGINT): раньше такие значения доходили до базы и
ронялись внутренней ошибкой. Остальные ошибки (настоящие сбои) по-прежнему 500 и пишутся в лог."""
from __future__ import annotations

import asyncpg
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger

BAD_INPUT = (ValueError, TypeError, OverflowError, ArithmeticError, asyncpg.DataError)


class AdminRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except HTTPException:
                raise
            except BAD_INPUT as exc:
                logger.warning(f"bot-admin {request.method} {request.url.path}: некорректные данные: {exc!r}")
                return JSONResponse({"detail": "Некорректное значение в запросе: проверьте числа и поля."}, status_code=400)
        return handler

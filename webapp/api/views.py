"""Camera framing (view) CRUD."""

from __future__ import annotations


from typing import Any


from fastapi import HTTPException

from fastapi.responses import Response

from sqlalchemy import select


from ..db import View, session_scope

from ..revision import bump_revision

from .router import VIEW_KINDS, router

from .schemas import ViewIn

from .serializers import view_to_dict


@router.get("/views")
def api_views_list(kind: str = "") -> list[dict[str, Any]]:

    with session_scope() as s:
        query = select(View).order_by(View.kind, View.position, View.key)

        if kind:
            query = query.where(View.kind == kind)

        rows = s.scalars(query).all()

        return [view_to_dict(v) for v in rows]


@router.post("/views", status_code=201)
def api_views_create(payload: ViewIn) -> dict[str, Any]:

    if payload.kind not in VIEW_KINDS:
        raise HTTPException(400, f"kind must be one of {VIEW_KINDS}")

    with session_scope() as s:
        if s.scalar(select(View.id).where(View.key == payload.key)) is not None:
            raise HTTPException(409, f"key {payload.key!r} already in use")

        v = View(
            key=payload.key,
            kind=payload.kind,
            label=payload.label or payload.key,
            position=payload.position,
            comment=payload.comment,
            framing_clause=payload.framing_clause,
        )

        s.add(v)

        s.flush()

        out = view_to_dict(v)

    bump_revision()

    return out


@router.get("/views/{key:path}")
def api_views_get(key: str) -> dict[str, Any]:

    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))

        if v is None:
            raise HTTPException(404, "view not found")

        return view_to_dict(v)


@router.put("/views/{key:path}")
def api_views_update(key: str, payload: ViewIn) -> dict[str, Any]:

    if payload.kind not in VIEW_KINDS:
        raise HTTPException(400, f"kind must be one of {VIEW_KINDS}")

    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))

        if v is None:
            raise HTTPException(404, "view not found")

        if payload.key != key:
            if (
                s.scalar(
                    select(View.id).where(View.key == payload.key, View.id != v.id)
                )
                is not None
            ):
                raise HTTPException(409, f"key {payload.key!r} already in use")

        v.key = payload.key

        v.kind = payload.kind

        v.label = payload.label or payload.key

        v.position = payload.position

        v.comment = payload.comment
        v.framing_clause = payload.framing_clause

        out = view_to_dict(v)

    bump_revision()

    return out


@router.delete("/views/{key:path}", status_code=204)
def api_views_delete(key: str) -> Response:

    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))

        if v is None:
            raise HTTPException(404, "view not found")

        s.delete(v)

    bump_revision()

    return Response(status_code=204)

"""Character CRUD and design hub."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select

from ...services import attributes as char_attrs
from ...services.design.outfit import outfit_form_context, parse_outfit_form
from ...services.design.forms import (
    apply_inline_lora,
    clear_uploaded_image,
    joined,
    lora_form_fields,
    parse_bool,
    parse_inline_lora_form,
    parse_taglist,
    save_uploaded_image,
)
from ...db import (
    LORA_KIND_CHARACTER,
    ROLE_MAIN,
    DesignEntity,
    session_scope,
)
from ...services.design.embed import embed_context, embed_redirect
from ...revision import bump_revision
from ...services.validate import (
    ValidationSaveError,
    entity_errors,
    validate_character,
)

router = APIRouter()
hub_router = APIRouter()
monster_router = APIRouter()
object_router = APIRouter()

_TYPE_TABS = (
    ("all", "All"),
    ("characters", "Characters"),
    ("monsters", "Monsters"),
    ("objects", "Objects"),
    ("backgrounds", "Backgrounds"),
)


def _ensure_unique_slug(s, slug: str, exclude_id: int | None = None) -> None:
    q = select(DesignEntity.id).where(DesignEntity.slug == slug)
    if exclude_id is not None:
        q = q.where(DesignEntity.id != exclude_id)
    if s.scalar(q) is not None:
        raise HTTPException(
            400, f"Choose a different slug — '{slug}' is already in use."
        )


@hub_router.get("", response_class=HTMLResponse, name="design_list")
def design_hub_list(request: Request, type: str = Query("all"), q: str = Query("")):
    from ...db.models import (
        ENTITY_BACKGROUND,
        ENTITY_CHARACTER,
        ENTITY_MONSTER,
        ENTITY_OBJECT,
    )

    with session_scope() as s:
        query = select(DesignEntity).order_by(DesignEntity.entity_type, DesignEntity.slug)
        if type == "characters":
            query = query.where(
                DesignEntity.entity_type == ENTITY_CHARACTER, DesignEntity.role == ROLE_MAIN
            )
        elif type == "monsters":
            query = query.where(DesignEntity.entity_type == ENTITY_MONSTER)
        elif type == "objects":
            query = query.where(DesignEntity.entity_type == ENTITY_OBJECT)
        elif type == "backgrounds":
            query = query.where(DesignEntity.entity_type == ENTITY_BACKGROUND)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    DesignEntity.slug.ilike(like),
                    DesignEntity.display_name.ilike(like),
                )
            )
        rows = s.scalars(query).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "design/hub_list.html",
        {
            "active": "design",
            "rows": rows,
            "q": q,
            "type": type,
            "type_tabs": _TYPE_TABS,
        },
    )


def _render_list(request: Request, q: str):
    from ...db.models import ENTITY_CHARACTER

    with session_scope() as s:
        query = (
            select(DesignEntity)
            .where(
                DesignEntity.role == ROLE_MAIN, DesignEntity.entity_type == ENTITY_CHARACTER
            )
            .order_by(DesignEntity.slug)
        )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    DesignEntity.slug.ilike(like),
                    DesignEntity.display_name.ilike(like),
                    DesignEntity.name_tag.ilike(like),
                )
            )
        rows = s.scalars(query).all()
        for c in rows:
            _ = c.character_lora
    return request.app.state.templates.TemplateResponse(
        request,
        "design/list.html",
        {
            "active": "characters",
            "rows": rows,
            "q": q,
        },
    )


@router.get("", response_class=HTMLResponse, name="characters_list")
def characters_list(request: Request, q: str = Query("")):
    return _render_list(request, q)


def _character_lora_context(character: DesignEntity) -> dict[str, str]:
    return lora_form_fields(character.character_lora)


def _physical_context(character: DesignEntity) -> dict:
    return {
        "physical_attributes": char_attrs.options_payload()["regions"],
        "physical_values": {
            a.key: char_attrs.format_physical_display(
                a, getattr(character, a.key, None)
            )
            for a in char_attrs.ATTRIBUTES
        },
    }


def _detach_character(session, c: DesignEntity) -> None:
    if c.character_lora is not None:
        session.expunge(c.character_lora)
    session.expunge(c)


async def _save_character_or_raise(session, c: DesignEntity, form) -> None:
    await _apply_character_form(session, c, form)
    issues = validate_character(session, c)
    errs = entity_errors(issues)
    if errs:
        _detach_character(session, c)
        raise ValidationSaveError(errs)


def _render_form(
    request: Request,
    character: DesignEntity,
    *,
    validation_issues=None,
    form=None,
):
    ctx = {
        "active": "characters",
        "character": character,
        "joined": joined,
        "lora_data": _character_lora_context(character),
        **_physical_context(character),
        **outfit_form_context(character),
        **embed_context(request, form),
    }
    if validation_issues:
        ctx["validation_issues"] = validation_issues
    return request.app.state.templates.TemplateResponse(
        request,
        "design/form.html",
        ctx,
    )


def _blank_character() -> DesignEntity:
    blank = DesignEntity(
        slug="",
        display_name="",
        name_tag="",
        role=ROLE_MAIN,
        identity_core=[],
    )
    blank.id = None
    return blank


@router.get("/new", response_class=HTMLResponse, name="characters_new")
def characters_new(request: Request):
    return _render_form(request, _blank_character())


async def _do_create(request: Request):
    form = await request.form()
    slug = (form.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "Slug is required.")
    from ...db.models import ENTITY_CHARACTER

    c = DesignEntity(
        slug=slug,
        name_tag=slug,
        display_name=slug,
        entity_type=ENTITY_CHARACTER,
        role=ROLE_MAIN,
    )
    try:
        with session_scope() as s:
            _ensure_unique_slug(s, slug)
            s.add(c)
            s.flush()
            await _save_character_or_raise(s, c, form)
    except ValidationSaveError as exc:
        return _render_form(request, c, validation_issues=exc.issues, form=form)
    bump_revision()
    return embed_redirect(request, f"/characters/{slug}", form=form)


@router.post("", response_class=HTMLResponse)
async def characters_create(request: Request):
    return await _do_create(request)


def _do_edit(request: Request, slug: str):
    with session_scope() as s:
        c = s.scalar(
            select(DesignEntity).where(DesignEntity.slug == slug, DesignEntity.role == ROLE_MAIN)
        )
        if c is None:
            raise HTTPException(404, "character not found")
        _ = c.character_lora
    return _render_form(request, c)


@router.get("/{slug}", response_class=HTMLResponse, name="characters_edit")
def characters_edit(request: Request, slug: str):
    return _do_edit(request, slug)


async def _do_update(request: Request, slug: str):
    form = await request.form()
    new_slug = (form.get("slug") or "").strip() or slug
    try:
        with session_scope() as s:
            c = s.scalar(
                select(DesignEntity).where(
                    DesignEntity.slug == slug, DesignEntity.role == ROLE_MAIN
                )
            )
            if c is None:
                raise HTTPException(404, "character not found")
            if new_slug != c.slug:
                _ensure_unique_slug(s, new_slug, exclude_id=c.id)
            await _save_character_or_raise(s, c, form)
    except ValidationSaveError as exc:
        return _render_form(request, c, validation_issues=exc.issues, form=form)
    bump_revision()
    return embed_redirect(request, f"/characters/{new_slug}", form=form)


@router.post("/{slug}", response_class=HTMLResponse)
async def characters_update(request: Request, slug: str):
    return await _do_update(request, slug)


@router.post("/{slug}/delete", response_class=HTMLResponse)
def characters_delete(slug: str):
    with session_scope() as s:
        c = s.scalar(
            select(DesignEntity).where(DesignEntity.slug == slug, DesignEntity.role == ROLE_MAIN)
        )
        if c is not None:
            clear_uploaded_image(c.image_path)
            s.delete(c)
    bump_revision()
    return RedirectResponse("/characters", status_code=303)


async def _apply_character_form(s, c: DesignEntity, form) -> None:
    c.slug = (form.get("slug") or c.slug or "").strip()
    c.display_name = (form.get("display_name") or c.slug).strip()
    c.name_tag = (form.get("name_tag") or c.slug or "").strip()
    c.comment = (form.get("comment") or "").strip() or None
    c.video_prompt = (form.get("video_prompt") or "").strip() or None
    c.role = ROLE_MAIN

    c.identity_core = parse_taglist(form.get("identity_core"))
    for key, value in parse_outfit_form(form).items():
        setattr(c, key, value)

    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(c.image_path)
        c.image_path = None
    else:
        upload = form.get("image")
        c.image_path = save_uploaded_image(
            upload, entity="characters", slug=c.slug, existing=c.image_path
        )

    for attr in char_attrs.ATTRIBUTES:
        setattr(
            c,
            attr.key,
            char_attrs.coerce_physical_incoming(attr, form.get(attr.key)),
        )

    lora_fields = parse_inline_lora_form(form, "lora_")
    new_lora_id = apply_inline_lora(
        s,
        kind=LORA_KIND_CHARACTER,
        existing_id=c.lora_id,
        **lora_fields,
    )
    c.lora_id = new_lora_id


def _simple_entity_meta(entity_type: str) -> dict[str, str]:
    from ...db.models import ENTITY_MONSTER, ENTITY_OBJECT

    if entity_type == ENTITY_MONSTER:
        return {
            "kind_label": "Monster",
            "kind_icon": "flame",
            "page_prefix": "/design/monsters",
            "list_url": "/design?type=monsters",
            "tag_placeholder": "slime\nmonster\nsolo",
            "upload_entity": "monsters",
        }
    if entity_type == ENTITY_OBJECT:
        return {
            "kind_label": "Object",
            "kind_icon": "category",
            "page_prefix": "/design/objects",
            "list_url": "/design?type=objects",
            "tag_placeholder": "sword\nweapon\nno humans",
            "upload_entity": "objects",
        }
    raise ValueError(f"unsupported entity_type {entity_type!r}")


def _get_simple_entity(session, entity_type: str, slug: str) -> DesignEntity:
    row = session.scalar(
        select(DesignEntity).where(
            DesignEntity.slug == slug, DesignEntity.entity_type == entity_type
        )
    )
    if row is None:
        meta = _simple_entity_meta(entity_type)
        raise HTTPException(404, f"{meta['kind_label'].lower()} not found")
    return row


async def _apply_simple_entity_form(
    session, entity: DesignEntity, form, *, upload_entity: str
) -> None:
    entity.slug = (form.get("slug") or entity.slug or "").strip()
    entity.display_name = (form.get("display_name") or entity.slug).strip()
    entity.name_tag = (form.get("name_tag") or entity.slug).strip()
    entity.comment = (form.get("comment") or "").strip() or None
    entity.identity_core = parse_taglist(form.get("identity_core"))
    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(entity.image_path)
        entity.image_path = None
    else:
        upload = form.get("image")
        entity.image_path = save_uploaded_image(
            upload, entity=upload_entity, slug=entity.slug, existing=entity.image_path
        )


def _render_simple_entity_form(request: Request, entity_type: str, entity: DesignEntity):
    meta = _simple_entity_meta(entity_type)
    return request.app.state.templates.TemplateResponse(
        request,
        "design/simple_entity_form.html",
        {
            "active": "design",
            "entity": entity,
            "joined": joined,
            **meta,
            **embed_context(request),
        },
    )


def _register_simple_entity_routes(api_router: APIRouter, entity_type: str) -> None:
    meta = _simple_entity_meta(entity_type)

    @api_router.get("/new", response_class=HTMLResponse)
    def _new(request: Request):
        blank = DesignEntity(
            slug="",
            display_name="",
            name_tag="",
            entity_type=entity_type,
            role=ROLE_MAIN,
            identity_core=[],
        )
        blank.id = None
        return _render_simple_entity_form(request, entity_type, blank)

    @api_router.post("", response_class=HTMLResponse)
    async def _create(request: Request):
        form = await request.form()
        slug = (form.get("slug") or "").strip()
        if not slug:
            raise HTTPException(400, "Slug is required.")
        with session_scope() as s:
            if s.scalar(select(DesignEntity.id).where(DesignEntity.slug == slug)) is not None:
                raise HTTPException(
                    400, f"Choose a different slug — '{slug}' is already in use."
                )
            entity = DesignEntity(
                slug=slug,
                display_name=slug,
                name_tag=slug,
                entity_type=entity_type,
                role=ROLE_MAIN,
            )
            s.add(entity)
            s.flush()
            await _apply_simple_entity_form(
                s, entity, form, upload_entity=meta["upload_entity"]
            )
        bump_revision()
        return embed_redirect(request, f"{meta['page_prefix']}/{slug}", form=form)

    @api_router.get("/{slug}", response_class=HTMLResponse)
    def _edit(request: Request, slug: str):
        with session_scope() as s:
            entity = _get_simple_entity(s, entity_type, slug)
        return _render_simple_entity_form(request, entity_type, entity)

    @api_router.post("/{slug}", response_class=HTMLResponse)
    async def _update(request: Request, slug: str):
        form = await request.form()
        new_slug = (form.get("slug") or "").strip() or slug
        with session_scope() as s:
            entity = _get_simple_entity(s, entity_type, slug)
            if (
                new_slug != slug
                and s.scalar(
                    select(DesignEntity.id).where(
                        DesignEntity.slug == new_slug, DesignEntity.id != entity.id
                    )
                )
                is not None
            ):
                raise HTTPException(
                    400, f"Choose a different slug — '{new_slug}' is already in use."
                )
            await _apply_simple_entity_form(
                s, entity, form, upload_entity=meta["upload_entity"]
            )
        bump_revision()
        return embed_redirect(request, f"{meta['page_prefix']}/{new_slug}", form=form)

    @api_router.post("/{slug}/delete", response_class=HTMLResponse)
    def _delete(slug: str):
        with session_scope() as s:
            entity = _get_simple_entity(s, entity_type, slug)
            clear_uploaded_image(entity.image_path)
            s.delete(entity)
        bump_revision()
        return RedirectResponse(meta["list_url"], status_code=303)

    @api_router.post("/{slug}/image", response_class=HTMLResponse)
    async def _image(request: Request, slug: str):
        form = await request.form()
        with session_scope() as s:
            entity = _get_simple_entity(s, entity_type, slug)
            upload = form.get("image")
            entity.image_path = save_uploaded_image(
                upload,
                entity=meta["upload_entity"],
                slug=entity.slug,
                existing=entity.image_path,
            )
        bump_revision()
        return RedirectResponse(f"{meta['page_prefix']}/{slug}", status_code=303)


from ...db.models import ENTITY_MONSTER, ENTITY_OBJECT

_register_simple_entity_routes(monster_router, ENTITY_MONSTER)
_register_simple_entity_routes(object_router, ENTITY_OBJECT)

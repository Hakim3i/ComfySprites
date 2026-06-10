"""Character CRUD.

Same router serves both ``main`` characters (under ``/characters``) and
``partner`` characters (under ``/partners``).

Includes:

- multipart image upload (reference / cover image, served from
  ``/uploads/characters/<slug>.<ext>``)
- inline character LoRA editor (filename / url / trigger / strength on
  the form itself — no /loras tab)
"""

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
    parse_int,
    parse_taglist,
    save_uploaded_image,
)
from ...db import (
    LORA_KIND_CHARACTER,
    LORA_KIND_PARTNER,
    ROLE_MAIN,
    ROLE_PARTNER,
    Character,
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
partner_router = APIRouter()
hub_router = APIRouter()
monster_router = APIRouter()
object_router = APIRouter()

_TYPE_TABS = (
    ("all", "All"),
    ("characters", "Characters"),
    ("partners", "Partners"),
    ("monsters", "Monsters"),
    ("objects", "Objects"),
    ("backgrounds", "Backgrounds"),
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _ensure_unique_slug(s, slug: str, exclude_id: int | None = None) -> None:
    q = select(Character.id).where(Character.slug == slug)
    if exclude_id is not None:
        q = q.where(Character.id != exclude_id)
    if s.scalar(q) is not None:
        raise HTTPException(400, f"Choose a different slug — '{slug}' is already in use.")


def _detail_url(role: str, slug: str) -> str:
    base = "/partners" if role == ROLE_PARTNER else "/characters"
    return f"{base}/{slug}"


def _list_url(role: str) -> str:
    return "/partners" if role == ROLE_PARTNER else "/characters"


def _list_template(role: str) -> str:
    return "design/list.html" if role == ROLE_PARTNER else "design/list.html"


def _form_template(role: str) -> str:
    return "design/form.html" if role == ROLE_PARTNER else "design/form.html"


def _active(role: str) -> str:
    return "partners" if role == ROLE_PARTNER else "characters"


# ---------------------------------------------------------------------------
# Unified design hub at /design
# ---------------------------------------------------------------------------


@hub_router.get("", response_class=HTMLResponse, name="design_list")
def design_hub_list(request: Request, type: str = Query("all"), q: str = Query("")):
    from ...db.models import ENTITY_BACKGROUND, ENTITY_CHARACTER, ENTITY_MONSTER, ENTITY_OBJECT

    with session_scope() as s:
        query = select(Character).order_by(Character.entity_type, Character.slug)
        if type == "characters":
            query = query.where(Character.entity_type == ENTITY_CHARACTER, Character.role == ROLE_MAIN)
        elif type == "partners":
            query = query.where(Character.entity_type == ENTITY_CHARACTER, Character.role == ROLE_PARTNER)
        elif type == "monsters":
            query = query.where(Character.entity_type == ENTITY_MONSTER)
        elif type == "objects":
            query = query.where(Character.entity_type == ENTITY_OBJECT)
        elif type == "backgrounds":
            query = query.where(Character.entity_type == ENTITY_BACKGROUND)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    Character.slug.ilike(like),
                    Character.display_name.ilike(like),
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


# ---------------------------------------------------------------------------
# List view (shared, role-scoped)
# ---------------------------------------------------------------------------


def _render_list(request: Request, role: str, q: str):
    from ...db.models import ENTITY_CHARACTER

    with session_scope() as s:
        query = (
            select(Character)
            .where(Character.role == role, Character.entity_type == ENTITY_CHARACTER)
            .order_by(
                Character.partner_position if role == ROLE_PARTNER else Character.slug,
                Character.slug,
            )
        )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    Character.slug.ilike(like),
                    Character.display_name.ilike(like),
                    Character.name_tag.ilike(like),
                )
            )
        rows = s.scalars(query).all()
        for c in rows:
            _ = c.character_lora
    return request.app.state.templates.TemplateResponse(
        request,
        _list_template(role),
        {
            "active": _active(role),
            "rows": rows,
            "q": q,
            "role": role,
        },
    )


@router.get("", response_class=HTMLResponse, name="characters_list")
def characters_list(request: Request, q: str = Query("")):
    return _render_list(request, ROLE_MAIN, q)


@partner_router.get("", response_class=HTMLResponse, name="partners_list")
def partners_list(request: Request, q: str = Query("")):
    return _render_list(request, ROLE_PARTNER, q)


# ---------------------------------------------------------------------------
# New / edit form
# ---------------------------------------------------------------------------


def _character_lora_context(character: Character) -> dict[str, str]:
    return lora_form_fields(character.character_lora)


def _physical_context(character: Character) -> dict:
    role = character.role or ROLE_MAIN
    attrs = char_attrs.attributes_for_role(role)
    return {
        "physical_attributes": char_attrs.options_payload(role=role)["regions"],
        "physical_values": {
            a.key: char_attrs.format_physical_display(a, getattr(character, a.key, None))
            for a in attrs
        },
    }


def _detach_character(session, c: Character) -> None:
    if c.character_lora is not None:
        session.expunge(c.character_lora)
    session.expunge(c)


async def _save_character_or_raise(session, c: Character, form) -> None:
    await _apply_character_form(session, c, form)
    issues = validate_character(session, c)
    errs = entity_errors(issues)
    if errs:
        _detach_character(session, c)
        raise ValidationSaveError(errs)


def _render_form(
    request: Request,
    role: str,
    character: Character,
    *,
    validation_issues=None,
    form=None,
):
    ctx = {
        "active": _active(role),
        "character": character,
        "role": role,
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
        _form_template(role),
        ctx,
    )


def _blank_character(role: str) -> Character:
    blank = Character(
        slug="",
        display_name="",
        name_tag="",
        role=role,
        identity_core=[],
    )
    blank.id = None
    return blank


@router.get("/new", response_class=HTMLResponse, name="characters_new")
def characters_new(request: Request):
    return _render_form(request, ROLE_MAIN, _blank_character(ROLE_MAIN))


@partner_router.get("/new", response_class=HTMLResponse, name="partners_new")
def partners_new(request: Request):
    return _render_form(request, ROLE_PARTNER, _blank_character(ROLE_PARTNER))


# ---------------------------------------------------------------------------
# Create / edit / update / delete
# ---------------------------------------------------------------------------


async def _do_create(request: Request, role: str):
    form = await request.form()
    slug = (form.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "Slug is required.")
    from ...db.models import ENTITY_CHARACTER

    c = Character(
        slug=slug,
        name_tag=slug,
        display_name=slug,
        entity_type=ENTITY_CHARACTER,
        role=role,
    )
    try:
        with session_scope() as s:
            _ensure_unique_slug(s, slug)
            s.add(c)
            s.flush()
            await _save_character_or_raise(s, c, form)
    except ValidationSaveError as exc:
        return _render_form(request, role, c, validation_issues=exc.issues, form=form)
    bump_revision()
    return embed_redirect(request, _detail_url(role, slug), form=form)


@router.post("", response_class=HTMLResponse)
async def characters_create(request: Request):
    return await _do_create(request, ROLE_MAIN)


@partner_router.post("", response_class=HTMLResponse)
async def partners_create(request: Request):
    return await _do_create(request, ROLE_PARTNER)


def _do_edit(request: Request, role: str, slug: str):
    with session_scope() as s:
        c = s.scalar(
            select(Character)
            .where(Character.slug == slug, Character.role == role)
        )
        if c is None:
            raise HTTPException(404, f"{role} not found")
        _ = c.character_lora
    return _render_form(request, role, c)


@router.get("/{slug}", response_class=HTMLResponse, name="characters_edit")
def characters_edit(request: Request, slug: str):
    return _do_edit(request, ROLE_MAIN, slug)


@partner_router.get("/{slug}", response_class=HTMLResponse, name="partners_edit")
def partners_edit(request: Request, slug: str):
    return _do_edit(request, ROLE_PARTNER, slug)


async def _do_update(request: Request, role: str, slug: str):
    form = await request.form()
    new_slug = (form.get("slug") or "").strip() or slug
    try:
        with session_scope() as s:
            c = s.scalar(
                select(Character).where(Character.slug == slug, Character.role == role)
            )
            if c is None:
                raise HTTPException(404, f"{role} not found")
            if new_slug != c.slug:
                _ensure_unique_slug(s, new_slug, exclude_id=c.id)
            await _save_character_or_raise(s, c, form)
    except ValidationSaveError as exc:
        return _render_form(request, role, c, validation_issues=exc.issues, form=form)
    bump_revision()
    return embed_redirect(request, _detail_url(role, new_slug), form=form)


@router.post("/{slug}", response_class=HTMLResponse)
async def characters_update(request: Request, slug: str):
    return await _do_update(request, ROLE_MAIN, slug)


@partner_router.post("/{slug}", response_class=HTMLResponse)
async def partners_update(request: Request, slug: str):
    return await _do_update(request, ROLE_PARTNER, slug)


def _do_delete(role: str, slug: str):
    with session_scope() as s:
        c = s.scalar(
            select(Character).where(Character.slug == slug, Character.role == role)
        )
        if c is not None:
            clear_uploaded_image(c.image_path)
            s.delete(c)
    bump_revision()
    return RedirectResponse(_list_url(role), status_code=303)


@router.post("/{slug}/delete", response_class=HTMLResponse)
def characters_delete(slug: str):
    return _do_delete(ROLE_MAIN, slug)


@partner_router.post("/{slug}/delete", response_class=HTMLResponse)
def partners_delete(slug: str):
    return _do_delete(ROLE_PARTNER, slug)


# ---------------------------------------------------------------------------
# Form -> model
# ---------------------------------------------------------------------------


async def _apply_character_form(s, c: Character, form) -> None:
    c.slug = (form.get("slug") or c.slug or "").strip()
    c.display_name = (form.get("display_name") or c.slug).strip()
    c.name_tag = (form.get("name_tag") or c.slug or "").strip()
    c.comment = (form.get("comment") or "").strip() or None

    # role is set on create and via a hidden field on update — we trust it.
    requested_role = (form.get("role") or c.role or ROLE_MAIN).strip()
    if requested_role in (ROLE_MAIN, ROLE_PARTNER):
        c.role = requested_role

    c.identity_core = parse_taglist(form.get("identity_core"))
    for key, value in parse_outfit_form(form).items():
        setattr(c, key, value)

    c.partner_position = parse_int(form.get("partner_position"))

    # Reference image — multipart upload or "clear" checkbox
    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(c.image_path)
        c.image_path = None
    else:
        upload = form.get("image")
        c.image_path = save_uploaded_image(
            upload, entity="characters", slug=c.slug, existing=c.image_path
        )

    for attr in char_attrs.attributes_for_role(c.role or ROLE_MAIN):
        setattr(
            c,
            attr.key,
            char_attrs.coerce_physical_incoming(attr, form.get(attr.key)),
        )

    # Inline LoRA — present on every character form (partners can have a LoRA too)
    lora_kind = LORA_KIND_PARTNER if c.role == ROLE_PARTNER else LORA_KIND_CHARACTER
    lora_fields = parse_inline_lora_form(form, "lora_")
    new_lora_id = apply_inline_lora(
        s,
        kind=lora_kind,
        existing_id=c.lora_id,
        **lora_fields,
    )
    c.lora_id = new_lora_id


# ---------------------------------------------------------------------------
# Monsters + objects (simplified editors — not the character form)
# ---------------------------------------------------------------------------


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


def _get_simple_entity(session, entity_type: str, slug: str) -> Character:
    row = session.scalar(
        select(Character).where(Character.slug == slug, Character.entity_type == entity_type)
    )
    if row is None:
        meta = _simple_entity_meta(entity_type)
        raise HTTPException(404, f"{meta['kind_label'].lower()} not found")
    return row


async def _apply_simple_entity_form(session, entity: Character, form, *, upload_entity: str) -> None:
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


def _render_simple_entity_form(request: Request, entity_type: str, entity: Character):
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
        blank = Character(
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
            if s.scalar(select(Character.id).where(Character.slug == slug)) is not None:
                raise HTTPException(400, f"Choose a different slug — '{slug}' is already in use.")
            entity = Character(
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
            if new_slug != slug and s.scalar(
                select(Character.id).where(Character.slug == new_slug, Character.id != entity.id)
            ) is not None:
                raise HTTPException(400, f"Choose a different slug — '{new_slug}' is already in use.")
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

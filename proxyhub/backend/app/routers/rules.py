from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth import get_current_user
from app.models.rule import CustomRule
from app.services.parser import parse_text_or_base64

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCreate(BaseModel):
    rule_type: str = "direct"       # direct / proxy / reject
    pattern: str                    # e.g. "example.com"
    match_type: str = "DOMAIN-SUFFIX"
    remark: Optional[str] = None
    priority: int = 100


class RuleUpdate(BaseModel):
    rule_type: Optional[str] = None
    pattern: Optional[str] = None
    match_type: Optional[str] = None
    remark: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class ParseTextRequest(BaseModel):
    text: str


@router.get("/")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(CustomRule).order_by(CustomRule.priority.asc(), CustomRule.id.asc())
    )
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "rule_type": r.rule_type, "pattern": r.pattern,
            "match_type": r.match_type, "remark": r.remark,
            "enabled": r.enabled, "priority": r.priority,
            "created_at": r.created_at,
        }
        for r in rules
    ]


@router.post("/", status_code=201)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    rule = CustomRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"id": rule.id, "message": "规则已添加"}


@router.put("/{rule_id}")
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(CustomRule).where(CustomRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(CustomRule).where(CustomRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.delete(rule)
    await db.commit()
    return {"message": "删除成功"}


@router.delete("/batch/delete")
async def batch_delete_rules(
    rule_ids: List[int],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    await db.execute(delete(CustomRule).where(CustomRule.id.in_(rule_ids)))
    await db.commit()
    return {"message": f"已删除 {len(rule_ids)} 条规则"}


@router.post("/parse-text")
async def parse_nodes_from_text(
    body: ParseTextRequest,
    _: str = Depends(get_current_user),
):
    """
    Universal NekoBox-style parser:
    1. If user pasted an HTTP/HTTPS URL -> identify as subscription URL.
    2. Otherwise -> decode (Base64/URI/YAML) and parse into nodes.
    """
    raw = (body.text or "").strip()
    # Check if single or multiple HTTP URLs
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if len(lines) == 1 and (lines[0].startswith("http://") or lines[0].startswith("https://")):
        url = lines[0]
        # Attempt auto-name detection
        from app.services.parser import fetch_subscription
        auto_name = None
        try:
            _, auto_name = await fetch_subscription(url, timeout=5)
        except Exception:
            pass
        return {
            "type": "subscription_url",
            "url": url,
            "auto_name": auto_name or "新订阅源",
            "count": 0,
            "nodes": [],
        }

    # Otherwise parse as nodes
    nodes = parse_text_or_base64(raw)
    return {
        "type": "nodes",
        "url": None,
        "auto_name": None,
        "count": len(nodes),
        "nodes": nodes,
    }


@router.post("/parse-file")
async def parse_nodes_from_file(
    file: UploadFile = File(...),
    _: str = Depends(get_current_user),
):
    """
    Parse nodes directly from an uploaded file (YAML, txt, json, conf)
    Supports large files (up to 50MB) without text payload limits.
    """
    from fastapi import UploadFile
    content_bytes = await file.read()
    try:
        raw = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = content_bytes.decode("latin-1", errors="ignore")

    nodes = parse_text_or_base64(raw)
    return {
        "type": "nodes",
        "url": None,
        "auto_name": file.filename,
        "count": len(nodes),
        "nodes": nodes,
    }



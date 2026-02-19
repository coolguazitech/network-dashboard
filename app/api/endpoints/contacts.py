"""
Contacts (通訊錄) API endpoints.

通訊錄功能的 API 端點，支援分類管理和聯絡人 CRUD。
"""
from __future__ import annotations

import csv
import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.endpoints.auth import get_current_user, require_write
from app.db.base import get_session_context
from app.db.models import Contact, ContactCategory

router = APIRouter(prefix="/contacts", tags=["Contacts"])


# ========== Pydantic Schemas ==========


class ContactCategoryCreate(BaseModel):
    """創建通訊錄分類。"""

    maintenance_id: str
    name: str
    description: str | None = None
    color: str | None = "#3B82F6"
    icon: str | None = None


class ContactCategoryUpdate(BaseModel):
    """更新通訊錄分類。"""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None


class ContactCategoryResponse(BaseModel):
    """分類回應。"""

    id: int
    name: str
    description: str | None
    color: str | None
    icon: str | None
    sort_order: int
    contact_count: int


class ContactCreate(BaseModel):
    """創建聯絡人。"""

    category_id: int | None = None
    name: str
    title: str | None = None
    department: str | None = None
    company: str | None = None
    phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    extension: str | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    """更新聯絡人。"""

    category_id: int | None = None
    name: str | None = None
    title: str | None = None
    department: str | None = None
    company: str | None = None
    phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    extension: str | None = None
    notes: str | None = None
    sort_order: int | None = None


class ContactResponse(BaseModel):
    """聯絡人回應。"""

    id: int
    category_id: int | None
    category_name: str | None = None
    name: str
    title: str | None
    department: str | None
    company: str | None
    phone: str | None
    mobile: str | None
    email: str | None
    extension: str | None
    notes: str | None


# ========== Category Endpoints ==========


@router.get("/categories/{maintenance_id}", response_model=list[ContactCategoryResponse])
async def list_contact_categories(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict[str, Any]]:
    """獲取該歲修的所有通訊錄分類。"""
    async with get_session_context() as session:
        stmt = (
            select(
                ContactCategory,
                func.count(Contact.id).label("contact_count"),
            )
            .outerjoin(Contact, Contact.category_id == ContactCategory.id)
            .where(
                ContactCategory.maintenance_id == maintenance_id,
                ContactCategory.is_active == True,
            )
            .group_by(ContactCategory.id)
            .order_by(ContactCategory.sort_order)
        )
        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "color": cat.color,
                "icon": cat.icon,
                "sort_order": cat.sort_order,
                "contact_count": count,
            }
            for cat, count in rows
        ]


@router.post("/categories", response_model=ContactCategoryResponse)
async def create_contact_category(
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: ContactCategoryCreate,
) -> dict[str, Any]:
    """創建通訊錄分類。"""
    async with get_session_context() as session:
        # 檢查名稱重複
        stmt = select(ContactCategory).where(
            ContactCategory.maintenance_id == data.maintenance_id,
            ContactCategory.name == data.name,
            ContactCategory.is_active == True,
        )
        existing = await session.execute(stmt)
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"分類 '{data.name}' 已存在")

        # 獲取當前分類數量作為排序
        count_stmt = (
            select(func.count())
            .select_from(ContactCategory)
            .where(
                ContactCategory.maintenance_id == data.maintenance_id,
                ContactCategory.is_active == True,
            )
        )
        count_result = await session.execute(count_stmt)
        current_count = count_result.scalar() or 0

        category = ContactCategory(
            maintenance_id=data.maintenance_id,
            name=data.name,
            description=data.description,
            color=data.color,
            icon=data.icon,
            sort_order=current_count,
        )
        session.add(category)
        await session.commit()
        await session.refresh(category)

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "color": category.color,
            "icon": category.icon,
            "sort_order": category.sort_order,
            "contact_count": 0,
        }


@router.put("/categories/{category_id}", response_model=ContactCategoryResponse)
async def update_contact_category(
    category_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: ContactCategoryUpdate,
) -> dict[str, Any]:
    """更新通訊錄分類。"""
    async with get_session_context() as session:
        stmt = select(ContactCategory).where(ContactCategory.id == category_id)
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()

        if not category:
            raise HTTPException(status_code=404, detail="分類不存在")

        # 更新欄位
        if data.name is not None:
            category.name = data.name
        if data.description is not None:
            category.description = data.description
        if data.color is not None:
            category.color = data.color
        if data.icon is not None:
            category.icon = data.icon
        if data.sort_order is not None:
            category.sort_order = data.sort_order

        await session.commit()
        await session.refresh(category)

        # 計算成員數
        count_stmt = (
            select(func.count())
            .select_from(Contact)
            .where(
                Contact.category_id == category_id,
                Contact.is_active == True,
            )
        )
        count_result = await session.execute(count_stmt)
        contact_count = count_result.scalar() or 0

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "color": category.color,
            "icon": category.icon,
            "sort_order": category.sort_order,
            "contact_count": contact_count,
        }


@router.delete("/categories/{category_id}")
async def delete_contact_category(
    category_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, str]:
    """刪除通訊錄分類（硬刪除），並將該分類下的聯絡人移至未分類。"""
    async with get_session_context() as session:
        stmt = select(ContactCategory).where(ContactCategory.id == category_id)
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()

        if not category:
            raise HTTPException(status_code=404, detail="分類不存在")

        category_name = category.name

        # 將該分類下的所有聯絡人的 category_id 設為 NULL（未分類）
        from sqlalchemy import update
        update_stmt = (
            update(Contact)
            .where(Contact.category_id == category_id)
            .values(category_id=None)
        )
        await session.execute(update_stmt)

        # 硬刪除分類（從資料庫中完全移除）
        await session.delete(category)
        await session.commit()

        return {"message": f"分類 '{category_name}' 已刪除，聯絡人已移至未分類"}


# ========== Contact Endpoints ==========


@router.get("/{maintenance_id}", response_model=list[ContactResponse])
async def list_contacts(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    category_id: int | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """獲取通訊錄聯絡人列表。"""
    async with get_session_context() as session:
        stmt = (
            select(Contact, ContactCategory.name.label("category_name"))
            .outerjoin(ContactCategory, Contact.category_id == ContactCategory.id)
            .where(
                Contact.maintenance_id == maintenance_id,
                Contact.is_active == True,
            )
        )

        if category_id:
            stmt = stmt.where(Contact.category_id == category_id)

        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                (Contact.name.ilike(search_pattern))
                | (Contact.phone.ilike(search_pattern))
                | (Contact.mobile.ilike(search_pattern))
                | (Contact.email.ilike(search_pattern))
                | (Contact.department.ilike(search_pattern))
                | (Contact.company.ilike(search_pattern))
            )

        stmt = stmt.order_by(
            ContactCategory.sort_order, Contact.sort_order, Contact.name
        )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": contact.id,
                "category_id": contact.category_id,
                "category_name": cat_name,
                "name": contact.name,
                "title": contact.title,
                "department": contact.department,
                "company": contact.company,
                "phone": contact.phone,
                "mobile": contact.mobile,
                "email": contact.email,
                "extension": contact.extension,
                "notes": contact.notes,
            }
            for contact, cat_name in rows
        ]


@router.post("/{maintenance_id}", response_model=ContactResponse)
async def create_contact(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: ContactCreate,
) -> dict[str, Any]:
    """新增聯絡人。"""
    async with get_session_context() as session:
        category_name = None

        # 如果有指定分類，驗證分類存在且屬於該歲修
        if data.category_id is not None:
            cat_stmt = select(ContactCategory).where(
                ContactCategory.id == data.category_id,
                ContactCategory.maintenance_id == maintenance_id,
            )
            cat_result = await session.execute(cat_stmt)
            category = cat_result.scalar_one_or_none()

            if not category:
                raise HTTPException(status_code=404, detail="分類不存在或不屬於該歲修")
            category_name = category.name

        contact = Contact(
            maintenance_id=maintenance_id,
            category_id=data.category_id,
            name=data.name,
            title=data.title,
            department=data.department,
            company=data.company,
            phone=data.phone,
            mobile=data.mobile,
            email=data.email,
            extension=data.extension,
            notes=data.notes,
        )
        session.add(contact)
        await session.commit()
        await session.refresh(contact)

        return {
            "id": contact.id,
            "category_id": contact.category_id,
            "category_name": category_name,
            "name": contact.name,
            "title": contact.title,
            "department": contact.department,
            "company": contact.company,
            "phone": contact.phone,
            "mobile": contact.mobile,
            "email": contact.email,
            "extension": contact.extension,
            "notes": contact.notes,
        }


@router.put("/{maintenance_id}/{contact_id}", response_model=ContactResponse)
async def update_contact(
    maintenance_id: str,
    contact_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: ContactUpdate,
) -> dict[str, Any]:
    """更新聯絡人。"""
    async with get_session_context() as session:
        stmt = select(Contact).where(
            Contact.id == contact_id,
            Contact.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=404, detail="聯絡人不存在")

        # 更新欄位（只更新有明確提供的欄位）
        for field in [
            "category_id",
            "name",
            "title",
            "department",
            "company",
            "phone",
            "mobile",
            "email",
            "extension",
            "notes",
            "sort_order",
        ]:
            # 使用 model_fields_set 檢查欄位是否有明確提供
            if field in data.model_fields_set:
                value = getattr(data, field)
                setattr(contact, field, value)

        await session.commit()
        await session.refresh(contact)

        # 獲取分類名稱
        cat_stmt = select(ContactCategory.name).where(
            ContactCategory.id == contact.category_id
        )
        cat_result = await session.execute(cat_stmt)
        cat_name = cat_result.scalar()

        return {
            "id": contact.id,
            "category_id": contact.category_id,
            "category_name": cat_name,
            "name": contact.name,
            "title": contact.title,
            "department": contact.department,
            "company": contact.company,
            "phone": contact.phone,
            "mobile": contact.mobile,
            "email": contact.email,
            "extension": contact.extension,
            "notes": contact.notes,
        }


@router.delete("/{maintenance_id}/{contact_id}")
async def delete_contact(
    maintenance_id: str,
    contact_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, str]:
    """刪除聯絡人。"""
    async with get_session_context() as session:
        stmt = select(Contact).where(
            Contact.id == contact_id,
            Contact.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(status_code=404, detail="聯絡人不存在")

        await session.delete(contact)
        await session.commit()

        return {"message": f"聯絡人 '{contact.name}' 已刪除"}


@router.post("/{maintenance_id}/import-csv")
async def import_contacts_csv(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    批量匯入聯絡人。

    CSV 格式:
    category_name,name,title,department,company,phone,mobile,email,extension,notes

    會自動建立不存在的分類。
    """
    DEFAULT_COLORS = [
        "#3B82F6",
        "#10B981",
        "#F59E0B",
        "#EF4444",
        "#8B5CF6",
        "#EC4899",
    ]

    async with get_session_context() as session:
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("utf-8")

        reader = csv.DictReader(io.StringIO(text))

        # 獲取現有分類
        cat_stmt = select(ContactCategory).where(
            ContactCategory.maintenance_id == maintenance_id,
            ContactCategory.is_active == True,
        )
        cat_result = await session.execute(cat_stmt)
        existing_categories = {c.name: c for c in cat_result.scalars().all()}

        categories_created = 0
        contacts_imported = 0
        errors = []
        color_idx = len(existing_categories)

        for row_num, row in enumerate(reader, start=2):
            cat_name = row.get("category_name", "").strip() or "未分類"
            name = row.get("name", "").strip()

            if not name:
                errors.append(f"Row {row_num}: 姓名為空")
                continue

            # 建立或獲取分類
            if cat_name not in existing_categories:
                category = ContactCategory(
                    maintenance_id=maintenance_id,
                    name=cat_name,
                    color=DEFAULT_COLORS[color_idx % len(DEFAULT_COLORS)],
                    sort_order=color_idx,
                )
                session.add(category)
                await session.flush()
                existing_categories[cat_name] = category
                categories_created += 1
                color_idx += 1

            # 新增聯絡人
            contact = Contact(
                maintenance_id=maintenance_id,
                category_id=existing_categories[cat_name].id,
                name=name,
                title=row.get("title", "").strip() or None,
                department=row.get("department", "").strip() or None,
                company=row.get("company", "").strip() or None,
                phone=row.get("phone", "").strip() or None,
                mobile=row.get("mobile", "").strip() or None,
                email=row.get("email", "").strip() or None,
                extension=row.get("extension", "").strip() or None,
                notes=row.get("notes", "").strip() or None,
            )
            session.add(contact)
            contacts_imported += 1

        await session.commit()

        return {
            "categories_created": categories_created,
            "contacts_imported": contacts_imported,
            "errors": errors[:10],
            "total_errors": len(errors),
        }

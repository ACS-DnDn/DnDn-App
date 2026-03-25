import os
import json
import logging
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def _to_kst_str(dt: datetime | None) -> str:
    """UTC datetime → KST 'YYYY-MM-DD HH:MM' 문자열"""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")

from apps.api.src.database import get_db
from apps.api.src.models import Document, Approval, User, DocumentRead, Attachment, Workspace
from apps.api.src.routers.auth import get_current_user
from apps.api.src.schemas.common import SuccessResponse
from apps.api.src.schemas.documents import (
    DocumentSubmitRequest,
    DocumentSubmitResponse,
    DocumentArchiveResponse,
    DocumentApproveRequest,
    DocumentStatusResponse,
    DocumentRejectRequest,
    DocumentReadRequest,
    DocumentReadResponse,
    DocumentReadAllRequest,
    RefDocMetaItem,
    RefDocumentDetailResponse,
    DocumentDetailResponse,
)
import requests.exceptions as requests_exc
from apps.api.src.security.slack_oauth import send_message, SlackError
from apps.api.src.security.github_oauth import create_terraform_pr, GitHubError

_S3_BUCKET = os.getenv("S3_BUCKET", "")
_AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
_S3_CLIENT = None


def _get_s3_client():
    """
    Lazily initialize and cache a boto3 S3 client at module level
    to avoid repeated client creation overhead.
    """
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client("s3", region_name=_AWS_REGION)
    return _S3_CLIENT


def _s3_get_text(key: str) -> str | None:
    """S3에서 텍스트 파일 내용을 가져옵니다. 실패 시 None 반환."""
    if not key or not _S3_BUCKET:
        return None
    try:
        s3 = _get_s3_client()
        obj = s3.get_object(Bucket=_S3_BUCKET, Key=key)
        return obj["Body"].read().decode("utf-8")
    except ClientError:
        return None


def _s3_get_json(key: str) -> dict | None:
    """S3에서 JSON 파일을 가져와 dict로 반환합니다. 실패 시 None 반환."""
    text = _s3_get_text(key)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# 프론트엔드는 /documents 로 요청합니다.
router = APIRouter(prefix="/documents", tags=["Documents"])


def _notify(user: User, text: str) -> None:
    """결재 관련 Slack DM 알림 — 실패해도 메인 플로우에 영향 없음."""
    if user and user.slack_access_token and user.slack_notify is not False and user.slack_user_id:
        try:
            send_message(user.slack_access_token, user.slack_user_id, text)
        except SlackError:
            pass


_logger = logging.getLogger(__name__)

# ── 문서번호 채번 ──────────────────────────────────────────────
_DOC_TYPE_CODE = {
    "계획서": "PLN",
    "이벤트보고서": "EVT",
    "헬스이벤트보고서": "RPT",
    "주간보고서": "RPT",
}


def _next_doc_num(db: "Session", doc_type: str) -> str:
    """연도-종류-일련번호 형식의 문서번호 채번 (예: 2026-PLN-0001)."""
    from sqlalchemy import cast, Integer, func as sa_func

    code = _DOC_TYPE_CODE.get(doc_type, "DOC")
    year = datetime.now(KST).year
    prefix = f"{year}-{code}-"

    suffix_expr = sa_func.substr(Document.doc_num, len(prefix) + 1)
    max_seq = (
        db.query(sa_func.max(cast(suffix_expr, Integer)))
        .filter(Document.doc_num.like(f"{prefix}%"))
        .scalar()
    )
    seq = (max_seq or 0) + 1
    return f"{prefix}{seq:04d}"


def _s3_put_text(key: str, content: str) -> None:
    """S3에 텍스트 파일을 저장합니다."""
    if not key or not _S3_BUCKET:
        return
    _get_s3_client().put_object(
        Bucket=_S3_BUCKET, Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )


def _s3_list_terraform_files(prefix: str) -> dict[str, str]:
    """S3 prefix 아래의 terraform 파일들을 {filename: content} 딕셔너리로 반환."""
    if not prefix or not _S3_BUCKET:
        return {}
    s3 = _get_s3_client()
    result = {}
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_S3_BUCKET, Prefix=prefix + "/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.rsplit("/", 1)[-1]
                if not filename:
                    continue
                body = s3.get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read().decode("utf-8")
                result[filename] = body
    except ClientError as e:
        _logger.warning("terraform S3 파일 조회 실패: %s", e)
    return result


def _create_terraform_pr_if_needed(doc: Document, db: "Session") -> None:
    """최종결재 완료 시 terraform 파일이 있으면 고객 repo에 PR 생성."""
    if not doc.terraform_key:
        return

    # 워크스페이스 정보
    ws = db.query(Workspace).filter(Workspace.id == doc.workspace_id).first()
    if not ws:
        _logger.warning("terraform PR: 워크스페이스 없음 (doc=%s)", doc.id)
        return

    # GitHub 토큰 — 워크스페이스 owner의 토큰 사용
    owner_user = db.query(User).filter(User.id == ws.owner_id).first()
    if not owner_user or not owner_user.github_access_token:
        _logger.warning("terraform PR: GitHub 토큰 없음 (workspace=%s)", ws.id)
        return

    # S3에서 terraform 파일 가져오기
    tf_files = _s3_list_terraform_files(doc.terraform_key)
    if not tf_files:
        _logger.warning("terraform PR: S3에 terraform 파일 없음 (key=%s)", doc.terraform_key)
        return

    # 브랜치명·PR 제목·본문 구성
    doc_num = doc.doc_num or doc.id[:8]
    head_branch = f"dndn/{doc_num}"
    pr_title = f"[DnDn] {doc.title}"
    author_name = doc.author.name if doc.author else "DnDn"
    pr_body = (
        f"> **이 PR은 [DnDn](https://www.dndn.cloud) 결재 시스템에 의해 자동 생성되었습니다.**\n\n"
        f"## 📋 문서 정보\n"
        f"- **문서번호**: `{doc_num}`\n"
        f"- **제목**: {doc.title}\n"
        f"- **유형**: {doc.type}\n"
        f"- **작성자**: {author_name}\n\n"
        f"## 📂 Terraform 파일\n"
        + "\n".join(f"- `{fn}`" for fn in tf_files.keys())
        + "\n\n---\n🤖 *Generated by DnDn — Cloud Compliance & Automation Platform*"
    )

    try:
        result = create_terraform_pr(
            token=owner_user.github_access_token,
            owner=ws.github_org,
            repo=ws.repo,
            base_branch=ws.branch,
            head_branch=head_branch,
            files=tf_files,
            title=pr_title,
            body=pr_body,
            path_prefix=ws.path or None,
        )
        _logger.info("terraform PR 생성 완료: %s", result["pr_url"])
        # PR 정보 DB 저장 (caller가 commit)
        doc.pr_number = result["pr_number"]
        doc.pr_url = result["pr_url"]
        doc.pr_status = "open"
    except GitHubError as e:
        _logger.error("terraform PR 생성 실패: %s", e.message)
    except (requests_exc.RequestException, KeyError, ValueError) as e:
        _logger.error("terraform PR 생성 예외 (%s): %s", type(e).__name__, e)


def _has_document_access(db: "Session", doc: Document, current_user: User) -> bool:
    """문서 접근 권한 확인: 작성자 / 결재선 / 같은 워크스페이스(회사·부서)."""
    if doc.author_id is not None and doc.author_id == current_user.id:
        return True
    is_approver = (
        db.query(Approval)
        .filter(Approval.document_id == doc.id, Approval.user_id == current_user.id)
        .first()
        is not None
    )
    if is_approver:
        return True
    if doc.workspace_id:
        ws = db.query(Workspace).filter(Workspace.id == doc.workspace_id).first()
        if ws:
            owner = db.query(User).filter(User.id == ws.owner_id).first()
            if owner and owner.company_id == current_user.company_id and owner.department_id == current_user.department_id:
                return True
    return False


@router.get("", response_model=SuccessResponse[DocumentArchiveResponse])
def get_documents(
    tab: Optional[str] = Query(
        "all", description="action (처리할 문서) / all (전체 문서)"
    ),
    searchField: str = Query("name", description="name / author"),
    keyword: Optional[str] = Query(None, description="검색어"),
    type: Optional[str] = Query(None, description="문서 유형"),
    status: Optional[str] = Query(None, description="문서 상태"),
    dateFrom: Optional[str] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    dateTo: Optional[str] = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    pageSize: int = Query(10, ge=1, description="페이지당 항목 수"),
    archived: Optional[bool] = Query(
        None, description="참조 문서 검색용 (과거 명세 호환)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 내 워크스페이스(같은 회사·부서) 문서 쿼리
    my_ws_ids = (
        db.query(Workspace.id)
        .join(User, Workspace.owner_id == User.id)
        .filter(
            User.company_id == current_user.company_id,
            User.department_id == current_user.department_id,
        )
    )

    # 💡 [호환성 로직] 참조 문서 검색에서 archived=true로 찌른 경우
    if archived:
        query = db.query(Document).filter(
            Document.workspace_id.in_(my_ws_ids), Document.status == "done"
        )
    elif tab == "action":
        # 결재 대상 문서는 워크스페이스 무관 — Approval 기준으로 직접 조회
        query = (
            db.query(Document)
            .join(Approval, Approval.document_id == Document.id)
            .filter(Approval.user_id == current_user.id)
            .filter(Approval.status.in_(["current", "rejected"]))
        )
    else:
        query = db.query(Document).filter(
            Document.workspace_id.in_(my_ws_ids),
            Document.status != "draft",
        )

    # 3. 검색어(keyword) 필터링
    if keyword:
        if searchField == "name":
            query = query.filter(Document.title.ilike(f"%{keyword}%"))
        elif searchField == "author":
            query = query.join(User, Document.author_id == User.id)
            query = query.filter(User.name.ilike(f"%{keyword}%"))

    # 4. 유형(type) 필터링
    if type:
        query = query.filter(Document.type == type)

    # 5. 상태(status) 필터링 (archived가 아닐 때만)
    if status and not archived:
        query = query.filter(Document.status == status)

    # 6. 날짜(dateFrom, dateTo) 필터링
    try:
        from_dt = datetime.strptime(dateFrom, "%Y-%m-%d") if dateFrom else None
        to_dt = datetime.strptime(dateTo, "%Y-%m-%d") if dateTo else None
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_DATE_FORMAT")
    if from_dt:
        query = query.filter(Document.created_at >= from_dt)
    if to_dt:
        # 해당 일자의 23:59:59 까지 포함하도록 설정
        to_dt = to_dt.replace(hour=23, minute=59, second=59)
        query = query.filter(Document.created_at <= to_dt)

    # 7. 전체 개수 구하기 (JOIN 시 문서 중복 방지)
    query = query.distinct()
    total_count = query.count()

    # 8. 정렬 및 페이징
    offset = (page - 1) * pageSize
    documents = (
        query.order_by(Document.created_at.desc()).offset(offset).limit(pageSize).all()
    )

    # tab == "action" 인 경우, 모든 문서에 대한 Approval 을 한 번에 조회하여 N+1 문제를 방지
    approvals_by_doc_id = {}
    if tab == "action" and documents:
        doc_ids = [doc.id for doc in documents]
        approvals = (
            db.query(Approval)
            .filter(
                Approval.document_id.in_(doc_ids),
                Approval.user_id == current_user.id,
            )
            .all()
        )
        approvals_by_doc_id = {approval.document_id: approval for approval in approvals}

    # 8-1. 현재 사용자 기준 문서 읽음 여부를 한 번에 조회 (N+1 쿼리 방지)
    doc_ids = [doc.id for doc in documents]
    read_document_ids = set()
    if doc_ids:
        read_rows = (
            db.query(DocumentRead.document_id)
            .filter(
                DocumentRead.user_id == current_user.id,
                DocumentRead.document_id.in_(doc_ids),
            )
            .all()
        )
        read_document_ids = {row.document_id for row in read_rows}

    # 9. 응답 데이터 조립
    items = []
    for doc in documents:
        is_read_flag = doc.id in read_document_ids
        # action 값 계산 (명세서: 내가 결재해야 하면 'approve', 내가 반려했으면 'rejected', 없으면 null)
        action_val = None
        if tab == "action":
            my_approval = approvals_by_doc_id.get(doc.id)

            if my_approval:
                if my_approval.status == "current":
                    action_val = "approve"
                elif my_approval.status == "rejected":
                    action_val = "rejected"

        items.append(
            {
                "id": str(doc.id),
                "docNum": doc.doc_num or str(doc.id)[:8],
                "name": doc.title,
                "author": doc.author.name if doc.author else "DnDn Agent",
                "date": _to_kst_str(doc.created_at),
                "type": doc.type,
                "status": doc.status,
                "action": action_val,
                "isRead": is_read_flag,
                "prStatus": doc.pr_status,
            }
        )

    return SuccessResponse(
        data=DocumentArchiveResponse(
            total=total_count, page=page, pageSize=pageSize, items=items
        )
    )


@router.post(
    "", response_model=SuccessResponse[DocumentSubmitResponse], status_code=status.HTTP_201_CREATED
)
def submit_document(
    req: DocumentSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 대상 문서(임시저장본) 찾기
    # (AI 워커가 끝날 때 Document 테이블에 가안을 만들어 둔다고 가정합니다.)
    doc = db.query(Document).filter(Document.id == req.documentId).first()

    if not doc:
        # 대상 문서가 존재하지 않으면 404를 반환합니다.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DOCUMENT_NOT_FOUND",
        )

    # 2. 임시 문서 만료 검사 (400 DRAFT_EXPIRED)
    # 문서 생성일이 24시간을 넘었는지 체크합니다.
    if doc.created_at:
        created = doc.created_at.replace(tzinfo=timezone.utc) if doc.created_at.tzinfo is None else doc.created_at
        time_diff = datetime.now(timezone.utc) - created
        if time_diff > timedelta(hours=24):
            raise HTTPException(status_code=400, detail="DRAFT_EXPIRED")

    # 3. 결재자(Approver) ID 검증 (400 INVALID_APPROVER)
    # 프론트엔드에서 보낸 userId들이 실제로 DB에 있는 사람들인지 확인합니다.
    approver_ids = [app.userId for app in req.approvers]
    if approver_ids:
        existing_users_count = (
            db.query(User.id).filter(User.id.in_(approver_ids)).count()
        )
        if existing_users_count != len(approver_ids):
            raise HTTPException(status_code=400, detail="INVALID_APPROVER")

    # 4. 문서 정보 업데이트
    doc.workspace_id = req.workspaceId
    doc.work_date = req.work_date
    doc.ref_doc_ids = req.refDocIds
    doc.is_draft = req.isDraft
    if req.authorComment is not None:
        doc.submit_comment = req.authorComment.strip()

    # 임시저장(isDraft=true)이면 draft, 상신(isDraft=false)이면 progress 상태로 변경
    doc.status = "draft" if req.isDraft else "progress"

    # 상신 시 doc_num이 없으면 채번 (S3 HTML 갱신은 commit 후 수행)
    need_html_update = False
    if not req.isDraft and not doc.doc_num:
        doc.doc_num = _next_doc_num(db, doc.type or "계획서")
        need_html_update = bool(doc.html_key)

    # 5. 기존 결재선이 있다면 싹 지우고 새로 그리기 (덮어쓰기)
    db.query(Approval).filter(Approval.document_id == doc.id).delete()
    db.flush()

    # 6. 새로운 결재선 등록
    for app in req.approvers:
        # 상신 상태(isDraft=false)일 때, 첫 번째 결재자(seq=1)는 바로 'current(결재 대기)' 상태가 되고, 나머지는 'wait'가 됩니다.
        # 임시저장 상태면 모두 'wait'로 둡니다.
        approval_status = "wait"
        if not req.isDraft and app.seq == 1:
            approval_status = "current"

        new_approval = Approval(
            document_id=doc.id,
            user_id=app.userId,
            seq=app.seq,
            type=app.type,
            status=approval_status,
        )
        db.add(new_approval)

    # 7. DB 최종 반영
    db.commit()
    db.refresh(doc)

    # 7-1. S3 HTML 문서번호 갱신 (commit 성공 후 수행 — DB/S3 불일치 방지)
    if need_html_update and doc.doc_num and doc.html_key:
        try:
            import re as _re
            html = _s3_get_text(doc.html_key)
            if html:
                # 헤더: 문서번호: XXX → 문서번호: 실제번호
                updated = _re.sub(
                    r'(문서번호:\s*)(.*?)(<br|</div>)',
                    rf'\g<1>{doc.doc_num}\3',
                    html,
                    flags=_re.DOTALL,
                )
                # 푸터: 기존 문서번호 텍스트 치환
                updated = _re.sub(
                    r'(<div\s+class="doc-footer"><span>).*?(\s*&nbsp;/&nbsp;)',
                    rf'\g<1>{doc.doc_num}\2',
                    updated,
                    flags=_re.DOTALL,
                )
                if updated != html:
                    _s3_put_text(doc.html_key, updated)
        except (ClientError, ValueError, TypeError) as e:
            _logger.warning("HTML 문서번호 갱신 실패: %s", e)

    # 8. 첫 번째 결재자에게 Slack 알림 (상신 시에만)
    if not req.isDraft:
        first_approver_id = next((a.userId for a in req.approvers if a.seq == 1), None)
        if first_approver_id:
            first_approver = db.query(User).filter(User.id == first_approver_id).first()
            author_name = doc.author.name if doc.author and doc.author.name else "알 수 없음"
            _notify(first_approver, f"📋 결재 요청: {doc.title} ({author_name})")

    # 9. 명세서에 맞는 응답 반환
    return SuccessResponse(
        data=DocumentSubmitResponse(
            id=str(doc.id), docNum=doc.doc_num or str(doc.id)[:8], status=doc.status
        )
    )


@router.get("/{documentId}", response_model=SuccessResponse[DocumentDetailResponse])
def get_document_detail(
    documentId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    if not _has_document_access(db, doc, current_user):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # S3에서 HTML 본문 가져오기
    content = _s3_get_text(doc.html_key) if doc.html_key else None

    # 참조 문서 목록
    ref_docs = []
    if doc.ref_doc_ids:
        ref_doc_records = (
            db.query(Document).filter(Document.id.in_(doc.ref_doc_ids)).all()
        )
        ref_docs = [
            {"id": r.id, "docNum": r.doc_num or str(r.id)[:8], "title": r.title, "type": r.type} for r in ref_doc_records
        ]

    # 첨부파일 목록
    attachments_list = [
        {"id": a.id, "name": a.original_name, "sizeKb": a.size_kb}
        for a in db.query(Attachment).filter(Attachment.document_id == doc.id).all()
    ]

    # 결재선 — 작성자를 첫 번째 항목으로 추가
    approval_line = [
        {
            "seq": 0,
            "type": "작성자",
            "name": doc.author.name if doc.author else "알수없음",
            "role": doc.author.position if doc.author else "",
            "status": "author",
            "date": doc.created_at.isoformat() if doc.created_at else None,
            "comment": doc.submit_comment,
        }
    ]
    for apv in sorted(doc.approvals, key=lambda a: a.seq):
        approval_line.append(
            {
                "seq": apv.seq,
                "type": apv.type or "결재",
                "name": apv.user.name if apv.user else "알수없음",
                "role": apv.user.position if apv.user else "",
                "status": apv.status,
                "date": apv.approval_date.isoformat() if apv.approval_date else None,
                "comment": apv.comment,
            }
        )

    # Terraform 코드 (S3에서 조회)
    terraform_data = _s3_list_terraform_files(doc.terraform_key) if doc.terraform_key else None

    # 현재 사용자의 결재 액션 (approve/rejected 가능 여부)
    my_approval = (
        db.query(Approval)
        .filter(Approval.document_id == documentId, Approval.user_id == current_user.id)
        .first()
    )
    action = None
    if my_approval and my_approval.status == "current":
        action = "approve"
    elif my_approval and my_approval.status == "rejected":
        action = "rejected"

    return SuccessResponse(
        data=DocumentDetailResponse(
            id=str(doc.id),
            docNum=doc.doc_num or str(doc.id)[:8],
            title=doc.title,
            type=doc.type,
            status=doc.status,
            action=action,
            authorId=str(doc.author_id) if doc.author_id else None,
            author={"name": doc.author.name if doc.author else "DnDn Agent", "role": doc.author.position if doc.author else ""},
            createdAt=doc.created_at.isoformat() if doc.created_at else None,
            content=content,
            terraform=terraform_data,
            refDocs=ref_docs,
            attachments=attachments_list,
            approvalLine=approval_line,
            prNumber=doc.pr_number,
            prUrl=doc.pr_url,
            prStatus=doc.pr_status,
        )
    )


@router.post(
    "/{documentId}/approve", response_model=SuccessResponse[DocumentStatusResponse]
)
def approve_document(
    documentId: str,
    req: DocumentApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 문서 존재 여부 확인 (404)
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    # 2. 내 결재 차례인지 확인 (403)
    my_approval = (
        db.query(Approval)
        .filter(Approval.document_id == documentId, Approval.user_id == current_user.id)
        .first()
    )

    # 내 결재 정보가 없거나, 상태가 "current"가 아니면 내 차례가 아님
    if not my_approval or my_approval.status != "current":
        raise HTTPException(status_code=403, detail="NOT_YOUR_TURN")

    # 3. 내 결재 상태를 '승인(approved)'으로 변경
    my_approval.status = "approved"

    # 코멘트가 있다면 저장하고, 결재 일시도 현재 시간으로 기록합니다.
    # 💡 주의: models.py의 Approval 테이블에 comment와 approval_date 컬럼이 없다면 추가해야 합니다!
    if req.comment:
        my_approval.comment = req.comment
    my_approval.approval_date = datetime.now(timezone.utc)

    # 4. 다음 결재자 찾기 (나의 seq + 1 인 사람)
    next_approval = (
        db.query(Approval)
        .filter(
            Approval.document_id == documentId,
            Approval.seq > my_approval.seq,
            Approval.status.in_(["wait", "current"]),
        )
        .order_by(Approval.seq.asc())
        .first()
    )

    # 5. 문서 상태 및 바통 터치 결정
    if next_approval:
        # 다음 사람이 있다면 그 사람의 상태를 "current"로 열어줍니다.
        next_approval.status = "current"
        new_status = "progress"  # 문서는 계속 진행 중
    else:
        # 다음 사람이 없다면 내가 최종 결재자! 문서를 완료 처리합니다.
        doc.status = "done"
        new_status = "done"

        # 🚀 최종 결재 시 Terraform PR 생성
        _create_terraform_pr_if_needed(doc, db)

    # 6. DB 최종 반영
    db.commit()

    # 7. Slack 알림
    if next_approval:
        next_user = db.query(User).filter(User.id == next_approval.user_id).first()
        author_name = doc.author.name if doc.author and doc.author.name else "알 수 없음"
        _notify(next_user, f"📋 결재 요청: {doc.title} ({author_name})")
    else:
        _notify(doc.author, f"✅ 결재 완료: {doc.title}")

    # 8. 공통 응답 규격으로 리턴
    return SuccessResponse(data=DocumentStatusResponse(newStatus=new_status))


@router.post(
    "/{documentId}/reject", response_model=SuccessResponse[DocumentStatusResponse]
)
def reject_document(
    documentId: str,
    req: DocumentRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 반려 사유 필수값 검증 (400)
    # Pydantic이 기본적으로 막아주긴 하지만, 공백("   ")만 보내는 꼼수를 막기 위해 한 번 더 체크합니다.
    if not req.comment or not req.comment.strip():
        raise HTTPException(status_code=400, detail="MISSING_COMMENT")

    # 2. 문서 존재 여부 확인 (404)
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    # 3. 내 결재 차례인지 확인 (403)
    my_approval = (
        db.query(Approval)
        .filter(Approval.document_id == documentId, Approval.user_id == current_user.id)
        .first()
    )

    if not my_approval or my_approval.status != "current":
        raise HTTPException(status_code=403, detail="NOT_YOUR_TURN")

    # 4. 내 결재 상태를 '반려(rejected)'로 변경하고 사유와 시간 기록
    my_approval.status = "rejected"
    my_approval.comment = req.comment
    my_approval.approval_date = datetime.now(timezone.utc)

    # 5. 문서 전체 상태를 '반려(rejected)'로 덮어쓰기
    # 💡 이 순간, 기안자(작성자)의 대시보드에 이 문서가 다시 'rejected' 상태로 뜨게 됩니다!
    doc.status = "rejected"

    # 6. DB 최종 반영
    db.commit()

    # 7. 작성자에게 Slack 알림
    _notify(doc.author, f"❌ 반려: {doc.title} — {req.comment}")

    # 8. 공통 응답 규격으로 리턴 (상태는 무조건 rejected)
    return SuccessResponse(data=DocumentStatusResponse(newStatus="rejected"))


@router.patch("/read", response_model=SuccessResponse[DocumentReadResponse])
def mark_documents_as_read(
    req: DocumentReadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 빈 리스트가 오면 그냥 성공 처리 (에러 낼 필요 없음)
    if not req.ids:
        return SuccessResponse(data=DocumentReadResponse(success=True))

    # 1. 전달받은 문서 ID들이 실제로 DB에 다 존재하는지 검증 (400 INVALID_IDS)
    # in_ 쿼리를 써서 한 번에 찾습니다. 성능 최적화!
    existing_docs = db.query(Document.id).filter(Document.id.in_(req.ids)).all()
    existing_ids = {str(doc.id) for doc in existing_docs}

    missing_ids = set(req.ids) - existing_ids
    if missing_ids:
        raise HTTPException(status_code=400, detail="INVALID_IDS")

    # 2. 이미 읽음 처리된 문서가 있는지 확인 후, 안 읽은 것만 삽입
    # (이미 읽은 걸 또 읽었다고 에러를 낼 필요는 없으므로 부드럽게 무시합니다)
    already_read_docs = (
        db.query(DocumentRead.document_id)
        .filter(
            DocumentRead.user_id == current_user.id,
            DocumentRead.document_id.in_(req.ids),
        )
        .all()
    )
    already_read_ids = {str(r.document_id) for r in already_read_docs}

    # 아직 안 읽은 진짜 새 문서들만 골라냅니다.
    ids_to_insert = set(req.ids) - already_read_ids

    # 3. DB에 일괄 추가 (Bulk Insert)
    if ids_to_insert:
        new_reads = [
            DocumentRead(user_id=current_user.id, document_id=doc_id)
            for doc_id in ids_to_insert
        ]
        db.add_all(new_reads)
        db.commit()

    # 4. 공통 응답 규격으로 리턴
    return SuccessResponse(data=DocumentReadResponse(success=True))


@router.patch("/read-all", response_model=SuccessResponse[DocumentReadResponse])
def mark_all_documents_as_read(
    req: DocumentReadAllRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 탭에 따라 대상 문서 ID 목록 조회 쿼리 준비
    query = db.query(Document.id)

    if req.tab == "action":
        # action 탭: 내가 결재할 차례거나 내가 반려한 문서들만 타겟팅
        query = (
            query.join(Approval, Approval.document_id == Document.id)
            .filter(Approval.user_id == current_user.id)
            .filter(Approval.status.in_(["current", "rejected"]))
        )
    elif req.tab == "all":
        # all 탭: 전체 문서 대상 (별도 필터 없음)
        pass
    else:
        # 혹시라도 프론트엔드에서 이상한 탭 이름을 보내면 차단
        raise HTTPException(status_code=400, detail="INVALID_TAB")

    # DB에서 해당하는 문서 ID들만 싹 뽑아옵니다. (JOIN 시 문서 중복 방지)
    target_docs = query.distinct().all()
    target_doc_ids = [str(doc.id) for doc in target_docs]

    # 조건에 맞는 문서가 하나도 없다면 바로 성공 리턴
    if not target_doc_ids:
        return SuccessResponse(data=DocumentReadResponse(success=True))

    # 2. 타겟 문서들 중 이미 내가 읽은 문서 ID 조회
    already_read_docs = (
        db.query(DocumentRead.document_id)
        .filter(
            DocumentRead.user_id == current_user.id,
            DocumentRead.document_id.in_(target_doc_ids),
        )
        .all()
    )
    already_read_ids = {str(r.document_id) for r in already_read_docs}

    # 3. 진짜로 새로 읽음 처리해야 할 '안 읽은 문서'들만 필터링 (집합 연산)
    ids_to_insert = set(target_doc_ids) - already_read_ids

    # 4. DB에 한꺼번에 일괄 추가 (Bulk Insert)
    if ids_to_insert:
        new_reads = [
            DocumentRead(user_id=current_user.id, document_id=doc_id)
            for doc_id in ids_to_insert
        ]
        db.add_all(new_reads)
        db.commit()

    # 5. 공통 응답 규격으로 리턴
    return SuccessResponse(data=DocumentReadResponse(success=True))


@router.get(
    "/{documentId}/refs/{refDocumentId}",
    response_model=SuccessResponse[RefDocumentDetailResponse],
)
def get_ref_document_detail(
    documentId: str,
    refDocumentId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 원본 문서 확인 및 접근 권한 검증
    parent_doc = db.query(Document).filter(Document.id == documentId).first()
    if not parent_doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    if not _has_document_access(db, parent_doc, current_user):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 2. 참조 문서(타겟) 상세 정보 조회 (404 REF_DOC_NOT_FOUND)
    ref_doc = db.query(Document).filter(Document.id == refDocumentId).first()
    if not ref_doc:
        raise HTTPException(status_code=404, detail="REF_DOC_NOT_FOUND")

    # 부모 문서의 참조 관계를 검증
    parent_refs = set(parent_doc.ref_doc_ids or [])
    if refDocumentId not in parent_refs:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 3. 메타데이터(meta) 배열 조립
    # 프론트엔드 화면에 "라벨: 값" 형태로 예쁘게 출력될 수 있도록 구성합니다.
    # 기획에 따라 필요한 항목(예: 작업 예정일 등)을 얼마든지 추가/수정할 수 있습니다.
    meta_data = [
        RefDocMetaItem(
            label="문서 유형", value=ref_doc.type if ref_doc.type else "알 수 없음"
        ),
        RefDocMetaItem(
            label="작성자",
            value=ref_doc.author.name if ref_doc.author else "알 수 없음",
        ),
        RefDocMetaItem(
            label="등록일",
            value=_to_kst_str(ref_doc.created_at),
        ),
        RefDocMetaItem(label="결재 상태", value=ref_doc.status),
    ]

    # 만약 문서에 작업 예정일(work_date)이 있다면 메타데이터에 추가해 주는 센스!
    if ref_doc.work_date:
        meta_data.append(
            RefDocMetaItem(label="작업 예정일", value=str(ref_doc.work_date))
        )

    # 4. 공통 응답 규격으로 리턴
    content = _s3_get_text(ref_doc.html_key) if ref_doc.html_key else None

    return SuccessResponse(
        data=RefDocumentDetailResponse(
            id=str(ref_doc.id),
            title=ref_doc.title,
            meta=meta_data,
            content=content or "<p>본문 내용이 없습니다.</p>",
        )
    )


_PRESIGNED_EXPIRES = int(os.getenv("S3_PRESIGNED_EXPIRES", "3600"))
_MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100")) * 1024 * 1024  # bytes


@router.post("/{documentId}/attachments/presign", summary="첨부파일 업로드 presigned URL 발급")
def presign_upload(
    documentId: str,
    fileName: str = Query(..., description="업로드할 파일명"),
    fileSizeKb: int = Query(0, description="파일 크기 (KB)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """S3 presigned PUT URL을 발급한다. 프론트에서 이 URL로 직접 업로드."""
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")
    if doc.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if not _S3_BUCKET:
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")

    attachment_id = str(__import__("uuid").uuid4())
    workspace_id = doc.workspace_id or "default"
    s3_key = f"{workspace_id}/attachments/{documentId}/{attachment_id}_{fileName}"

    # presigned PUT URL 생성
    s3 = _get_s3_client()
    presigned_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": _S3_BUCKET, "Key": s3_key},
        ExpiresIn=_PRESIGNED_EXPIRES,
    )

    # DB에 첨부파일 메타 저장
    att = Attachment(
        id=attachment_id,
        document_id=documentId,
        original_name=fileName,
        file_path=s3_key,
        size_kb=fileSizeKb,
    )
    db.add(att)
    db.commit()

    return SuccessResponse(data={
        "attachmentId": attachment_id,
        "uploadUrl": presigned_url,
        "s3Key": s3_key,
    })


@router.get("/{documentId}/attachments/{fileId}/download", summary="첨부파일 다운로드")
def download_attachment(
    documentId: str,
    fileId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """S3 presigned GET URL을 발급하여 리다이렉트."""
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    if not _has_document_access(db, doc, current_user):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == fileId, Attachment.document_id == documentId)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    if not _S3_BUCKET:
        raise HTTPException(status_code=503, detail="S3_NOT_CONFIGURED")

    s3 = _get_s3_client()
    encoded_filename = quote(attachment.original_name)
    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": _S3_BUCKET,
            "Key": attachment.file_path,
            "ResponseContentDisposition": f"attachment; filename*=utf-8''{encoded_filename}",
        },
        ExpiresIn=_PRESIGNED_EXPIRES,
    )

    return SuccessResponse(data={"downloadUrl": presigned_url})


@router.delete("/{documentId}/attachments/{fileId}", summary="첨부파일 삭제")
def delete_attachment(
    documentId: str,
    fileId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")
    if doc.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == fileId, Attachment.document_id == documentId)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    # S3에서 삭제
    if _S3_BUCKET:
        try:
            _get_s3_client().delete_object(Bucket=_S3_BUCKET, Key=attachment.file_path)
        except ClientError:
            pass  # S3 삭제 실패는 무시 (DB에서만 제거)

    db.delete(attachment)
    db.commit()

    return SuccessResponse(data={"deleted": True})

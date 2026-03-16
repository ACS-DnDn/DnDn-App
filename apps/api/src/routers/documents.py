import os
from urllib.parse import quote
from fastapi.responses import FileResponse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta

from apps.api.src.database import get_db
from apps.api.src.models import Document, Approval, User, DocumentRead, Attachment
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
)

# 프론트엔드는 /documents 로 요청합니다.
router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("", response_model=SuccessResponse[DocumentArchiveResponse])
async def get_documents(
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
    pageSize: int = Query(10, ge=1, le=100, description="페이지당 항목 수"),
    archived: Optional[bool] = Query(
        None, description="참조 문서 검색용 (과거 명세 호환)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 기본 쿼리 시작
    query = db.query(Document)

    # 💡 [호환성 로직] 참조 문서 검색에서 archived=true로 찌른 경우
    if archived:
        query = query.filter(Document.status == "done")

    # 2. 탭(tab) 필터링
    if tab == "action":
        # 내가 결재할 차례(current)이거나 내가 반려했던(rejected) 문서만 가져옵니다.
        query = (
            query.join(Approval, Approval.document_id == Document.id)
            .filter(Approval.user_id == current_user.id)
            .filter(Approval.status.in_(["current", "rejected"]))
        )

    # 3. 검색어(keyword) 필터링
    if keyword:
        if searchField == "name":
            query = query.filter(Document.title.ilike(f"%{keyword}%"))
        elif searchField == "author":
            # 탭이 action이 아닐 때만 User 조인이 필요할 수 있으므로 안전하게 조인
            if tab != "action":
                query = query.join(User, Document.author_id == User.id)
            query = query.filter(User.name.ilike(f"%{keyword}%"))

    # 4. 유형(type) 필터링
    if type:
        query = query.filter(Document.type == type)

    # 5. 상태(status) 필터링 (archived가 아닐 때만)
    if status and not archived:
        query = query.filter(Document.status == status)

    # 6. 날짜(dateFrom, dateTo) 필터링
    if dateFrom:
        from_dt = datetime.strptime(dateFrom, "%Y-%m-%d")
        query = query.filter(Document.created_at >= from_dt)
    if dateTo:
        to_dt = datetime.strptime(dateTo, "%Y-%m-%d")
        # 해당 일자의 23:59:59 까지 포함하도록 설정
        to_dt = to_dt.replace(hour=23, minute=59, second=59)
        query = query.filter(Document.created_at <= to_dt)

    # 7. 전체 개수 구하기
    total_count = query.count()

    # 8. 정렬 및 페이징
    offset = (page - 1) * pageSize
    documents = (
        query.order_by(Document.created_at.desc()).offset(offset).limit(pageSize).all()
    )

    # 9. 응답 데이터 조립
    items = []
    for doc in documents:
        is_read_flag = (
            db.query(DocumentRead)
            .filter(
                DocumentRead.user_id == current_user.id,
                DocumentRead.document_id == doc.id,
            )
            .first()
            is not None
        )
        # action 값 계산 (명세서: 내가 결재해야 하면 'approve', 내가 반려했으면 'rejected', 없으면 null)
        action_val = None
        if tab == "action":
            my_approval = (
                db.query(Approval)
                .filter(
                    Approval.document_id == doc.id, Approval.user_id == current_user.id
                )
                .first()
            )

            if my_approval:
                if my_approval.status == "current":
                    action_val = "approve"
                elif my_approval.status == "rejected":
                    action_val = "rejected"

        items.append(
            {
                "id": str(doc.id),
                "docNum": f"2026-DnDn-{str(doc.id)[:4].upper()}",  # 예: 2026-DnDn-A1B2
                "name": doc.title,
                "author": doc.author.name if doc.author else "알수없음",
                "date": (
                    doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else ""
                ),
                "type": doc.type,
                "status": doc.status,
                "action": action_val,
                "isRead": is_read_flag,
            }
        )

    return SuccessResponse(
        data=DocumentArchiveResponse(
            total=total_count, page=page, pageSize=pageSize, items=items
        )
    )


@router.post(
    "", response_model=DocumentSubmitResponse, status_code=status.HTTP_201_CREATED
)
async def submit_document(
    req: DocumentSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 대상 문서(임시저장본) 찾기
    # (원래는 AI 워커가 끝날 때 Document 테이블에 가안을 만들어 뒀다고 가정합니다.
    # 지금은 테스트를 위해 문서가 없으면 방금 새로 만든 것처럼 생성해 주겠습니다!)
    doc = db.query(Document).filter(Document.id == req.documentId).first()

    if not doc:
        from datetime import date as date_type
        doc = Document(
            id=req.documentId,
            title=req.title or "작업계획서",
            content=req.content or "",
            author_id=current_user.id,
            work_date=date_type.today(),
        )
        db.add(doc)

    # 2. 임시 문서 만료 검사 (400 DRAFT_EXPIRED)
    # 문서 생성일이 24시간을 넘었는지 체크합니다.
    if doc.created_at:
        # 시간대를 맞추기 위해 타임존 제거(또는 통일) 후 비교
        time_diff = datetime.now() - doc.created_at.replace(tzinfo=None)
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
    doc.type = req.type
    if req.title:
        doc.title = req.title
    if req.content:
        doc.content = req.content
    doc.work_date = req.work_date or doc.work_date
    doc.terraform = req.terraform
    doc.ref_doc_ids = req.refDocIds
    doc.is_draft = req.isDraft

    # 임시저장(isDraft=true)이면 draft, 상신(isDraft=false)이면 progress 상태로 변경
    doc.status = "draft" if req.isDraft else "progress"

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
            document_id=doc.id, user_id=app.userId, seq=app.seq, status=approval_status
        )
        db.add(new_approval)

    # 7. DB 최종 반영
    db.commit()
    db.refresh(doc)

    # 8. 명세서에 맞는 응답 반환
    return DocumentSubmitResponse(
        id=str(doc.id), docNum=str(doc.id)[:8], status=doc.status  # UUID 앞 8자리
    )


@router.get("/{documentId}")
async def get_document_detail(documentId: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return doc


@router.post(
    "/{documentId}/approve", response_model=SuccessResponse[DocumentStatusResponse]
)
async def approve_document(
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
    my_approval.approval_date = datetime.now()

    # 4. 다음 결재자 찾기 (나의 seq + 1 인 사람)
    next_approval = (
        db.query(Approval)
        .filter(Approval.document_id == documentId, Approval.seq == my_approval.seq + 1)
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

        # 🚀 [TODO] 명세서 요구사항: "최종 결재자 승인 시 terraform apply 자동 반영"
        # 여기에 Terraform을 실행하는 워커(Worker)나 백그라운드 태스크를 호출하는 로직이 들어갈 자리입니다.
        # 예: background_tasks.add_task(run_terraform_apply, doc.terraform)

    # 6. DB 최종 반영
    db.commit()

    # 7. 공통 응답 규격으로 리턴
    return SuccessResponse(data=DocumentStatusResponse(newStatus=new_status))


@router.post(
    "/{documentId}/reject", response_model=SuccessResponse[DocumentStatusResponse]
)
async def reject_document(
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
    my_approval.approval_date = datetime.now()

    # 5. 문서 전체 상태를 '반려(rejected)'로 덮어쓰기
    # 💡 이 순간, 기안자(작성자)의 대시보드에 이 문서가 다시 'rejected' 상태로 뜨게 됩니다!
    doc.status = "rejected"

    # 6. DB 최종 반영
    db.commit()

    # 7. 공통 응답 규격으로 리턴 (상태는 무조건 rejected)
    return SuccessResponse(data=DocumentStatusResponse(newStatus="rejected"))


@router.patch("/read", response_model=SuccessResponse[DocumentReadResponse])
async def mark_documents_as_read(
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
async def mark_all_documents_as_read(
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

    # DB에서 해당하는 문서 ID들만 싹 뽑아옵니다.
    target_docs = query.all()
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
async def get_ref_document_detail(
    documentId: str,
    refDocumentId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 원본 문서 확인 (보안 및 데이터 정합성 차원)
    # 현재 보고 있는 문서가 진짜로 존재하는지 가볍게 체크해 줍니다.
    parent_doc = db.query(Document).filter(Document.id == documentId).first()
    if not parent_doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    # 2. 참조 문서(타겟) 상세 정보 조회 (404 REF_DOC_NOT_FOUND)
    ref_doc = db.query(Document).filter(Document.id == refDocumentId).first()
    if not ref_doc:
        raise HTTPException(status_code=404, detail="REF_DOC_NOT_FOUND")

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
            value=(
                ref_doc.created_at.strftime("%Y-%m-%d %H:%M")
                if ref_doc.created_at
                else ""
            ),
        ),
        RefDocMetaItem(label="결재 상태", value=ref_doc.status),
    ]

    # 만약 문서에 작업 예정일(work_date)이 있다면 메타데이터에 추가해 주는 센스!
    if ref_doc.work_date:
        meta_data.append(
            RefDocMetaItem(label="작업 예정일", value=str(ref_doc.work_date))
        )

    # 4. 공통 응답 규격으로 리턴
    return SuccessResponse(
        data=RefDocumentDetailResponse(
            id=str(ref_doc.id),
            title=ref_doc.title,
            meta=meta_data,
            content=(
                ref_doc.content if ref_doc.content else "<p>본문 내용이 없습니다.</p>"
            ),  # 프론트엔드가 HTML을 기대하므로 빈 값 처리
        )
    )


@router.get("/{documentId}/attachments/{fileId}/download", summary="첨부파일 다운로드")
async def download_attachment(
    documentId: str,
    fileId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 문서 존재 여부 및 접근 권한 확인 (404, 403)
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    # 💡 [보안] 명세서의 '403 FORBIDDEN' 처리:
    # 이 문서의 작성자이거나, 결재선에 포함된 사람만 다운로드할 수 있도록 막아줍니다.
    is_author = doc.author_id == current_user.id
    is_approver = (
        db.query(Approval)
        .filter(Approval.document_id == documentId, Approval.user_id == current_user.id)
        .first()
        is not None
    )

    if not (is_author or is_approver):
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # 2. 첨부파일 DB 정보 조회 (404 FILE_NOT_FOUND)
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == fileId, Attachment.document_id == documentId)
        .first()
    )

    if not attachment:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    # 3. 실제 서버에 파일이 존재하는지 검증
    # (나중에 AWS S3를 쓰신다면 boto3를 이용해 S3에서 스트리밍으로 가져오는 로직으로 바뀝니다!)
    file_path = attachment.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    # 4. 한국어 파일명 깨짐 방지 (URL 인코딩)
    encoded_filename = quote(attachment.original_name)

    # 5. FileResponse로 바이너리 반환! (이 API는 SuccessResponse로 감싸지 않습니다)
    return FileResponse(
        path=file_path,
        filename=attachment.original_name,
        # 브라우저가 직접 열지 않고 무조건 "다운로드" 하도록 강제하는 헤더
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"
        },
    )

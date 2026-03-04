from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.schemas.documents import DocumentCreateRequest
from apps.api.models import Document, Approval, User

# 프론트엔드는 /documents 로 요청합니다.
router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
async def get_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return docs


@router.post("")
async def save_document(doc_data: DocumentCreateRequest, db: Session = Depends(get_db)):
    first_user = db.query(User).first()
    if not first_user:
        raise HTTPException(status_code=400, detail="가입된 유저가 없습니다.")

    new_doc = Document(
        title=doc_data.title,
        content=doc_data.content,
        terraform=doc_data.terraform,
        ref_doc_ids=doc_data.refDocIds,
        work_date=doc_data.workDate,
        is_draft=doc_data.isDraft,
        status="draft" if doc_data.isDraft else "progress",
        author_id=first_user.id,
    )
    db.add(new_doc)
    db.flush()

    for approver in doc_data.approvers:
        new_approval = Approval(
            document_id=new_doc.id,
            user_id=first_user.id,
            seq=approver.seq,
            status="current" if approver.seq == 1 else "wait",
        )
        db.add(new_approval)

    db.commit()
    return {"message": "저장 완료", "documentId": new_doc.id}


@router.get("/{documentId}")
async def get_document_detail(documentId: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == documentId).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return doc

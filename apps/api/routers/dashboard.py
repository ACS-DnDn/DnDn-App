from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import User, Task, Document, Approval  # 가상의 테이블 모델

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
async def get_dashboard_data(
    user_id: str = "current_user", db: Session = Depends(get_db)
):
    # 1. 내가 결재해야 할 대기 문서 수 (Approval 테이블 조인)
    pending_count = (
        db.query(Approval)
        .filter(Approval.user_id == user_id, Approval.status == "current")
        .count()
    )

    # 2. 내가 작성한 진행 중인 문서 수
    active_docs_count = (
        db.query(Document)
        .filter(Document.author_id == user_id, Document.status == "progress")
        .count()
    )

    # 3. 오늘의 업무 목록 가져오기
    tasks = db.query(Task).filter(Task.user_id == user_id).all()

    return {
        "pendingApprovals": pending_count,
        "activeProjects": active_docs_count,
        "todayTasks": tasks,
    }


@router.post("/tasks")
async def add_task(
    content: str, user_id: str = "current_user", db: Session = Depends(get_db)
):
    first_user = db.query(User).first()
    if not first_user:
        raise HTTPException(
            status_code=400, detail="DB에 유저가 없습니다. 회원가입 먼저 해주세요!"
        )

    new_task = Task(user_id=first_user.id, content=content, status="todo")
    db.add(new_task)
    db.commit()
    db.refresh(new_task)  # DB에서 생성된 ID를 가져옴
    return new_task


@router.delete("/tasks/{taskId}")
async def delete_task(
    taskId: int, user_id: str = "current_user", db: Session = Depends(get_db)
):
    task = db.query(Task).filter(Task.id == taskId, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")

    db.delete(task)
    db.commit()
    return {"message": "업무가 삭제되었습니다."}

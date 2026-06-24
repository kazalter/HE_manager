from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..database import get_db
from ..services import login_throttle

router = APIRouter()


@router.get("/auth/status", response_model=schemas.AuthStatus)
def auth_status(db: Session = Depends(get_db)):
    return {"has_users": db.query(models.User).first() is not None}


@router.post("/auth/bootstrap", response_model=schemas.AuthToken)
def bootstrap_first_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).first():
        raise HTTPException(status_code=409, detail="Users already exist")

    user = models.User(
        username=payload.username.strip(),
        password_hash=auth.hash_password(payload.password),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth.create_access_token(db, user)
    return {"access_token": token, "user": user}


@router.post("/auth/login", response_model=schemas.AuthToken)
def login(payload: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    failure_key = login_throttle._login_failure_key(request, payload.username)
    user_key = f"user:{payload.username.strip().lower()}"
    if (
        len(login_throttle._pruned_login_failures(failure_key)) >= login_throttle.LOGIN_MAX_FAILURES
        or len(login_throttle._pruned_login_failures(user_key))
        >= login_throttle.LOGIN_MAX_FAILURES_PER_USER
    ):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")

    user = db.query(models.User).filter(models.User.username == payload.username.strip()).first()
    if not user or not user.is_active or not auth.verify_password(payload.password, user.password_hash):
        login_throttle._record_login_failure(failure_key)
        login_throttle._record_login_failure(user_key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    login_throttle.LOGIN_FAILURES.pop(failure_key, None)
    login_throttle.LOGIN_FAILURES.pop(user_key, None)
    token = auth.create_access_token(db, user)
    return {"access_token": token, "user": user}


@router.post("/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    raw_token = auth.extract_token(
        authorization=request.headers.get("authorization"),
        query_token=request.query_params.get("token"),
    )
    if raw_token:
        auth.revoke_access_token(db, raw_token)
    return {"message": "Logged out"}


@router.get("/auth/me", response_model=schemas.UserRead)
def get_me(user: models.User = Depends(auth.get_current_user)):
    return user


@router.get("/users", response_model=List[schemas.UserRead])
def list_users(_: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id.asc()).all()


@router.post("/users", response_model=schemas.UserRead)
def create_user(
    payload: schemas.UserCreate,
    _: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    username = payload.username.strip()
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = models.User(
        username=username,
        password_hash=auth.hash_password(payload.password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username is not None:
        username = payload.username.strip()
        existing = db.query(models.User).filter(models.User.username == username).first()
        if existing and existing.id != user_id:
            raise HTTPException(status_code=409, detail="用户名已存在")
        user.username = username

    if payload.password is not None:
        user.password_hash = auth.hash_password(payload.password)

    if payload.is_admin is not None:
        if current_user.id == user_id and payload.is_admin is False:
            raise HTTPException(status_code=400, detail="不能撤销自己的管理员权限")
        user.is_admin = payload.is_admin

    if payload.is_active is not None:
        if current_user.id == user_id and payload.is_active is False:
            raise HTTPException(status_code=400, detail="不能停用自己的账号")
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

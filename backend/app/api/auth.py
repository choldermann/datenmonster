from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str


@router.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falscher Benutzername oder Passwort",
        )
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username}


@router.post("/register", response_model=Token)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Benutzername bereits vergeben")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Passwort mindestens 6 Zeichen")
    user = User(username=data.username, hashed_password=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": u.id, "username": u.username} for u in db.query(User).filter(User.id != user.id).all()]


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(data: ChangePassword, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Neues Passwort mindestens 6 Zeichen")
    user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"ok": True}

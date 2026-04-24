from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from passlib.context import CryptContext  # Re-added for password hashing

from ..db.models import (
    User,
    UserCreate,
    UserUpdate,
)  # Ensure User, UserCreate, UserUpdate are imported
from ..db.database import get_session  # Import get_session from main.py

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

users_router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    responses={404: {"description": "User not found"}},
)


def get_password_hash(password: str) -> str:
    """Hashes a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


@users_router.post(
    "/", response_model=User, status_code=status.HTTP_201_CREATED, summary="Create a new User"
)
async def create_user(user_create: UserCreate, session: Session = Depends(get_session)):
    """
    Creates a new user in the database.
    Hashes the password before storing it.
    """
    # Check if a user with the given email already exists
    existing_user = session.exec(select(User).where(User.email == user_create.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email already exists."
        )

    # Hash the password
    hashed_password = get_password_hash(user_create.password)

    # Create the User instance, excluding the plain password and using the hashed one
    user = User(
        name=user_create.name,
        email=user_create.email,
        hashed_password=hashed_password,  # Storing hashed password
        is_active=user_create.is_active,
        is_superuser=user_create.is_superuser,
    )

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@users_router.get("/", response_model=List[User], summary="Get all Users")
async def get_all_users(session: Session = Depends(get_session)):
    """Retrieves a list of all users."""
    users = session.exec(select(User)).all()
    return users


@users_router.get("/{user_id}", response_model=User, summary="Get User by ID")
async def get_user_by_id(user_id: int, session: Session = Depends(get_session)):
    """Retrieves a single user by their ID."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@users_router.put("/{user_id}", response_model=User, summary="Update a User")
async def update_user(
    user_id: int, user_update: UserUpdate, session: Session = Depends(get_session)
):
    """
    Updates an existing user's information.
    Hashes the new password if provided.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update fields from user_update
    update_data = user_update.model_dump(exclude_unset=True)

    # Handle password update separately
    if "password" in update_data and update_data["password"]:
        user.hashed_password = get_password_hash(update_data["password"])  # Hashing new password
        del update_data["password"]  # Remove plain password from update_data

    for key, value in update_data.items():
        setattr(user, key, value)

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a User")
async def delete_user(user_id: int, session: Session = Depends(get_session)):
    """Deletes a user from the database."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    session.delete(user)
    session.commit()
    return {"ok": True}

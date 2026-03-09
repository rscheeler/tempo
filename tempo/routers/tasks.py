from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload  # Import selectinload for eager loading

from db.models import Task, TaskCreate, TaskUpdate, TimeEntry, Project  # Import TimeEntry and Project
from db.database import get_session

tasks_router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
    responses={404: {"description": "Task not found"}},
)


@tasks_router.post("/", response_model=Task, status_code=status.HTTP_201_CREATED, summary="Create a new Task")
async def create_task(task: TaskCreate, session: Session = Depends(get_session)):
    """Creates a new task in the database."""
    db_task = Task.model_validate(task)
    session.add(db_task)
    session.commit()
    session.refresh(db_task)
    return db_task


@tasks_router.get("/", response_model=List[Task], summary="Get all Tasks")
async def get_all_tasks(
    session: Session = Depends(get_session), project_id: Optional[int] = None  # Optional filter by project_id
):
    """Retrieves a list of all tasks, optionally filtered by project ID."""
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    tasks = session.exec(query).all()
    return tasks


@tasks_router.get("/{task_id}", response_model=Task, summary="Get Task by ID")
async def get_task_by_id(task_id: int, session: Session = Depends(get_session)):
    """Retrieves a single task by its ID."""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@tasks_router.get("/{task_id}/has_time_entries", summary="Check if Task has associated Time Entries")
async def has_task_time_entries(task_id: int, session: Session = Depends(get_session)) -> bool:
    """
    Checks if a task has any associated time entries.
    Returns True if time entries exist, False otherwise.
    """
    associated_time_entry = session.exec(select(TimeEntry).where(TimeEntry.task_id == task_id)).first()
    return associated_time_entry is not None


@tasks_router.put("/{task_id}", response_model=Task, summary="Update a Task")
async def update_task(task_id: int, task_update: TaskUpdate, session: Session = Depends(get_session)):
    """Updates an existing task's information."""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task_data = task_update.model_dump(exclude_unset=True)
    for key, value in task_data.items():
        setattr(task, key, value)

    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a Task")
async def delete_task(task_id: int, session: Session = Depends(get_session)):
    """Deletes a task from the database, preventing deletion if dependent time entries exist."""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Check for associated time entries
    associated_time_entry = session.exec(select(TimeEntry).where(TimeEntry.task_id == task_id)).first()
    if associated_time_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete task: Associated time entries exist."
        )

    session.delete(task)
    session.commit()
    return {"ok": True}

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from db.models import Customer, CustomerUpdate, Project, Invoice, TimeEntry  # Adjusted import if models.py is at root
from db.database import get_session

customers_router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
    responses={404: {"description": "Customer not found"}},
)


@customers_router.post(
    "/", response_model=Customer, status_code=status.HTTP_201_CREATED, summary="Create a new Customer"
)
async def create_customer(customer: Customer, session: Session = Depends(get_session)):
    """Creates a new customer in the database."""
    # Check if a customer with the same name already exists
    existing_customer = session.exec(select(Customer).where(Customer.name == customer.name)).first()
    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Customer with name '{customer.name}' already exists."
        )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


@customers_router.get("/", response_model=List[Customer], summary="Get all Customers")
async def get_all_customers(
    session: Session = Depends(get_session),
    show_archived: bool = Query(False, description="Include archived customers in the list"),
):
    """Retrieves a list of all customers, optionally including archived ones."""
    query = select(Customer)
    if not show_archived:
        query = query.where(Customer.is_archived == False)
    customers = session.exec(query).all()
    return customers


@customers_router.get("/{customer_id}", response_model=Customer, summary="Get Customer by ID")
async def get_customer_by_id(customer_id: int, session: Session = Depends(get_session)):
    """Retrieves a single customer by their ID."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@customers_router.put("/{customer_id}", response_model=Customer, summary="Update a Customer")
async def update_customer(customer_id: int, customer_update: CustomerUpdate, session: Session = Depends(get_session)):
    """Updates an existing customer's information."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # If name is being updated, check for uniqueness
    if customer_update.name is not None and customer_update.name != customer.name:
        existing_customer = session.exec(select(Customer).where(Customer.name == customer_update.name)).first()
        if existing_customer and existing_customer.id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer with name '{customer_update.name}' already exists.",
            )

    customer_data = customer_update.model_dump(exclude_unset=True)
    for key, value in customer_data.items():
        setattr(customer, key, value)

    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


@customers_router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a Customer")
async def delete_customer(customer_id: int, session: Session = Depends(get_session)):
    """Deletes a customer from the database, preventing deletion if dependent records exist."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Check for associated projects
    associated_project = session.exec(select(Project).where(Project.customer_id == customer_id)).first()
    if associated_project:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Changed to 409 Conflict as it's a conflict with existing data
            detail="Cannot delete customer: Projects are associated with this customer. Please delete or reassign projects first.",
        )

    # Check for associated invoices
    associated_invoice = session.exec(select(Invoice).where(Invoice.customer_id == customer_id)).first()
    if associated_invoice:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Changed to 409 Conflict
            detail="Cannot delete customer: Invoices are associated with this customer. Please delete or reassign invoices first.",
        )

    # If no dependencies, proceed with deletion
    session.delete(customer)
    session.commit()
    return {"ok": True}

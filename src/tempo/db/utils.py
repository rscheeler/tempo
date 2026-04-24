from sqlmodel import Session, select
from .models import Invoice
from datetime import datetime, date


def generate_record_number(session: Session, record_date: date = None) -> str:
    """
    Generates a unique record number for a given model.

    The record number is in the format 'YYYYMMDD-NNN', where NNN is
    a unique sequence number for the given date.  This function now
    checks for uniqueness across all relevant tables.
    """
    if record_date:
        date_str = record_date.strftime("%Y%m%d")
    else:
        date_str = datetime.now().strftime("%Y%m%d")
    base_record_number = f"{date_str}"

    # Check for the highest existing sequence number for today across all tables.
    highest_sequence = 0
    for model in [Invoice]:  # Add all your models here
        if hasattr(model, "record_number"):  # Check if the model has 'record_number' attribute
            query = select(model.record_number).where(
                model.record_number.like(f"{base_record_number}%")
            )
            results = session.exec(query).all()
            for result in results:
                if result:  # Make sure result and result[0] are not None
                    try:
                        sequence_part = int(result.split("-")[-1])
                        highest_sequence = max(highest_sequence, sequence_part)
                    except ValueError:
                        # Handle cases where the record number doesn't match the expected format
                        pass

    next_sequence = highest_sequence + 1
    sequence_str = str(next_sequence).zfill(3)
    return f"{base_record_number}-{sequence_str}"

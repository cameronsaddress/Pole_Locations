import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from sqlmodel import Session, select, text
from database import engine
from models import Tile

def reset_all_tiles():
    print("Connecting to database...")
    with Session(engine) as session:
        # Use raw SQL for speed on bulk update
        # ORM iteration is too slow for 10k+ items sometimes
        session.exec(text(f"UPDATE {Tile.__tablename__} SET status='Pending'"))
        session.commit()
        print("All tiles reset to 'Pending'. Ready for full re-scan.")

if __name__ == "__main__":
    reset_all_tiles()

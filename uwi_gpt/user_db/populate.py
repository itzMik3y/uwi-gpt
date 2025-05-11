import json
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, text

from .models import CatalogCourse, CatalogPrerequisite  # your models file
from .database import DATABASE_URL, Base  # import Base and DATABASE_URL from your setup

# ─────── CONFIG ───────
BASE_DIR   = Path(__file__).parent
INPUT_FILE = BASE_DIR / "course_prereqs.json"

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def populate_catalog():
    # load scraped JSON
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        courses = json.load(f)

    async with AsyncSessionLocal() as session:
        # 1) Truncate tables to reset
        await session.execute(text("TRUNCATE TABLE catalog_prerequisites CASCADE"))
        await session.execute(text("TRUNCATE TABLE catalog_courses RESTART IDENTITY CASCADE"))
        await session.commit()

        # 2) Re-populate courses and prerequisites
        success_count = 0
        for item in courses:
            ban_id = item.get('id')
            try:
                course = CatalogCourse(
                    ban_id=ban_id,
                    term_effective=item.get('termEffective'),
                    subject_code=item.get('subjectCode'),
                    course_number=item.get('courseNumber'),
                    course_code=f"{item.get('subjectCode')}{item.get('courseNumber')}",
                    course_title=item.get('courseTitle'),
                    credit_hour_low=item.get('creditHourLow'),
                    credit_hour_high=item.get('creditHourHigh'),
                    college=item.get('college'),       # new field
                    department=item.get('department')  # new field
                )
                session.add(course)
                await session.flush()  # assign course.id

                # Add prerequisites
                for p in item.get('prerequisites', []):
                    prereq = CatalogPrerequisite(
                        course_id=course.id,
                        and_or=p.get('and_or'),
                        subject=p.get('subject'),
                        number=p.get('number'),
                        level=p.get('level'),
                        grade=p.get('grade'),
                    )
                    session.add(prereq)

                success_count += 1
                # commit periodically
                if success_count % 100 == 0:
                    await session.commit()
                    print(f"Committed {success_count} courses so far")
            except Exception as e:
                print(f"Error processing course ban_id={ban_id}: {e}")
                await session.rollback()
                continue

        # Final commit for remaining records
        await session.commit()
        print(f"Successfully populated {success_count} courses")

async def main():
    try:
        await init_db()
        await populate_catalog()
        print("Database population complete")
    finally:
        await engine.dispose()
        print("Engine disposed")

if __name__ == '__main__':
    asyncio.run(main())
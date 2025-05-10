import json
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from db_models import CatalogCourse, CatalogPrerequisite  # your models file
from your_db import DATABASE_URL, Base  # import Base and DATABASE_URL from your setup

# Create engine & session factory
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Path to your scraped JSON
INPUT_FILE = "course_prereqs.json"

async def init_db():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def populate_catalog():
    # Load JSON data
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        courses = json.load(f)

    async with AsyncSessionLocal() as session:
        for item in courses:
            # Upsert CatalogCourse by ban_id
            stmt = select(CatalogCourse).where(CatalogCourse.ban_id == item.get('ban_id'))
            result = await session.execute(stmt)
            course = result.scalar_one_or_none()

            if not course:
                # Create new entry
                course = CatalogCourse(
                    ban_id=item.get('ban_id'),
                    term_effective=item.get('termEffective'),
                    subject_code=item.get('subjectCode'),
                    course_number=item.get('courseNumber'),
                    course_title=item.get('courseTitle'),
                    credit_hour_low=item.get('creditHourLow'),
                    credit_hour_high=item.get('creditHourHigh')
                )
                session.add(course)
                await session.flush()  # ensure course.id is populated
            else:
                # Update fields if needed
                course.term_effective  = item.get('termEffective')
                course.subject_code    = item.get('subjectCode')
                course.course_number   = item.get('courseNumber')
                course.course_title    = item.get('courseTitle')
                course.credit_hour_low = item.get('creditHourLow')
                course.credit_hour_high= item.get('creditHourHigh')

                # Clear existing prerequisites
                course.prerequisites.clear()

            # Populate prerequisites
            prereqs = item.get('prerequisites') or []
            for p in prereqs:
                prereq = CatalogPrerequisite(
                    and_or=p.get('and_or'),
                    subject=p.get('subject'),
                    number=p.get('number'),
                    level=p.get('level'),
                    grade=p.get('grade')
                )
                course.prerequisites.append(prereq)

        # Commit all changes
        await session.commit()

async def main():
    await init_db()
    await populate_catalog()
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())

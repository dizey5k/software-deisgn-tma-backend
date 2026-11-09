from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from app.models.models import GroupMembership, User

async def get_or_create_user(db: AsyncSession, telegram_id: int, username: str = None) -> User:
    """
    Find user by telegram_id. 
    If not exist — auto create (multi-user mode).
    """
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        user_data = {"telegram_id": telegram_id}
        if username is not None:
            user_data["username"] = username
            
        user = User(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif username and getattr(user, "username", None) != username:
        user.username = username
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    return user


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    normalized_username = username.lstrip("@").casefold()
    result = await db.execute(
        select(User).where(func.lower(User.username) == normalized_username)
    )
    return result.scalars().first()


async def join_group(
    db: AsyncSession,
    user: User,
    chat_id: int,
    chat_title: str | None = None,
) -> bool:
    membership_insert = insert(GroupMembership)
    statement = (
        membership_insert
        .values(user_id=user.id, chat_id=chat_id, chat_title=chat_title)
        .on_conflict_do_update(
            index_elements=[GroupMembership.user_id, GroupMembership.chat_id],
            set_={"chat_title": membership_insert.excluded.chat_title},
            where=membership_insert.excluded.chat_title.is_not(None),
        )
    )
    result = await db.execute(statement)
    await db.commit()
    return result.rowcount == 1
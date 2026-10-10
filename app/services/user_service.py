from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import User

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
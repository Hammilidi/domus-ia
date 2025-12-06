import asyncio
from web.database import Database, get_users_collection
from web.models import UserRole

async def check_admin():
    await Database.connect()
    users = get_users_collection()
    admin = await users.find_one({"role": "admin"})
    print("Admin trouvé:", admin)
    if admin:
        print("Email:", admin.get("email"))
        print("Password hash:", admin.get("password_hash", "N/A"))
    await Database.disconnect()

if __name__ == "__main__":
    asyncio.run(check_admin())

"""
Load reference clients from config to database.

從 config/switches.yaml 載入不斷電機台定義到資料庫。
"""
import asyncio
import yaml
from sqlalchemy import select
from app.db.base import get_async_session
from app.db.models import ReferenceClient


async def load_reference_clients():
    """載入不斷電機台。"""
    
    # 讀取 config
    with open('config/switches.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    reference_clients = config.get('reference_clients', [])
    
    if not reference_clients:
        print("⚠️ No reference clients found in config")
        return
    
    async for session in get_async_session():
        for client_config in reference_clients:
            mac = client_config['mac_address']
            
            # 檢查是否已存在
            stmt = select(ReferenceClient).where(ReferenceClient.mac_address == mac)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"⏭️  {mac} already exists, skipping")
                continue
            
            # 創建新記錄
            client = ReferenceClient(
                mac_address=mac,
                description=client_config.get('description'),
                location=client_config.get('location'),
                reason=client_config.get('reason'),
            )
            session.add(client)
            print(f"✅ Added {mac}")
        
        await session.commit()
    
    print(f"\n🎉 Loaded {len(reference_clients)} reference clients")


if __name__ == "__main__":
    asyncio.run(load_reference_clients())

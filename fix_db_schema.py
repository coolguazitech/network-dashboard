import asyncio
from sqlalchemy import text
from app.db.base import engine

async def fix_schema():
    async with engine.begin() as conn:
        print("Checking current schema...")
        
        # 檢查 uplink_expectations 表是否存在
        try:
            await conn.execute(text("DESCRIBE uplink_expectations"))
            print("Table uplink_expectations exists.")
        except Exception as e:
            print(f"Table check failed (expected if table missing): {e}")

        print("Dropping tables...")
        await conn.execute(text("DROP TABLE IF EXISTS uplink_expectations"))
        await conn.execute(text("DROP TABLE IF EXISTS version_expectations"))
        await conn.execute(text("DROP TABLE IF EXISTS arp_sources"))
        await conn.execute(text("DROP TABLE IF EXISTS port_channel_expectations"))
        
        print("Recreating tables (without FK constraint to avoid type mismatch)...")
        
        # UplinkExpectation
        await conn.execute(text("""
            CREATE TABLE uplink_expectations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                maintenance_id VARCHAR(100) NOT NULL,
                hostname VARCHAR(100) NOT NULL,
                local_interface VARCHAR(50) NOT NULL,
                expected_neighbor VARCHAR(100) NOT NULL,
                expected_interface VARCHAR(50),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_uplink_exp_maintenance (maintenance_id),
                INDEX idx_uplink_exp_hostname (hostname)
            )
        """))
        
        # VersionExpectation
        await conn.execute(text("""
            CREATE TABLE version_expectations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                maintenance_id VARCHAR(100) NOT NULL,
                hostname VARCHAR(100) NOT NULL,
                expected_versions TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_version_exp_maintenance (maintenance_id),
                INDEX idx_version_exp_hostname (hostname)
            )
        """))
        
        # ArpSource
        await conn.execute(text("""
            CREATE TABLE arp_sources (
                id INT AUTO_INCREMENT PRIMARY KEY,
                maintenance_id VARCHAR(100) NOT NULL,
                hostname VARCHAR(100) NOT NULL,
                ip_address VARCHAR(50) NOT NULL,
                priority INT DEFAULT 100,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_arp_sources_maintenance (maintenance_id)
            )
        """))
        
        # PortChannelExpectation
        await conn.execute(text("""
            CREATE TABLE port_channel_expectations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                maintenance_id VARCHAR(100) NOT NULL,
                hostname VARCHAR(100) NOT NULL,
                port_channel VARCHAR(50) NOT NULL,
                member_interfaces TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_port_channel_exp_maintenance (maintenance_id),
                INDEX idx_port_channel_exp_hostname (hostname)
            )
        """))
        
        print("Tables recreated successfully.")

if __name__ == "__main__":
    asyncio.run(fix_schema())

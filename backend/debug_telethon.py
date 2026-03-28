import asyncio
from telethon import TelegramClient

async def main():
    api_id = 21307616
    api_hash = 'f55b396c7204361afeb19c2f4b88fc33'
    phone = '+94769631098'
    
    print(f"DEBUG: Initializing client for {phone}...")
    client = TelegramClient(f'session_debug_{phone}', api_id, api_hash)
    
    try:
        print("DEBUG: Connecting to Telegram...")
        await client.connect()
        print("DEBUG: Connected!")
        
        print("DEBUG: Checking authorization status...")
        authorized = await client.is_user_authorized()
        print(f"DEBUG: Authorized: {authorized}")
        
        if not authorized:
            print(f"DEBUG: Requesting code for {phone}...")
            # We don't want to actually send multiple codes if they are already flooded,
            # but we want to see if this call hangs.
            # Using timeout to detect hang.
            try:
                await asyncio.wait_for(client.send_code_request(phone), timeout=15)
                print("DEBUG: Code request SUCCESSFUL!")
            except asyncio.TimeoutError:
                print("DEBUG: Code request HUNG (Timeout 15s)!")
            except Exception as e:
                print(f"DEBUG: Code request error: {str(e)}")
                
        await client.disconnect()
        print("DEBUG: Disconnected.")
        
    except Exception as e:
        print(f"DEBUG: Connection/General error: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())

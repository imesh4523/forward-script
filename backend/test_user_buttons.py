import asyncio
from telethon import TelegramClient, Button

async def main():
    api_id = 21307616
    api_hash = 'f55b396c7204361afeb19c2f4b88fc33'
    phone = '+94769631098'
    
    client = TelegramClient(f'session_debug_btns_{phone}', api_id, api_hash)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
             print("DEBUG: Not authorized. Run authentication first.")
             return

        # Try sending to a saved message (Self) or a target group
        target = 'me' # Saved Messages
        text = "Test message with buttons from User Account"
        kb = [[Button.url("Google", "https://google.com")]]
        
        print(f"DEBUG: Attempting to send message with buttons to {target}...")
        try:
            await client.send_message(target, text, buttons=kb)
            print("DEBUG: Send SUCCESSFUL (wait, did it really work?)")
        except Exception as e:
            print(f"DEBUG: Send FAILED: {str(e)}")
            
        await client.disconnect()
    except Exception as e:
        print(f"DEBUG: General error: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())

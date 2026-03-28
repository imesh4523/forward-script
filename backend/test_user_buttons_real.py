import asyncio
from telethon import TelegramClient, Button

async def main():
    api_id = 21307616
    api_hash = 'f55b396c7204361afeb19c2f4b88fc33'
    # Use the session file I found!
    session = 'session_source_94769631098'
    
    client = TelegramClient(session, api_id, api_hash)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
             print("DEBUG: Client NOT authorized. Check credentials or session.")
             return
             
        print("DEBUG: Connected & Authorized!")
        
        # Try sending to 'me' (Saved Messages)
        kb = [[Button.url("Test Button", "https://google.com")]]
        print("DEBUG: Attempting to send message with buttons to Saved Messages...")
        try:
            msg = await client.send_message('me', "Test message with inline button from a user account.", buttons=kb)
            print(f"DEBUG: Message sent! ID: {msg.id}")
            print(f"DEBUG: Reply Markup: {msg.reply_markup}")
        except Exception as e:
            print(f"DEBUG: FAILED: {str(e)}")
            
        await client.disconnect()
    except Exception as e:
        print(f"DEBUG: General error: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())

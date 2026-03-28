import asyncio
import random
import time
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatWriteForbiddenError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.sessions import StringSession
from database import SessionLocal, TelegramConfig, SenderConfig, TargetGroup, ForwardingConfig

# Two clients: source (watcher) and sender
source_client = None
sender_client = None
is_running = False
is_joining = False
bot_task = None
logs = []
message_queue = []

def add_log(message, log_type="info"):
    logs.append({"message": message, "type": log_type, "time": time.strftime("%H:%M:%S")})
    if len(logs) > 300:
        logs.pop(0)

# --- Source Client (Channel Watcher) ---
async def init_source_client(api_id, api_hash, phone):
    global source_client
    
    # Get stored session string from DB if available
    session_str = None
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        if conf: session_str = conf.session_string

    clean_phone = phone.replace('+', '').strip()
    session_target = StringSession(session_str) if session_str else f'session_source_{clean_phone}'
    
    print(f"DEBUG: init_source_client for {phone} (Session: {'String' if session_str else 'File'})")
    
    if source_client:
        try:
            if source_client.is_connected():
                # For StringSession, we check if api_id matches
                if source_client.api_id == int(api_id):
                    print("DEBUG: Reusing existing source_client")
                    return source_client
            print("DEBUG: Disconnecting old source_client")
            await asyncio.wait_for(source_client.disconnect(), timeout=5)
        except Exception as e:
            print(f"DEBUG: Error during old source_client cleanup: {e}")
    
    print("DEBUG: Creating new TelegramClient instance")
    source_client = TelegramClient(session_target, int(api_id), api_hash)
    try:
        print("DEBUG: Awaiting connect()...")
        await asyncio.wait_for(source_client.connect(), timeout=15)
        print("DEBUG: Connection successful")
        return source_client
    except asyncio.TimeoutError:
        print("DEBUG: connect() timed out after 15s")
        add_log("❌ Connection timed out. Please try again or restart backend.", "error")
        raise Exception("Connection timed out")
    except Exception as e:
        print(f"DEBUG: connect() error: {e}")
        add_log(f"❌ Connection error: {str(e)}", "error")
        raise e

async def send_source_code(api_id, api_hash, phone):
    await init_source_client(api_id, api_hash, phone)
    if not await source_client.is_user_authorized():
        await source_client.send_code_request(phone)
        return True
    return False

async def sign_in_source(phone, code, password=None):
    try:
        if password:
            await source_client.sign_in(password=password)
        else:
            await source_client.sign_in(phone, code)
        
        # Save StringSession to DB for stateless environments
        session_str = source_client.session.save()
        with SessionLocal() as db:
            conf = db.query(TelegramConfig).first()
            if conf:
                conf.session_string = session_str
                conf.is_authenticated = True
                db.commit()

        add_log("✅ Source account authenticated!", "success")
        return True
    except SessionPasswordNeededError:
        return "needs_password"
    except Exception as e:
        add_log(f"❌ Source login error: {str(e)}", "error")
        return False

async def logout_source(phone):
    global source_client
    try:
        if source_client and source_client.is_connected():
            await source_client.log_out()
            await source_client.disconnect()
        import os
        for ext in ['.session', '.session-journal']:
            f = f'session_source_{phone}{ext}'
            if os.path.exists(f): os.remove(f)
        source_client = None
        return True
    except: return False

async def check_source_live(api_id, api_hash, phone):
    try:
        if not source_client or not source_client.is_connected():
            await init_source_client(api_id, api_hash, phone)
        if await source_client.is_user_authorized():
            me = await source_client.get_me()
            return True if me else False
        return False
    except: return False

# --- Sender Client (Message Sender) ---
async def init_sender_client(api_id, api_hash, phone):
    global sender_client
    clean_phone = phone.replace('+', '').strip()
    session_name = f'session_sender_{clean_phone}'
    
    print(f"DEBUG: init_sender_client for {phone} (Session: {session_name})")

    if sender_client:
        try:
            if sender_client.is_connected():
                # Check if it's the SAME session file
                current_session = str(getattr(sender_client.session, 'filename', ''))
                if session_name in current_session:
                    print("DEBUG: Reusing existing sender_client connection")
                    return sender_client
            print("DEBUG: Disconnecting old sender_client")
            await asyncio.wait_for(sender_client.disconnect(), timeout=5)
        except Exception as e:
            print(f"DEBUG: Error during old sender_client cleanup: {e}")

    print("DEBUG: Creating new sender TelegramClient instance")
    sender_client = TelegramClient(session_name, int(api_id), api_hash)
    try:
        print("DEBUG: Awaiting connect()...")
        await asyncio.wait_for(sender_client.connect(), timeout=15)
        print("DEBUG: Connection successful")
        return sender_client
    except Exception as e:
        add_log(f"❌ Sender connection error: {str(e)}", "error")
        raise e

async def send_sender_code(api_id, api_hash, phone):
    await init_sender_client(api_id, api_hash, phone)
    if not await sender_client.is_user_authorized():
        await sender_client.send_code_request(phone)
        return True
    return False

async def sign_in_sender(phone, code, password=None):
    try:
        if password:
            await sender_client.sign_in(password=password)
        else:
            await sender_client.sign_in(phone, code)
        
        # Save StringSession to DB 
        session_str = sender_client.session.save()
        with SessionLocal() as db:
            conf = db.query(SenderConfig).first()
            if conf:
                conf.session_string = session_str
                conf.is_authenticated = True
                db.commit()

        add_log("✅ Sender account authenticated!", "success")
        return True
    except SessionPasswordNeededError:
        return "needs_password"
    except Exception as e:
        add_log(f"❌ Sender login error: {str(e)}", "error")
        return False

async def logout_sender(phone):
    global sender_client
    try:
        if sender_client and sender_client.is_connected():
            await sender_client.log_out()
            await sender_client.disconnect()
        import os
        for ext in ['.session', '.session-journal']:
            f = f'session_sender_{phone}{ext}'
            if os.path.exists(f): os.remove(f)
        sender_client = None
        return True
    except: return False

async def check_sender_live(api_id, api_hash, phone):
    try:
        if not sender_client or not sender_client.is_connected():
            await init_sender_client(api_id, api_hash, phone)
        if await sender_client.is_user_authorized():
            me = await sender_client.get_me()
            return True if me else False
        return False
    except: return False

# --- Auto Detect Groups ---
async def auto_detect_from_source(source_api_id, source_api_hash, source_phone, sender_api_id, sender_api_hash, sender_phone):
    """Source account එකේ join වී ඇති groups detect කර Sender එකේ status බලනවා"""
    if not source_client or not source_client.is_connected():
        await init_source_client(source_api_id, source_api_hash, source_phone)
    if not await source_client.is_user_authorized():
        add_log("❌ Source account not authenticated", "error")
        return {"success": False, "error": "Source account not authenticated", "groups": []}

    if not sender_client or not sender_client.is_connected():
        await init_sender_client(sender_api_id, sender_api_hash, sender_phone)
    if not await sender_client.is_user_authorized():
        add_log("❌ Sender account not authenticated", "error")
        return {"success": False, "error": "Sender account not authenticated", "groups": []}

    add_log("🔍 Detecting writable groups from Source...", "info")
    source_groups = []
    async for dialog in source_client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            entity = dialog.entity
            can_send = True
            
            # 1. Broadcast channel
            if getattr(entity, 'broadcast', False):
                is_creator = getattr(entity, 'creator', False)
                has_admin_rights = getattr(entity, 'admin_rights', None)
                can_post = has_admin_rights and getattr(has_admin_rights, 'post_messages', False)
                if not is_creator and not can_post:
                    can_send = False
            else:
                # 2. Group or Supergroup Default rights
                default_banned = getattr(entity, 'default_banned_rights', None)
                if default_banned and getattr(default_banned, 'send_messages', False):
                    if not getattr(entity, 'creator', False) and not getattr(entity, 'admin_rights', None):
                        can_send = False
                
                # 3. User specific banned rights
                banned = getattr(entity, 'banned_rights', None)
                if banned and getattr(banned, 'send_messages', False):
                    can_send = False

            if not can_send:
                continue

            username = getattr(entity, 'username', None)
            identifier = f"@{username}" if username else str(dialog.id)
            source_groups.append({
                "group_id_or_username": identifier,
                "group_title": dialog.title or identifier,
                "id": dialog.id
            })

    add_log("🔄 Checking Sender account join status...", "info")
    sender_joined_ids = set()
    async for dialog in sender_client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            sender_joined_ids.add(dialog.id)
            
    final_groups = []
    for g in source_groups:
        is_sender_joined = g["id"] in sender_joined_ids
        final_groups.append({
            "group_id_or_username": g["group_id_or_username"],
            "group_title": g["group_title"],
            "is_sender_joined": is_sender_joined
        })

    joined_count = sum(1 for g in final_groups if g['is_sender_joined'])
    add_log(f"✅ Found {len(final_groups)} total groups. Sender joined in {joined_count}.", "success")
    return {"success": True, "groups": final_groups}

# --- Auto Join Groups ---
async def auto_join_group(group_link):
    """එක group එකකට join වෙනවා"""
    if not sender_client or not await sender_client.is_user_authorized():
        return False, "Sender not authenticated"

    try:
        # Handle invite links (t.me/+xxx or t.me/joinchat/xxx)
        if '/+' in group_link or '/joinchat/' in group_link:
            invite_hash = group_link.split('/')[-1].replace('+', '')
            await sender_client(ImportChatInviteRequest(invite_hash))
        else:
            # Handle @username or t.me/username
            username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip()
            await sender_client(JoinChannelRequest(username))

        add_log(f"✅ Joined: {group_link}", "success")
        return True, "Joined successfully"
    except FloodWaitError as e:
        wait_time = e.seconds
        add_log(f"⏳ FloodWait! Must wait {wait_time}s before joining again", "warn")
        return False, f"FloodWait: wait {wait_time} seconds"
    except Exception as e:
        add_log(f"❌ Failed to join {group_link}: {str(e)}", "error")
        return False, str(e)

async def batch_join_groups(group_links, delay_minutes=60):
    """groups list එකකට rate limit එක්ක join වෙනවා"""
    global is_joining
    is_joining = True
    results = []

    for i, link in enumerate(group_links):
        if not is_joining:
            add_log("🛑 Join process stopped", "warn")
            break

        add_log(f"🚪 Joining group {i+1}/{len(group_links)}: {link}", "info")
        success, msg = await auto_join_group(link)
        results.append({"link": link, "success": success, "message": msg})

        if i < len(group_links) - 1 and is_joining:
            wait_seconds = delay_minutes * 60
            add_log(f"⏳ Waiting {delay_minutes} min before next join...", "info")
            await asyncio.sleep(wait_seconds)

    is_joining = False
    add_log(f"✅ Join process complete. {sum(1 for r in results if r['success'])}/{len(results)} succeeded", "success")
    return results

# --- Hourly Forward Logic ---
async def forward_message_to_group(channel_username, msg_id, group):
    """එක group එකකට post_link එකෙන් message කර forward කරනවා"""
    try:
        await sender_client.forward_messages(group, msg_id, from_peer=channel_username)
        
        # Increment total sent count in DB for dashboard tracking
        try:
            with SessionLocal() as db:
                conf = db.query(ForwardingConfig).first()
                if conf:
                    if conf.total_sent_count is None: conf.total_sent_count = 0
                    conf.total_sent_count += 1
                    db.commit()
        except: pass

        add_log(f"✓ Forwarded to {group}", "success")
        return True
    except ChatWriteForbiddenError:
        add_log(f"🚫 No write permission in {group}", "error")
        return False
    except Exception as e:
        add_log(f"✗ Failed to forward to {group}: {str(e)}", "error")
        return False

async def hourly_forward_loop(channel_username, msg_id, groups, hourly_count, delay_min, delay_max):
    """
    Hourly count system:
    - පැයකට messages hourly_count ක් forward කරනවා
    - සියලු groups 50+ ඉවර වෙනකන් ටිකෙන් ටික යවනවා
    """
    global is_running
    group_queue = groups.copy()

    while is_running and group_queue:
        messages_this_hour = min(hourly_count, len(group_queue))
        hour_seconds = 3600

        if messages_this_hour > 0:
            # Random times within the hour
            send_times = sorted(random.sample(range(0, hour_seconds), messages_this_hour))
            add_log(f"📅 Scheduled {messages_this_hour} groups this hour ({len(group_queue)} remaining total)", "info")

            start_time = time.time()
            for idx, send_at in enumerate(send_times):
                if not is_running or not group_queue:
                    break

                # Wait until the scheduled time
                elapsed = time.time() - start_time
                wait_for = send_at - elapsed
                if wait_for > 0:
                    add_log(f"⏳ Next forward in {int(wait_for)}s...", "info")
                    await asyncio.sleep(wait_for)

                if not is_running or not group_queue:
                    break

                group = group_queue.pop(0)

                await forward_message_to_group(channel_username, msg_id, group)
                
                add_log(f"✅ Forward {idx+1}/{messages_this_hour} done for this hour", "success")

            if not group_queue:
                break

            # Wait for remaining hour time
            elapsed = time.time() - start_time
            remaining = hour_seconds - elapsed
            if remaining > 0 and is_running:
                add_log(f"⏳ Hour not complete. Waiting {int(remaining)}s...", "info")
                await asyncio.sleep(remaining)
        else:
            await asyncio.sleep(10)

    if not group_queue:
        add_log("🎉 Finished! Sent to all groups.", "success")
        is_running = False

async def start_forwarding(source_api_id, source_api_hash, source_phone,
                           sender_api_id, sender_api_hash, sender_phone,
                           post_link, groups, delay_min, delay_max, hourly_count):
    global is_running
    is_running = True

    # Parse post_link
    post_link = post_link.strip().rstrip('/')
    parts = post_link.split('/')
    if len(parts) < 2 or not parts[-1].isdigit():
        add_log(f"❌ Invalid post link! Needs to end with message ID.", "error")
        is_running = False
        return

    msg_id = int(parts[-1])
    channel_username = parts[-2]
    # Handle private channels like t.me/c/1234/12
    if channel_username == 'c':
        channel_username = int("-100" + parts[-3])
    elif channel_username == 'joinchat':
        add_log(f"❌ Invite links not supported for forwarding. Use public channel links.", "error")
        is_running = False
        return

    # Connect source client (just to keep dual-account requirement as requested)
    await init_source_client(source_api_id, source_api_hash, source_phone)
    if not await source_client.is_user_authorized():
        add_log("❌ Source account not authenticated!", "error")
        is_running = False
        return

    # Connect sender client
    await init_sender_client(sender_api_id, sender_api_hash, sender_phone)
    if not await sender_client.is_user_authorized():
        add_log("❌ Sender account not authenticated!", "error")
        is_running = False
        return

    add_log(f"🤖 Bot started! Ready to forward.", "success")
    add_log(f"👁️ Post to forward: {channel_username} ID: {msg_id}", "info")
    add_log(f"📋 Forwarding to {len(groups)} groups", "info")
    add_log(f"⏱️ Hourly count: {hourly_count} groups/hour", "info")

    # Start hourly forward loop continuously pulling from specific post
    asyncio.create_task(hourly_forward_loop(channel_username, msg_id, groups, hourly_count, delay_min, delay_max))

async def stop_forwarding():
    global is_running, is_joining, source_client, sender_client
    is_running = False
    is_joining = False
    if source_client and source_client.is_connected():
        await source_client.disconnect()
    if sender_client and sender_client.is_connected():
        await sender_client.disconnect()
    add_log("🛑 Bot stopped.", "warn")

async def test_forward(sender_api_id, sender_api_hash, sender_phone, post_link, test_group):
    post_link = post_link.strip().rstrip('/')
    parts = post_link.split('/')
    if len(parts) < 2 or not parts[-1].isdigit():
        return {"success": False, "error": "Invalid post link! Needs to end with message ID."}

    msg_id = int(parts[-1])
    channel_username = parts[-2]
    if channel_username == 'c':
        channel_username = int("-100" + parts[-3])
    elif channel_username == 'joinchat':
        return {"success": False, "error": "Invite links not supported for forwarding. Use public channel links."}

    if not sender_client or not sender_client.is_connected():
        await init_sender_client(sender_api_id, sender_api_hash, sender_phone)

    if not await sender_client.is_user_authorized():
        return {"success": False, "error": "Sender account not authenticated! Please configure it in settings."}

    try:
        if isinstance(test_group, str) and test_group.replace('-','').isdigit():
            test_group = int(test_group)
            
        await sender_client.forward_messages(test_group, msg_id, from_peer=channel_username)
        return {"success": True, "message": f"Successfully forwarded to {test_group}!"}
    except Exception as e:
        return {"success": False, "error": f"Failed: {str(e)}"}

async def send_custom_message(sender_api_id, sender_api_hash, sender_phone, test_group, text, photo_path=None, buttons=None, bot_token=None):
    """
    Sends a custom message with optional photo and buttons.
    If bot_token is provided, uses a bot account to enable Inline Buttons.
    """
    try:
        # Normalize target group
        if isinstance(test_group, str) and test_group.replace('-','').isdigit():
            test_group = int(test_group)

        # Build buttons
        kb = []
        if buttons:
            row = []
            for btn in buttons[:3]: 
                label = btn.get("label")
                url = btn.get("url", "").strip()
                if label and url:
                    # Fix Telegram Usernames in URL
                    if url.startswith('@'):
                        url = 'https://t.me/' + url[1:]
                    
                    # Fix missing protocol in URL
                    if not url.startswith(('http://', 'https://', 'tg://')):
                        url = 'https://' + url
                    row.append(Button.url(label, url))
            if row:
                kb.append(row)

        target_client = None
        
        if bot_token:
            # Create a temporary bot client session
            # We use a unique session name for each bot token suffix to avoid collisions
            token_suffix = bot_token[-8:]
            target_client = TelegramClient(f'session_bot_{token_suffix}', sender_api_id, sender_api_hash)
            await target_client.start(bot_token=bot_token)
            print(f"DEBUG: Using BOT account for sending to {test_group}")
        else:
            # Use the existing sender user-client
            if not sender_client or not sender_client.is_connected():
                await init_sender_client(sender_api_id, sender_api_hash, sender_phone)
            if not await sender_client.is_user_authorized():
                return {"success": False, "error": "Sender account not authenticated!"}
            target_client = sender_client
            print(f"DEBUG: Using USER account for sending to {test_group}")

        try:
            if photo_path:
                await target_client.send_file(test_group, photo_path, caption=text, buttons=kb if kb else None)
            else:
                await target_client.send_message(test_group, text, buttons=kb if kb else None)
        finally:
            # If we created a bot client, disconnect it
            if bot_token and target_client:
                await target_client.disconnect()
            
        return {"success": True, "message": f"Successfully sent to {test_group}!"}
    except Exception as e:
        print(f"DEBUG: send_custom_message error: {e}")
        return {"success": False, "error": f"Failed: {str(e)}"}

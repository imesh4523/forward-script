import asyncio
import random
import time
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError, 
    PhoneNumberInvalidError, ChatWriteForbiddenError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from database import SessionLocal, TelegramConfig, SenderConfig, TargetGroup, ForwardingConfig

# Two clients: source (watcher) and sender
source_client = None
sender_client = None

is_running = False
is_joining = False
logs = []

def add_log(message, type="info"):
    global logs
    logs.append({"time": time.strftime("%H:%M:%S"), "message": message, "type": type})
    if len(logs) > 100:
        logs.pop(0)

# --- Client Initializers ---
async def init_source_client(api_id, api_hash, phone):
    global source_client
    with SessionLocal() as db:
        config = db.query(TelegramConfig).filter(TelegramConfig.phone_number == phone).first()
        session_str = config.session_string if config else None
        
    source_client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await source_client.connect()

async def init_sender_client(api_id, api_hash, phone):
    global sender_client
    with SessionLocal() as db:
        config = db.query(SenderConfig).filter(SenderConfig.phone_number == phone).first()
        session_str = config.session_string if config else None

    # Use a custom session name/string for sender
    sender_client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await sender_client.connect()

async def logout_source(phone):
    global source_client
    if source_client:
        await source_client.log_out()
        source_client = None

async def logout_sender(phone):
    global sender_client
    if sender_client:
        await sender_client.log_out()
        sender_client = None

# --- Auth Flow Helpers ---
async def send_code(client, phone):
    try:
        return await client.send_code_request(phone)
    except FloodWaitError as e:
        return {"error": f"Flood wait for {e.seconds} seconds"}

async def sign_in_client(client, phone, code, phone_code_hash, password=None):
    try:
        await client.sign_in(phone, code, password=password, phone_code_hash=phone_code_hash)
        return {"success": True, "session": client.session.save()}
    except SessionPasswordNeededError:
        return {"needs_password": True}
    except PhoneCodeInvalidError:
        return {"error": "Invalid OTP code"}
    except Exception as e:
        return {"error": str(e)}

async def check_source_live(api_id, api_hash, phone):
    try:
        if not source_client or not source_client.is_connected():
            await init_source_client(api_id, api_hash, phone)
        if await source_client.is_user_authorized():
            me = await source_client.get_me()
            return True if me else False
        return False
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
            if getattr(entity, 'broadcast', False):
                is_creator = getattr(entity, 'creator', False)
                has_admin_rights = getattr(entity, 'admin_rights', None)
                can_post = has_admin_rights and getattr(has_admin_rights, 'post_messages', False)
                if not is_creator and not can_post: can_send = False
            else:
                default_banned = getattr(entity, 'default_banned_rights', None)
                if default_banned and getattr(default_banned, 'send_messages', False):
                    if not getattr(entity, 'creator', False) and not getattr(entity, 'admin_rights', None): can_send = False
                banned = getattr(entity, 'banned_rights', None)
                if banned and getattr(banned, 'send_messages', False): can_send = False
            if not can_send: continue
            username = getattr(entity, 'username', None)
            identifier = f"@{username}" if username else str(dialog.id)
            source_groups.append({"group_id_or_username": identifier, "group_title": dialog.title or identifier, "id": dialog.id})

    add_log("🔄 Checking Sender account join status...", "info")
    sender_joined_ids = set()
    async for dialog in sender_client.iter_dialogs():
        if dialog.is_group or dialog.is_channel: sender_joined_ids.add(dialog.id)
    final_groups = [{"group_id_or_username": g["group_id_or_username"], "group_title": g["group_title"], "is_sender_joined": g["id"] in sender_joined_ids} for g in source_groups]
    add_log(f"✅ Found {len(final_groups)} total groups. Sender joined in {sum(1 for g in final_groups if g['is_sender_joined'])}.", "success")
    return {"success": True, "groups": final_groups}

# --- Auto Join Groups ---
async def auto_join_group(group_link):
    if not sender_client or not await sender_client.is_user_authorized(): return False, "Sender not authenticated"
    try:
        if '/+' in group_link or '/joinchat/' in group_link:
            invite_hash = group_link.split('/')[-1].replace('+', '')
            await sender_client(ImportChatInviteRequest(invite_hash))
        else:
            username = group_link.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip()
            await sender_client(JoinChannelRequest(username))
        add_log(f"✅ Joined: {group_link}", "success")
        return True, "Joined successfully"
    except FloodWaitError as e: return False, f"Flood wait {e.seconds}s"
    except Exception as e: return False, str(e)

async def start_auto_join_process(group_links, delay_minutes):
    global is_joining
    is_joining = True
    results = []
    for i, link in enumerate(group_links):
        if not is_joining: break
        success, msg = await auto_join_group(link)
        results.append({"link": link, "success": success, "message": msg})
        if i < len(group_links) - 1 and is_joining:
            add_log(f"⏳ Waiting {delay_minutes} min before next join...", "info")
            await asyncio.sleep(delay_minutes * 60)
    is_joining = False
    return results

# --- Hourly Forward Logic ---
async def forward_message_to_group(channel_username, msg_id, group):
    try:
        await sender_client.forward_messages(group, msg_id, from_peer=channel_username)
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
    global is_running
    while is_running:
        try:
            group_queue = groups.copy()
            if not group_queue:
                add_log("📋 No groups selected! Waiting 1 minute...", "warn")
                await asyncio.sleep(60); continue
            add_log(f"🔄 Starting new forwarding cycle for {len(group_queue)} groups.", "info")
            while is_running and group_queue:
                messages_this_hour = min(hourly_count, len(group_queue))
                if messages_this_hour > 0:
                    send_times = sorted(random.sample(range(0, 3600), messages_this_hour))
                    add_log(f"📅 Scheduled {messages_this_hour} groups this hour.", "info")
                    start_time = time.time()
                    for idx, send_at in enumerate(send_times):
                        if not is_running or not group_queue: break
                        wait_for = send_at - (time.time() - start_time)
                        if wait_for > 0:
                            add_log(f"⏳ Next forward in {int(wait_for)}s...", "info")
                            await asyncio.sleep(wait_for)
                        if not is_running or not group_queue: break
                        group = group_queue.pop(0)
                        await forward_message_to_group(channel_username, msg_id, group)
                    if not group_queue:
                        add_log("✨ Cycle complete. Restarting in 60s...", "success")
                        await asyncio.sleep(60); break
                    remaining = 3600 - (time.time() - start_time)
                    if remaining > 0 and is_running:
                        add_log(f"⏳ Waiting {int(remaining)}s for next hour batch...", "info")
                        await asyncio.sleep(remaining)
                else: await asyncio.sleep(10)
        except Exception as e:
            add_log(f"🔥 Error: {str(e)}. Retrying in 30s...", "error")
            await asyncio.sleep(30)
    add_log("🛑 Forwarding stopped.", "warn")

async def start_forwarding(source_api_id, source_api_hash, source_phone,
                           sender_api_id, sender_api_hash, sender_phone,
                           post_link, groups, delay_min, delay_max, hourly_count):
    global is_running
    is_running = True
    post_link = post_link.strip().rstrip('/')
    parts = post_link.split('/')
    if len(parts) < 2 or not parts[-1].isdigit():
        add_log(f"❌ Invalid post link!", "error")
        is_running = False; return
    msg_id = int(parts[-1])
    channel_username = parts[-2]
    if channel_username == 'c': channel_username = int("-100" + parts[-3])
    await init_source_client(source_api_id, source_api_hash, source_phone)
    await init_sender_client(sender_api_id, sender_api_hash, sender_phone)
    if not await source_client.is_user_authorized() or not await sender_client.is_user_authorized():
        add_log("❌ Authentication failed!", "error")
        is_running = False; return
    add_log(f"🤖 Bot started! Monitoring: {channel_username}", "success")
    asyncio.create_task(hourly_forward_loop(channel_username, msg_id, groups, hourly_count, delay_min, delay_max))

async def stop_forwarding():
    global is_running, is_joining; is_running = False; is_joining = False

async def test_forward(api_id, api_hash, phone, post_link, target_group):
    try:
        await init_sender_client(api_id, api_hash, phone)
        post_link = post_link.strip().rstrip('/')
        parts = post_link.split('/')
        msg_id, channel_username = int(parts[-1]), parts[-2]
        if channel_username == 'c': channel_username = int("-100" + parts[-3])
        await sender_client.forward_messages(target_group, msg_id, from_peer=channel_username)
        return {"success": True, "message": f"Test sent to {target_group}!"}
    except Exception as e: return {"success": False, "error": str(e)}

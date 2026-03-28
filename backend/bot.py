import asyncio
import random
import time
import os
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError, 
    PhoneNumberInvalidError, ChatWriteForbiddenError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from database import SessionLocal, TelegramConfig, SenderConfig, TargetGroup, ForwardingConfig

# Global clients
source_client = None
sender_client = None

# Track OTP hashes for auth
source_phone_code_hash = None
sender_phone_code_hash = None

is_running = False
is_joining = False
logs = []

def add_log(message, type="info"):
    global logs
    logs.append({"time": time.strftime("%H:%M:%S"), "message": message, "type": type})
    if len(logs) > 100: logs.pop(0)

# --- Client Management ---
async def get_source_client(api_id=None, api_hash=None, phone=None):
    global source_client
    if source_client and source_client.is_connected(): return source_client
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        if not conf: return None
        ss = conf.session_string
    source_client = TelegramClient(StringSession(ss), conf.api_id, conf.api_hash)
    await source_client.connect()
    return source_client

async def get_sender_client(api_id=None, api_hash=None, phone=None):
    global sender_client
    if sender_client and sender_client.is_connected(): return sender_client
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        if not conf: return None
        ss = conf.session_string
    sender_client = TelegramClient(StringSession(ss), conf.api_id, conf.api_hash)
    await sender_client.connect()
    return sender_client

# --- AUTH FUNCTIONS EXPECTED BY MAIN.PY ---

async def send_source_code(api_id, api_hash, phone):
    global source_client, source_phone_code_hash
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        ss = conf.session_string if conf else ""
    
    source_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await source_client.connect()
    if await source_client.is_user_authorized(): 
        print(f"INFO: Source account {phone} already authorized via DB session!")
        return None # No OTP needed
    
    # If not authorized, start a fresh login session
    source_client = TelegramClient(StringSession(""), api_id, api_hash)
    await source_client.connect()
    res = await source_client.send_code_request(phone)
    source_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_source(phone, code, password=None):
    global source_client, source_phone_code_hash
    try:
        if password:
            print(f"INFO: Attempting 2FA with password...")
            await source_client.sign_in(password=password)
        else:
            print(f"INFO: Attempting OTP sign-in...")
            await source_client.sign_in(phone, code, phone_code_hash=source_phone_code_hash)
        
        ss = source_client.session.save()
        with SessionLocal() as db:
            conf = db.query(TelegramConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        print(f"INFO: Session string saved to DB. Length: {len(ss)}")
        add_log(f"✅ Source account ({phone}) authenticated and saved!", "success")
        return True
    except SessionPasswordNeededError: return "needs_password"
    except Exception as e: raise e

async def send_sender_code(api_id, api_hash, phone):
    global sender_client, sender_phone_code_hash
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        ss = conf.session_string if conf else ""
        
    sender_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await sender_client.connect()
    if await sender_client.is_user_authorized(): 
        print(f"INFO: Sender account {phone} already authorized via DB session!")
        return None # No OTP needed
        
    # If not authorized, start a fresh login session
    sender_client = TelegramClient(StringSession(""), api_id, api_hash)
    await sender_client.connect()
    res = await sender_client.send_code_request(phone)
    sender_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_sender(phone, code, password=None):
    global sender_client, sender_phone_code_hash
    try:
        if password:
            print(f"INFO: Attempting 2FA with password...")
            await sender_client.sign_in(password=password)
        else:
            print(f"INFO: Attempting OTP sign-in...")
            await sender_client.sign_in(phone, code, phone_code_hash=sender_phone_code_hash)
            
        ss = sender_client.session.save()
        with SessionLocal() as db:
            conf = db.query(SenderConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        print(f"INFO: Session string saved to DB. Length: {len(ss)}")
        add_log(f"✅ Sender account ({phone}) authenticated and saved!", "success")
        return True
    except SessionPasswordNeededError: return "needs_password"
    except Exception as e: raise e

async def check_source_live(api_id, api_hash, phone):
    try:
        c = await get_source_client(); return await c.is_user_authorized() if c else False
    except: return False

async def check_sender_live(api_id, api_hash, phone):
    try:
        c = await get_sender_client(); return await c.is_user_authorized() if c else False
    except: return False

async def logout_source(phone):
    global source_client
    c = await get_source_client()
    if c: await c.log_out(); source_client = None; 
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first(); 
        if conf: conf.session_string = ""; db.commit()

async def logout_sender(phone):
    global sender_client
    c = await get_sender_client()
    if c: await c.log_out(); sender_client = None
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        if conf: conf.session_string = ""; db.commit()

# --- FORWARDING LOGIC ---

async def forward_message_to_group(channel_username, msg_id, group):
    try:
        client = await get_sender_client()
        await client.forward_messages(group, msg_id, from_peer=channel_username)
        with SessionLocal() as db:
            conf = db.query(ForwardingConfig).first()
            if conf:
                conf.total_sent_count = (conf.total_sent_count or 0) + 1
                db.commit()
        add_log(f"✓ Forwarded to {group}", "success")
        return True
    except ChatWriteForbiddenError:
        add_log(f"🚫 No write permission in {group}", "error")
        return False
    except Exception as e:
        add_log(f"✗ Error {group}: {str(e)}", "error")
        return False

async def hourly_forward_loop(channel_username, msg_id, groups, hourly_count, delay_min, delay_max):
    global is_running
    while is_running:
        try:
            current_groups = groups.copy()
            if not current_groups:
                add_log("📋 No groups! Waiting...", "warn"); await asyncio.sleep(60); continue
            add_log(f"🔄 Starting cycle: {len(current_groups)} groups.", "info")
            while is_running and current_groups:
                batch_count = min(hourly_count, len(current_groups))
                if batch_count > 0:
                    send_times = sorted(random.sample(range(0, 3600), batch_count))
                    start_time = time.time()
                    for idx, send_at in enumerate(send_times):
                        if not is_running or not current_groups: break
                        wait = send_at - (time.time() - start_time)
                        if wait > 0:
                            add_log(f"⏳ Next batch in {int(wait)}s...", "info")
                            await asyncio.sleep(wait)
                        if not is_running or not current_groups: break
                        group = current_groups.pop(0)
                        await forward_message_to_group(channel_username, msg_id, group)
                    if not current_groups:
                        add_log("✨ Cycle done! Restarting in 60s...", "success")
                        await asyncio.sleep(60); break
                    rem = 3600 - (time.time() - start_time)
                    if rem > 0 and is_running: await asyncio.sleep(rem)
                else: await asyncio.sleep(10)
        except Exception as e:
            add_log(f"🔥 Error: {str(e)}. Retrying...", "error"); await asyncio.sleep(30)

async def start_forwarding(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph, post_link, groups, d_min, d_max, h_count):
    global is_running
    is_running = True
    
    try:
        link = post_link.strip().rstrip('/')
        parts = link.split('/')
        if len(parts) < 2:
            raise Exception("Invalid post link format!")
        
        msg_id = int(parts[-1])
        # Handle Private Channel links: https://t.me/c/123456789/10 -> parts[-3] is 'c'
        if len(parts) >= 4 and parts[-3] == 'c':
            channel_username = int("-100" + parts[-2])
        else:
            channel_username = parts[-2]
            
        # Initialize clients to ensure we are auth'd before launching loop
        add_log("🔄 Initializing clients for forwarding...", "info")
        src = await get_source_client()
        snd = await get_sender_client()
        
        if not (await src.is_user_authorized() and await snd.is_user_authorized()):
            add_log("❌ One or both accounts not authenticated! Bot stopping.", "error")
            is_running = False
            return

        add_log(f"🤖 Bot started! Monitoring: {channel_username} (ID: {msg_id})", "success")
        asyncio.create_task(hourly_forward_loop(channel_username, msg_id, groups, h_count, d_min, d_max))
        
    except Exception as e:
        add_log(f"❌ Startup Error: {str(e)}", "error")
        is_running = False

async def stop_forwarding():
    global is_running; is_running = False

# --- DETECTION AND JOINING ---
async def auto_detect_from_source(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph):
    src = await get_source_client(); snd = await get_sender_client()
    if not (await src.is_user_authorized() and await snd.is_user_authorized()):
        return {"success": False, "error": "Auth failed"}
    add_log("🔍 Detecting groups...", "info")
    source_groups = []
    async for d in src.iter_dialogs():
        if d.is_group or d.is_channel:
            username = getattr(d.entity, 'username', None)
            ident = f"@{username}" if username else str(d.id)
            source_groups.append({"group_id_or_username": ident, "group_title": d.title, "id": d.id})
    sender_joined = set()
    async for d in snd.iter_dialogs(): sender_joined.add(d.id)
    final = [{"group_id_or_username": g["group_id_or_username"], "group_title": g["group_title"], "is_sender_joined": g["id"] in sender_joined} for g in source_groups]
    return {"success": True, "groups": final}

async def auto_join_group(link):
    snd = await get_sender_client()
    try:
        if '/+' in link or '/joinchat/' in link:
            await snd(ImportChatInviteRequest(link.split('/')[-1].replace('+', '')))
        else:
            await snd(JoinChannelRequest(link.strip()))
        add_log(f"✅ Joined: {link}", "success"); return True, ""
    except Exception as e: return False, str(e)

async def start_auto_join_process(links, delay):
    global is_joining; is_joining = True
    for link in links:
        if not is_joining: break
        await auto_join_group(link); await asyncio.sleep(delay * 60)
    is_joining = False

async def test_forward(api_id, api_hash, phone, post_link, target_group):
    client = await get_sender_client()
    link = post_link.strip().rstrip('/')
    parts = link.split('/')
    msg_id, u = int(parts[-1]), parts[-2]
    if u == 'c': u = int("-100" + parts[-3])
    await client.forward_messages(target_group, msg_id, from_peer=u)
    return {"success": True, "message": "Test success!"}

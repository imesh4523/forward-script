import asyncio
import random
import time
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, ChatWriteForbiddenError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from database import SessionLocal, TelegramConfig, SenderConfig, TargetGroup, ForwardingConfig

# Global Clients
source_client = None
sender_client = None

# Track OTP hashes for auth
source_phone_code_hash = None
sender_phone_code_hash = None

is_running = False
is_joining = False
logs = []

# Detailed stats per cycle
forward_stats = {"success": 0, "skipped": 0, "failed": 0, "total": 0}


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
def add_log(message, type="info"):
    global logs
    logs.append({"time": time.strftime("%H:%M:%S"), "message": message, "type": type})
    print(f"[{type.upper()}] {message}")
    if len(logs) > 100:
        logs.pop(0)

# ─────────────────────────────────────────────
# CLIENT HELPERS — loads session from DB
# ─────────────────────────────────────────────
def _load_source_conf():
    """Load source config from DB. Returns (api_id, api_hash, session_string) or None."""
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        if not conf:
            return None
        return (conf.api_id, conf.api_hash, conf.session_string or "")

def _load_sender_conf():
    """Load sender config from DB. Returns (api_id, api_hash, session_string) or None."""
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        if not conf:
            return None
        return (conf.api_id, conf.api_hash, conf.session_string or "")

async def get_source_client():
    global source_client
    if source_client is not None:
        if not source_client.is_connected():
            await source_client.connect()
        return source_client
    data = _load_source_conf()
    if not data:
        return None
    api_id, api_hash, ss = data
    if not ss:
        return None
    source_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await source_client.connect()
    return source_client

async def get_sender_client():
    global sender_client
    if sender_client is not None:
        if not sender_client.is_connected():
            await sender_client.connect()
        return sender_client
    data = _load_sender_conf()
    if not data:
        return None
    api_id, api_hash, ss = data
    if not ss:
        return None
    sender_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await sender_client.connect()
    return sender_client

# ─────────────────────────────────────────────
# AUTH — Source Account
# ─────────────────────────────────────────────
async def send_source_code(api_id, api_hash, phone):
    global source_client, source_phone_code_hash
    data = _load_source_conf()
    ss = data[2] if data else ""
    if ss:
        try:
            source_client = TelegramClient(StringSession(ss), api_id, api_hash)
            await source_client.connect()
            if await source_client.is_user_authorized():
                return None
        except Exception:
            try: await source_client.disconnect()
            except: pass
            source_client = None

    source_client = TelegramClient(StringSession(""), api_id, api_hash)
    await source_client.connect()
    res = await source_client.send_code_request(phone)
    source_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_source(phone, code, password=None):
    global source_client, source_phone_code_hash
    try:
        if password:
            await source_client.sign_in(password=password)
        else:
            await source_client.sign_in(phone, code, phone_code_hash=source_phone_code_hash)

        ss = source_client.session.save()
        with SessionLocal() as db:
            conf = db.query(TelegramConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        add_log(f"✅ Source account authenticated!", "success")
        return True
    except SessionPasswordNeededError:
        return "needs_password"
    except Exception as e:
        raise e

# ─────────────────────────────────────────────
# AUTH — Sender Account
# ─────────────────────────────────────────────
async def send_sender_code(api_id, api_hash, phone):
    global sender_client, sender_phone_code_hash
    data = _load_sender_conf()
    ss = data[2] if data else ""
    if ss:
        try:
            sender_client = TelegramClient(StringSession(ss), api_id, api_hash)
            await sender_client.connect()
            if await sender_client.is_user_authorized():
                return None
        except Exception:
            try: await sender_client.disconnect()
            except: pass
            sender_client = None

    sender_client = TelegramClient(StringSession(""), api_id, api_hash)
    await sender_client.connect()
    res = await sender_client.send_code_request(phone)
    sender_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_sender(phone, code, password=None):
    global sender_client, sender_phone_code_hash
    try:
        if password:
            await sender_client.sign_in(password=password)
        else:
            await sender_client.sign_in(phone, code, phone_code_hash=sender_phone_code_hash)

        ss = sender_client.session.save()
        with SessionLocal() as db:
            conf = db.query(SenderConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        add_log(f"✅ Sender account authenticated!", "success")
        return True
    except SessionPasswordNeededError:
        return "needs_password"
    except Exception as e:
        raise e

# ─────────────────────────────────────────────
# LIVE / LOGOUT HELPERS
# ─────────────────────────────────────────────
async def check_source_live(api_id, api_hash, phone):
    try:
        c = await get_source_client()
        return (await c.is_user_authorized()) if c else False
    except: return False

async def check_sender_live(api_id, api_hash, phone):
    try:
        c = await get_sender_client()
        return (await c.is_user_authorized()) if c else False
    except: return False

async def logout_source(phone):
    global source_client
    try:
        c = await get_source_client()
        if c: await c.log_out()
        source_client = None
    except: pass
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        if conf:
            conf.session_string = ""
            conf.is_authenticated = False
            db.commit()

async def logout_sender(phone):
    global sender_client
    try:
        c = await get_sender_client()
        if c: await c.log_out()
        sender_client = None
    except: pass
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        if conf:
            conf.session_string = ""
            conf.is_authenticated = False
            db.commit()

# ─────────────────────────────────────────────
# FORWARDING LOGIC
# ─────────────────────────────────────────────
async def get_sender_joined_ids():
    try:
        snd = await get_sender_client()
        joined = set()
        async for dialog in snd.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                joined.add(dialog.id)
                u = getattr(dialog.entity, 'username', None)
                if u: joined.add(f"@{u.lower()}")
        return joined
    except Exception as e:
        add_log(f"⚠️ Could not fetch joined groups: {e}", "warn")
        return set()

async def forward_message_to_group(channel_username, msg_id, group):
    global is_running, forward_stats
    while is_running:
        try:
            snd = await get_sender_client()
            if isinstance(group, str) and group.lstrip('-').isdigit():
                target = int(group)
            else:
                target = group
            
            await snd.forward_messages(target, msg_id, from_peer=channel_username)
            
            with SessionLocal() as db:
                conf = db.query(ForwardingConfig).first()
                if conf:
                    conf.total_sent_count = (conf.total_sent_count or 0) + 1
                    db.commit()
            
            forward_stats["success"] += 1
            add_log(f"✅ [{forward_stats['success']}/{forward_stats['total']}] Forwarded → {group}", "success")
            return True

        except FloodWaitError as e:
            add_log(f"⏳ Flood limit (chat-specific): Waiting {e.seconds}s then retrying {group}...", "warn")
            await asyncio.sleep(e.seconds)
            # Loop will retry
            
        except ChatWriteForbiddenError:
            forward_stats["failed"] += 1
            add_log(f"🚫 Permission Denied (Admin only): {group}", "error")
            return False
            
        except Exception as e:
            err = str(e).lower()
            if "banned from sending messages" in err:
                add_log(f"🚨 ACCOUNT BANNED: {err}", "error")
                is_running = False
                return False
            if "cannot find any entity" in err or "could not find the input entity" in err:
                forward_stats["skipped"] += 1
                add_log(f"⚠️ Skipped {group} — not joined yet", "warn")
            else:
                forward_stats["failed"] += 1
                add_log(f"❌ Failed → {group}: {err}", "error")
            return False
    return False

async def hourly_forward_loop(channel_username, msg_id, groups):
    global is_running, forward_stats
    cycle_num = 0
    cycle_rest_minutes = 5
    
    while is_running:
        try:
            cycle_num += 1
            add_log(f"🚀 Starting PARALLEL Burst Cycle #{cycle_num}...", "info")
            
            joined_ids = await get_sender_joined_ids()
            all_groups = groups.copy()
            joined_groups = []
            for g in all_groups:
                g_key = g.lower() if isinstance(g, str) and g.startswith('@') else g
                num_id = int(g) if isinstance(g, str) and g.lstrip('-').isdigit() else None
                if g_key in joined_ids or (num_id and num_id in joined_ids):
                    joined_groups.append(g)

            if not joined_groups:
                add_log("📋 No joined groups! Waiting 60s to retry...", "warn")
                await asyncio.sleep(60)
                continue

            add_log(f"📊 Cycle #{cycle_num}: Blasting to {len(joined_groups)} groups IN PARALLEL...", "success")
            forward_stats = {"success": 0, "skipped": 0, "failed": 0, "total": len(joined_groups)}
            
            # PARALLEL RUN with ASYNCIO.GATHER
            tasks = [forward_message_to_group(channel_username, msg_id, group) for group in joined_groups]
            await asyncio.gather(*tasks)

            if is_running:
                add_log(f"🎉 Parallel Cycle #{cycle_num} Complete! ✅ {forward_stats['success']} sent. Rests for {cycle_rest_minutes}m.", "success")
                for _ in range(cycle_rest_minutes * 60):
                    if not is_running: break
                    await asyncio.sleep(1)

        except Exception as e:
            add_log(f"🔥 Parallel Loop error: {e}. Retrying in 30s...", "error")
            await asyncio.sleep(30)

    add_log("🛑 Forwarding stopped.", "warn")

async def start_forwarding(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph,
                           post_link, groups, d_min, d_max, h_count):
    global is_running
    is_running = True
    try:
        link = post_link.strip().rstrip('/')
        parts = link.split('/')
        msg_id = int(parts[-1])
        if len(parts) >= 4 and parts[-3] == 'c':
            channel_username = int("-100" + parts[-2])
        else:
            channel_username = parts[-2]

        add_log("🔄 Verifying accounts...", "info")
        src = await get_source_client()
        snd = await get_sender_client()

        if not src or not await src.is_user_authorized():
            raise Exception("Source account not authorized!")
        if not snd or not await snd.is_user_authorized():
            raise Exception("Sender account not authorized!")

        add_log(f"🤖 Bot started! Channel: {channel_username}, Msg: {msg_id}", "success")
        with SessionLocal() as db:
            fwd_conf = db.query(ForwardingConfig).first()
            if fwd_conf:
                fwd_conf.is_bot_running = True
                db.commit()
        asyncio.create_task(hourly_forward_loop(channel_username, msg_id, groups))

    except Exception as e:
        add_log(f"❌ Bot startup failed: {e}", "error")
        is_running = False

async def stop_forwarding():
    global is_running
    is_running = False

# ─────────────────────────────────────────────
# GROUP AUTO-DETECT & AUTO-JOIN
# ─────────────────────────────────────────────
async def auto_detect_from_source(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph):
    try:
        src = await get_source_client()
        snd = await get_sender_client()
        if not src or not snd:
            return {"success": False, "error": "Clients not available"}
        if not await src.is_user_authorized() or not await snd.is_user_authorized():
            return {"success": False, "error": "Auth failed"}

        add_log("🔍 Detecting groups from Source...", "info")
        source_groups = []
        async for d in src.iter_dialogs(limit=500):
            if not d.entity: continue
            is_sendable = False
            if d.is_group: is_sendable = True
            elif d.is_channel:
                entity = d.entity
                if getattr(entity, 'megagroup', False): is_sendable = True
                elif getattr(entity, 'creator', False) or (getattr(entity, 'admin_rights', None)):
                    is_sendable = True
            
            if is_sendable:
                username = getattr(d.entity, 'username', None)
                ident = f"@{username}" if username else str(d.id)
                source_groups.append({"group_id_or_username": ident, "group_title": d.title, "id": d.id})

        sender_joined = set()
        async for d in snd.iter_dialogs(limit=500):
            sender_joined.add(d.id)

        final = [
            {
                "group_id_or_username": g["group_id_or_username"],
                "group_title": g["group_title"],
                "is_sender_joined": g["id"] in sender_joined
            }
            for g in source_groups
        ]
        add_log(f"✅ Found {len(final)} sendable groups.", "success")
        return {"success": True, "groups": final}
    except Exception as e:
        add_log(f"❌ Auto-Detect Crash: {e}", "error")
        return {"success": False, "error": str(e)}

async def auto_join_group(link):
    snd = await get_sender_client()
    try:
        if '/+' in link or '/joinchat/' in link:
            await snd(ImportChatInviteRequest(link.split('/')[-1].replace('+', '')))
        else:
            username = link.strip().lstrip('@')
            await snd(JoinChannelRequest(username))
        add_log(f"✅ Joined: {link}", "success")
        return True, ""
    except Exception as e:
        return False, str(e)

async def start_auto_join_process(links, delay):
    global is_joining
    is_joining = True
    for link in links:
        if not is_joining: break
        await auto_join_group(link)
        await asyncio.sleep(delay * 60)
    is_joining = False

async def test_forward(api_id, api_hash, phone, post_link, target_group):
    try:
        snd = await get_sender_client()
        link = post_link.strip().rstrip('/')
        parts = link.split('/')
        msg_id = int(parts[-1])
        if len(parts) >= 4 and parts[-3] == 'c':
            channel = int("-100" + parts[-2])
        else:
            channel = parts[-2]
        await snd.forward_messages(target_group, msg_id, from_peer=channel)
        return {"success": True, "message": "Test forward success!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

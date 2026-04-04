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

# Per-group next allowed time (epoch seconds) to handle FloodWait smartly
group_next_allowed = {}

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
# CLIENT HELPERS
# ─────────────────────────────────────────────
def _load_source_conf():
    with SessionLocal() as db:
        conf = db.query(TelegramConfig).first()
        if not conf: return None
        return (conf.api_id, conf.api_hash, conf.session_string or "")

def _load_sender_conf():
    with SessionLocal() as db:
        conf = db.query(SenderConfig).first()
        if not conf: return None
        return (conf.api_id, conf.api_hash, conf.session_string or "")

async def get_source_client():
    global source_client
    if source_client is not None:
        if not source_client.is_connected(): await source_client.connect()
        return source_client
    data = _load_source_conf()
    if not data: return None
    api_id, api_hash, ss = data
    if not ss: return None
    source_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await source_client.connect()
    return source_client

async def get_sender_client():
    global sender_client
    if sender_client is not None:
        if not sender_client.is_connected(): await sender_client.connect()
        return sender_client
    data = _load_sender_conf()
    if not data: return None
    api_id, api_hash, ss = data
    if not ss: return None
    sender_client = TelegramClient(StringSession(ss), api_id, api_hash)
    await sender_client.connect()
    return sender_client

# ─────────────────────────────────────────────
# AUTH 
# ─────────────────────────────────────────────
async def send_source_code(api_id, api_hash, phone):
    global source_client, source_phone_code_hash
    source_client = TelegramClient(StringSession(""), api_id, api_hash)
    await source_client.connect()
    res = await source_client.send_code_request(phone)
    source_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_source(phone, code, password=None):
    global source_client, source_phone_code_hash
    try:
        if password: await source_client.sign_in(password=password)
        else: await source_client.sign_in(phone, code, phone_code_hash=source_phone_code_hash)
        ss = source_client.session.save()
        with SessionLocal() as db:
            conf = db.query(TelegramConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        return True
    except SessionPasswordNeededError: return "needs_password"
    except Exception as e: raise e

async def send_sender_code(api_id, api_hash, phone):
    global sender_client, sender_phone_code_hash
    sender_client = TelegramClient(StringSession(""), api_id, api_hash)
    await sender_client.connect()
    res = await sender_client.send_code_request(phone)
    sender_phone_code_hash = res.phone_code_hash
    return True

async def sign_in_sender(phone, code, password=None):
    global sender_client, sender_phone_code_hash
    try:
        if password: await sender_client.sign_in(password=password)
        else: await sender_client.sign_in(phone, code, phone_code_hash=sender_phone_code_hash)
        ss = sender_client.session.save()
        with SessionLocal() as db:
            conf = db.query(SenderConfig).first()
            if conf:
                conf.session_string = ss
                conf.is_authenticated = True
                db.commit()
        return True
    except SessionPasswordNeededError: return "needs_password"
    except Exception as e: raise e

# ─────────────────────────────────────────────
# FORWARDING
# ─────────────────────────────────────────────
async def get_sender_joined_ids():
    try:
        snd = await get_sender_client()
        joined = set()
        async for dialog in snd.iter_dialogs(limit=None):
            joined.add(dialog.id)
            u = getattr(dialog.entity, 'username', None)
            if u: joined.add(f"@{u.lower()}")
        return joined
    except Exception as e:
        add_log(f"⚠️ Could not fetch joined groups: {e}", "warn")
        return set()

async def check_source_live(api_id, api_hash, phone):
    try:
        c = await get_source_client()
        if not c: return False
        if not c.is_connected(): await c.connect()
        return await c.is_user_authorized()
    except: return False

async def check_sender_live(api_id, api_hash, phone):
    try:
        c = await get_sender_client()
        if not c: return False
        if not c.is_connected(): await c.connect()
        return await c.is_user_authorized()
    except: return False

async def forward_message_to_group(channel_username, msg_id, group):
    global is_running, forward_stats, group_next_allowed
    
    # Check if group is currently in FloodWait timeout
    now = time.time()
    if group in group_next_allowed:
        wait_left = group_next_allowed[group] - now
        if wait_left > 0:
            add_log(f"⏳ Still waiting for {group}: {int(wait_left)}s left.", "warn")
            forward_stats["skipped"] += 1
            return False

    try:
        snd = await get_sender_client()
        target = int(group) if isinstance(group, str) and group.lstrip('-').isdigit() else group
        
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
        # Smart handling: Record the time this group can be retried
        group_next_allowed[group] = time.time() + e.seconds
        add_log(f"⏳ Flood limit (@{group}): {e.seconds}s penalty. Skipping this cycle...", "warn")
        forward_stats["skipped"] += 1
        return False
        
    except ChatWriteForbiddenError:
        forward_stats["failed"] += 1
        add_log(f"🚫 Admin-only group: @{group}", "error")
        return False
        
    except Exception as e:
        err = str(e).lower()
        if "a wait of" in err and "seconds" in err:
            try:
                wait_time = int(''.join(filter(str.isdigit, str(e))))
                group_next_allowed[group] = time.time() + wait_time + 10
                add_log(f"⏳ Slow mode (@{group}): {wait_time}s penalty. Skipping this cycle.", "warn")
                forward_stats["skipped"] += 1
                return False
            except: pass
        if "banned" in err:
            add_log(f"🚨 ACCOUNT BANNED: {err}", "error")
            is_running = False
            return False
        forward_stats["failed"] += 1
        add_log(f"❌ Failed (@{group}): {err}", "error")
        return False

import random

async def hourly_forward_loop(channel_username, msg_id, groups):
    global is_running, forward_stats
    cycle_num = 0
    cycle_rest_minutes = 3 # Optimized to 3 minutes as requested
    
    while is_running:
        try:
            cycle_num += 1
            with SessionLocal() as db:
                fwd = db.query(ForwardingConfig).first()
                cycle_rest_minutes = fwd.hourly_count if fwd else 3

            add_log(f"🚀 Starting Parallel Cycle #{cycle_num}...", "info")
            
            joined_ids = await get_sender_joined_ids()
            
            def norm_g(g):
                gs = str(g).strip().rstrip('/')
                if 't.me/' in gs: return '@' + gs.split('t.me/')[-1].split('?')[0].lower()
                if 'telegram.me/' in gs: return '@' + gs.split('telegram.me/')[-1].split('?')[0].lower()
                if gs.startswith('@'): return gs.lower()
                try: return int(gs)
                except: return gs

            joined_ids_norm = {norm_g(j) for j in joined_ids}
            joined_groups = [g for g in groups if norm_g(g) in joined_ids_norm]

            if not joined_groups:
                add_log("📋 No valid target groups detected! Check Target Groups list formatting.", "warn")
                await asyncio.sleep(60)
                continue

            add_log(f"📊 Sending to {len(joined_groups)} joined groups sequentially...", "success")
            forward_stats = {"success": 0, "skipped": 0, "failed": 0, "total": len(joined_groups)}
            
            for group in joined_groups:
                if not is_running: break
                await forward_message_to_group(channel_username, msg_id, group)
                # Random human-like delay between 1.5 and 4.0 seconds to avoid trigger global spam filter array
                human_delay = random.uniform(1.5, 4.0)
                await asyncio.sleep(human_delay)

            if is_running:
                add_log(f"🎉 Cycle #{cycle_num} Complete! ✅ {forward_stats['success']} sent. Next in {cycle_rest_minutes}m.", "success")
                for _ in range(cycle_rest_minutes * 60):
                    if not is_running: break
                    await asyncio.sleep(1)

        except Exception as e:
            add_log(f"🔥 Loop error: {e}. Retrying in 30s...", "error")
            await asyncio.sleep(30)

    add_log("🛑 Forwarding stopped.", "warn")

async def start_forwarding(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph, post_link, groups, d_min, d_max, h_count):
    global is_running
    is_running = True
    try:
        parts = post_link.strip().rstrip('/').split('/')
        msg_id = int(parts[-1])
        channel_username = int("-100" + parts[-2]) if len(parts) >= 4 and parts[-3] == 'c' else parts[-2]

        add_log("🔄 Verifying accounts...", "info")
        src, snd = await get_source_client(), await get_sender_client()
        if not src or not await src.is_user_authorized() or not snd or not await snd.is_user_authorized():
            raise Exception("Auth failed!")

        add_log(f"🤖 Bot launched! Fast Cycle every {3}m.", "success")
        with SessionLocal() as db:
            fwd = db.query(ForwardingConfig).first()
            if fwd: fwd.is_bot_running = True; db.commit()
        asyncio.create_task(hourly_forward_loop(channel_username, msg_id, groups))
    except Exception as e:
        add_log(f"❌ Startup failed: {e}", "error"); is_running = False

async def stop_forwarding():
    global is_running; is_running = False
    with SessionLocal() as db:
        fwd = db.query(ForwardingConfig).first()
        if fwd: fwd.is_bot_running = False; db.commit()

async def auto_detect_from_source(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph):
    try:
        src, snd = await get_source_client(), await get_sender_client()
        if not src or not snd: return {"success": False, "error": "No clients"}
        add_log("🔍 Detecting groups...", "info")
        final = []
        source_groups = []
        async for d in src.iter_dialogs(limit=500):
            if d.is_group or (d.is_channel and (getattr(d.entity, 'megagroup', False) or getattr(d.entity, 'creator', False) or getattr(d.entity, 'admin_rights', None))):
                u = getattr(d.entity, 'username', None)
                ident = f"@{u}" if u else str(d.id)
                source_groups.append({"user": ident, "title": d.title, "id": d.id})
        sender_joined = set()
        async for d in snd.iter_dialogs(limit=500): sender_joined.add(d.id)
        for g in source_groups:
            final.append({"group_id_or_username": g["user"], "group_title": g["title"], "is_sender_joined": g["id"] in sender_joined})
        add_log(f"✅ Found {len(final)} groups.", "success")
        return {"success": True, "groups": final}
    except Exception as e: return {"success": False, "error": str(e)}

async def batch_join_groups(links, delay_minutes):
    add_log(f"🚀 Starting batch join for {len(links)} groups (Delay: {delay_minutes}m)...", "info")
    for link in links:
        await auto_join_group(link)
        add_log(f"💤 Waiting {delay_minutes} minutes before next join...", "info")
        await asyncio.sleep(delay_minutes * 60)
    add_log("✅ Batch join complete.", "success")

async def auto_join_group(link):
    snd = await get_sender_client()
    try:
        if '/+' in link or '/joinchat/' in link: await snd(ImportChatInviteRequest(link.split('/')[-1].replace('+', '')))
        else: await snd(JoinChannelRequest(link.strip().lstrip('@')))
        add_log(f"✅ Joined: {link}", "success"); return True, ""
    except Exception as e: return False, str(e)

async def test_forward(api_id, api_hash, phone, post_link, target_group):
    try:
        snd = await get_sender_client()
        parts = post_link.strip().rstrip('/').split('/')
        msg_id, channel = int(parts[-1]), (int("-100" + parts[-2]) if len(parts) >= 4 and parts[-3] == 'c' else parts[-2])
        await snd.forward_messages(target_group, msg_id, from_peer=channel)
        return {"success": True, "message": "Success!"}
    except Exception as e: return {"success": False, "error": str(e)}

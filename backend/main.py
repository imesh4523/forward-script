import bot
import os
import json
import shutil
import asyncio
from typing import Optional, List
from contextlib import contextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import SessionLocal, TelegramConfig, SenderConfig, TargetGroup, ForwardingConfig

app = FastAPI(title="Telegram Auto Forwarder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Ensure all tables exist on startup - critical for cloud deployments."""
    from database import engine, Base, DATABASE_URL
    from sqlalchemy import text

    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"INFO: Using database at: {safe_url}")

    if not DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.execute(text("GRANT ALL ON SCHEMA public TO PUBLIC"))
                conn.commit()
                print("INFO: Schema permissions granted.")
        except Exception as e:
            print(f"INFO: Schema grant skipped: {e}")

    try:
        Base.metadata.create_all(bind=engine)
        print("INFO: All tables verified/created successfully.")
    except Exception as e:
        print(f"ERROR: Table creation failed: {e}")

    # Auto-resume bot if it was marked as running in DB
    try:
        with get_db() as db:
            fwd = db.query(ForwardingConfig).first()
            if fwd and fwd.is_bot_running:
                print("INFO: Auto-resuming bot as per DB state...")
                asyncio.create_task(start_bot())
    except Exception as e:
        print(f"INFO: Auto-resume skipped: {e}")

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models ---
class ConfigUpdate(BaseModel):
    api_id: str
    api_hash: str
    phone_number: str

class OTPRequest(BaseModel):
    code: str
    password: Optional[str] = None

class GroupRequest(BaseModel):
    group_id_or_username: str
    group_title: str = ""
    is_joined: bool = False
    is_selected: bool = True

class GroupsBulk(BaseModel):
    groups: List[GroupRequest]

class GroupSelectUpdate(BaseModel):
    is_selected: bool

class ForwardConfigRequest(BaseModel):
    post_link: Optional[str] = ""
    delay_min: Optional[int] = 30
    delay_max: Optional[int] = 120
    hourly_count: Optional[int] = 3
    join_delay_minutes: Optional[int] = 60
    total_sent_count: Optional[int] = 0
    is_bot_running: Optional[bool] = False
    cycle_rest_minutes: Optional[int] = 3

class JoinRequest(BaseModel):
    group_links: List[str]

# ============================================
# SOURCE ACCOUNT
# ============================================
@app.get("/api/config")
def get_config():
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        if not config:
            return {"api_id": "", "api_hash": "", "phone_number": "", "is_authenticated": False}
        return {"api_id": config.api_id, "api_hash": config.api_hash, "phone_number": config.phone_number, "is_authenticated": config.is_authenticated}

@app.post("/api/config")
def update_config(data: ConfigUpdate):
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        if not config:
            config = TelegramConfig(api_id=data.api_id, api_hash=data.api_hash, phone_number=data.phone_number)
            db.add(config)
        else:
            config.api_id = data.api_id
            config.api_hash = data.api_hash
            config.phone_number = data.phone_number
            config.is_authenticated = False
        db.commit()
    return {"status": "success"}

@app.post("/api/auth/send_code")
async def request_source_code():
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        if not config or not config.api_id or not config.phone_number:
            raise HTTPException(status_code=400, detail="Please save Source API config first")
        api_id, api_hash, phone = config.api_id, config.api_hash, config.phone_number
    try:
        needed_otp = await bot.send_source_code(api_id, api_hash, phone)
        if not needed_otp:
            # Already authorized, session file exists and valid
            with get_db() as db:
                config = db.query(TelegramConfig).first()
                if config:
                    config.is_authenticated = True
                    db.commit()
            return {"success": True, "already_authenticated": True}
        return {"success": True, "already_authenticated": False}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/verify")
async def verify_source_code(data: OTPRequest):
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        phone = config.phone_number
    res = await bot.sign_in_source(phone, data.code, data.password)
    if res == "needs_password":
        return {"status": "needs_password"}
    elif res:
        with get_db() as db:
            config = db.query(TelegramConfig).first()
            if config:
                config.is_authenticated = True
                db.commit()
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Invalid code or password")

@app.post("/api/auth/logout")
async def logout_source_api():
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        if not config: return {"success": True}
        phone = config.phone_number
        config.is_authenticated = False
        db.commit()
    await bot.logout_source(phone)
    return {"success": True}

@app.get("/api/auth/live")
async def check_source_live_api():
    with get_db() as db:
        config = db.query(TelegramConfig).first()
        if not config or not config.is_authenticated:
            return {"live": False}
        is_live = await bot.check_source_live(config.api_id, config.api_hash, config.phone_number)
        if not is_live:
            config.is_authenticated = False
            db.commit()
        return {"live": is_live}

# ============================================
# SENDER ACCOUNT
# ============================================
@app.get("/api/sender-config")
def get_sender_config():
    with get_db() as db:
        config = db.query(SenderConfig).first()
        if not config:
            return {"api_id": "", "api_hash": "", "phone_number": "", "is_authenticated": False}
        return {"api_id": config.api_id, "api_hash": config.api_hash, "phone_number": config.phone_number, "is_authenticated": config.is_authenticated}

@app.post("/api/sender-config")
def update_sender_config(data: ConfigUpdate):
    with get_db() as db:
        config = db.query(SenderConfig).first()
        if not config:
            config = SenderConfig(api_id=data.api_id, api_hash=data.api_hash, phone_number=data.phone_number)
            db.add(config)
        else:
            config.api_id = data.api_id
            config.api_hash = data.api_hash
            config.phone_number = data.phone_number
            config.is_authenticated = False
        db.commit()
    return {"status": "success"}

@app.post("/api/sender-auth/send_code")
async def request_sender_code():
    with get_db() as db:
        config = db.query(SenderConfig).first()
        if not config or not config.api_id or not config.phone_number:
            raise HTTPException(status_code=400, detail="Please save Sender API config first")
        api_id, api_hash, phone = config.api_id, config.api_hash, config.phone_number
    try:
        needed_otp = await bot.send_sender_code(api_id, api_hash, phone)
        if not needed_otp:
            # Already authorized, session file exists and valid
            with get_db() as db:
                config = db.query(SenderConfig).first()
                if config:
                    config.is_authenticated = True
                    db.commit()
            return {"success": True, "already_authenticated": True}
        return {"success": True, "already_authenticated": False}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/sender-auth/verify")
async def verify_sender_code(data: OTPRequest):
    with get_db() as db:
        config = db.query(SenderConfig).first()
        phone = config.phone_number
    res = await bot.sign_in_sender(phone, data.code, data.password)
    if res == "needs_password":
        return {"status": "needs_password"}
    elif res:
        with get_db() as db:
            config = db.query(SenderConfig).first()
            if config:
                config.is_authenticated = True
                db.commit()
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail="Invalid code or password")

@app.post("/api/sender-auth/logout")
async def logout_sender_api():
    with get_db() as db:
        config = db.query(SenderConfig).first()
        if not config: return {"success": True}
        phone = config.phone_number
        config.is_authenticated = False
        db.commit()
    await bot.logout_sender(phone)
    return {"success": True}

@app.get("/api/sender-auth/live")
async def check_sender_live_api():
    with get_db() as db:
        config = db.query(SenderConfig).first()
        if not config or not config.is_authenticated:
            return {"live": False}
        is_live = await bot.check_sender_live(config.api_id, config.api_hash, config.phone_number)
        if not is_live:
            config.is_authenticated = False
            db.commit()
        return {"live": is_live}

# ============================================
# GROUPS
# ============================================
@app.get("/api/groups")
def get_groups():
    with get_db() as db:
        groups = db.query(TargetGroup).all()
        return {"groups": [{"id": g.id, "group_id_or_username": g.group_id_or_username, "group_title": g.group_title, "is_joined": g.is_joined, "is_selected": g.is_selected, "is_sender_joined": g.is_sender_joined} for g in groups]}

@app.post("/api/groups")
def add_group(data: GroupRequest):
    with get_db() as db:
        group = TargetGroup(group_id_or_username=data.group_id_or_username, group_title=data.group_title or data.group_id_or_username, is_joined=data.is_joined, is_selected=data.is_selected, is_sender_joined=data.is_sender_joined)
        db.add(group)
        db.commit()
        new_id = group.id
    return {"status": "success", "id": new_id}

@app.post("/api/groups/bulk")
def add_groups_bulk(data: GroupsBulk):
    with get_db() as db:
        db.query(TargetGroup).delete()
        for g in data.groups:
            group = TargetGroup(group_id_or_username=g.group_id_or_username, group_title=g.group_title or g.group_id_or_username, is_joined=g.is_joined, is_selected=g.is_selected)
            db.add(group)
        db.commit()
    return {"status": "success", "count": len(data.groups)}

@app.patch("/api/groups/{group_id}/select")
def toggle_group_select(group_id: int, data: GroupSelectUpdate):
    with get_db() as db:
        group = db.query(TargetGroup).filter(TargetGroup.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        group.is_selected = data.is_selected
        db.commit()
    return {"status": "success"}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int):
    with get_db() as db:
        group = db.query(TargetGroup).filter(TargetGroup.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        db.delete(group)
        db.commit()
    return {"status": "success"}

@app.post("/api/groups/auto-detect")
async def auto_detect_groups():
    with get_db() as db:
        source = db.query(TelegramConfig).first()
        sender = db.query(SenderConfig).first()
        if not source or not source.is_authenticated:
            raise HTTPException(status_code=400, detail="Source account not authenticated")
        if not sender or not sender.is_authenticated:
            raise HTTPException(status_code=400, detail="Sender account not authenticated")
        src_id, src_hash, src_ph = source.api_id, source.api_hash, source.phone_number
        snd_id, snd_hash, snd_ph = sender.api_id, sender.api_hash, sender.phone_number

    detected = await bot.auto_detect_from_source(src_id, src_hash, src_ph, snd_id, snd_hash, snd_ph)
    if not detected.get("success"):
        raise HTTPException(status_code=400, detail=detected.get("error", "Detection failed"))
    
    groups = detected.get("groups", [])
    with get_db() as db:
        db.query(TargetGroup).delete()
        for g in groups:
            group = TargetGroup(
                group_id_or_username=g["group_id_or_username"], 
                group_title=g["group_title"], 
                is_joined=True, 
                is_selected=True,
                is_sender_joined=g.get("is_sender_joined", False)
            )
            db.add(group)
        db.commit()
    return {"status": "success", "count": len(groups)}

@app.post("/api/groups/auto-join")
async def auto_join_groups(data: JoinRequest):
    with get_db() as db:
        fwd = db.query(ForwardingConfig).first()
        delay = fwd.join_delay_minutes if fwd else 60
    asyncio.create_task(bot.batch_join_groups(data.group_links, delay))
    return {"status": "started", "count": len(data.group_links), "delay_minutes": delay}

# ============================================
# FORWARDING CONFIG
# ============================================
@app.get("/api/forwarding-config")
def get_forwarding_config():
    with get_db() as db:
        config = db.query(ForwardingConfig).first()
        if not config:
            return {"post_link": "", "delay_min": 30, "delay_max": 120, "hourly_count": 3, "join_delay_minutes": 60, "total_sent_count": 0}
        return {
            "post_link": config.post_link, 
            "delay_min": config.delay_min, 
            "delay_max": config.delay_max, 
            "hourly_count": config.hourly_count, 
            "join_delay_minutes": config.join_delay_minutes,
            "cycle_rest_minutes": config.cycle_rest_minutes or 3,
            "total_sent_count": config.total_sent_count or 0,
            "is_bot_running": config.is_bot_running or False
        }

@app.post("/api/forwarding-config")
def update_forwarding_config(data: ForwardConfigRequest):
    print(f"INFO: Updating forwarding config: {data.model_dump()}")
    try:
        with get_db() as db:
            config = db.query(ForwardingConfig).first()
            if not config:
                config = ForwardingConfig(
                    post_link=data.post_link, 
                    delay_min=data.delay_min, 
                    delay_max=data.delay_max, 
                    hourly_count=data.hourly_count, 
                    join_delay_minutes=data.join_delay_minutes,
                    total_sent_count=data.total_sent_count or 0,
                    cycle_rest_minutes=data.cycle_rest_minutes or 3
                )
                db.add(config)
            else:
                config.post_link = data.post_link
                config.delay_min = data.delay_min
                config.delay_max = data.delay_max
                config.hourly_count = data.hourly_count
                config.join_delay_minutes = data.join_delay_minutes
                config.cycle_rest_minutes = data.cycle_rest_minutes or 3
                # Only update count if explicitly sent as non-zero or it's currently null
                if data.total_sent_count is not None:
                    config.total_sent_count = data.total_sent_count
            db.commit()
            print("INFO: Forwarding config saved successfully.")
        return {"status": "success"}
    except Exception as e:
        print(f"ERROR: Failed to save config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# BOT CONTROL
# ============================================
_bot_task = None

class TestForwardRequest(BaseModel):
    post_link: str
    target_group: str

@app.post("/api/bot/test-forward")
async def api_test_forward(data: TestForwardRequest):
    with get_db() as db:
        sender_config = db.query(SenderConfig).first()
        if not sender_config or not sender_config.is_authenticated:
            raise HTTPException(status_code=400, detail="Please authenticate Sender account first")
        
        snd_api_id, snd_api_hash = sender_config.api_id, sender_config.api_hash
        snd_phone = sender_config.phone_number

    result = await bot.test_forward(snd_api_id, snd_api_hash, snd_phone, data.post_link, data.target_group)
    
    if result.get("success"):
        return {"status": "success", "message": result.get("message")}
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))

@app.get("/api/bot/status")
def get_bot_status():
    global _bot_task
    # Check in-memory task first
    if _bot_task and not _bot_task.done():
        return {"status": "running"}
    # Fallback: check DB (authoritative after restarts)
    try:
        with get_db() as db:
            fwd = db.query(ForwardingConfig).first()
            if fwd and fwd.is_bot_running:
                return {"status": "running"}
    except:
        pass
    return {"status": "stopped"}

@app.post("/api/bot/start")
async def start_bot():
    global _bot_task
    
    # Prevent double-start
    if _bot_task and not _bot_task.done():
        return {"status": "already_running", "message": "Bot is already running"}

    with get_db() as db:
        source_config = db.query(TelegramConfig).first()
        sender_config = db.query(SenderConfig).first()
        fwd = db.query(ForwardingConfig).first()
        groups = db.query(TargetGroup).filter(TargetGroup.is_selected == True).all()

        if not source_config or not source_config.is_authenticated:
            raise HTTPException(status_code=400, detail="Please authenticate Source account first")
        if not sender_config or not sender_config.is_authenticated:
            raise HTTPException(status_code=400, detail="Please authenticate Sender account first")
        if not fwd or not fwd.post_link:
            raise HTTPException(status_code=400, detail="Please set a Post Link first")
        if not groups:
            raise HTTPException(status_code=400, detail="Please add and select at least one target group")

        group_list = [g.group_id_or_username for g in groups]
        src_api_id, src_api_hash, src_phone = source_config.api_id, source_config.api_hash, source_config.phone_number
        snd_api_id, snd_api_hash, snd_phone = sender_config.api_id, sender_config.api_hash, sender_config.phone_number
        post_link = fwd.post_link
        d_min, d_max, h_count = fwd.delay_min, fwd.delay_max, fwd.hourly_count
        
        # Mark as running in DB
        fwd.is_bot_running = True
        db.commit()

    _bot_task = asyncio.create_task(
        bot.start_forwarding(src_api_id, src_api_hash, src_phone, snd_api_id, snd_api_hash, snd_phone, post_link, group_list, d_min, d_max, h_count)
    )
    return {"status": "started"}

@app.post("/api/bot/stop")
async def stop_bot():
    global _bot_task
    with get_db() as db:
        fwd = db.query(ForwardingConfig).first()
        if fwd:
            fwd.is_bot_running = False
            db.commit()
    await bot.stop_forwarding()
    if _bot_task:
        _bot_task.cancel()
        _bot_task = None
    return {"status": "stopped"}

@app.get("/api/logs")
def get_logs():
    return {"logs": bot.logs}

# ============================================
# AUTO-JOIN MANAGER
# ============================================
_auto_join_task = None
is_auto_joining = False

async def background_slow_join():
    global is_auto_joining
    is_auto_joining = True
    bot.add_log("🚀 Background Auto-Join Manager Started", "success")
    
    with get_db() as db:
        sender_config = db.query(SenderConfig).first()
        if not sender_config or not sender_config.is_authenticated:
            bot.add_log("❌ Sender not authenticated for Auto-Join", "error")
            is_auto_joining = False
            return
        snd_api_id = sender_config.api_id
        snd_api_hash = sender_config.api_hash
        snd_phone = sender_config.phone_number

    await bot.init_sender_client(snd_api_id, snd_api_hash, snd_phone)
    if not await bot.sender_client.is_user_authorized():
        bot.add_log("❌ Sender not authenticated for Auto-Join", "error")
        is_auto_joining = False
        return

    while is_auto_joining:
        with get_db() as db:
            fwd = db.query(ForwardingConfig).first()
            delay_minutes = fwd.join_delay_minutes if fwd else 60
            pending_group = db.query(TargetGroup).filter(TargetGroup.is_sender_joined == False).first()
            
        if not pending_group:
            bot.add_log("🎉 All groups joined! Auto-Join sleeping...", "info")
            for _ in range(60):
                if not is_auto_joining: break
                await asyncio.sleep(1)
            continue
            
        group_link = pending_group.group_id_or_username
        group_id = pending_group.id
        bot.add_log(f"🚪 Auto-Join: Attempting to join {group_link}", "info")
        
        success, msg = await bot.auto_join_group(group_link)
        wait_seconds = delay_minutes * 60
        
        if success or "already" in msg.lower():
            with get_db() as db:
                g = db.query(TargetGroup).filter(TargetGroup.id == group_id).first()
                if g: 
                    g.is_sender_joined = True
                    db.commit()
        else:
            if "FloodWait" in msg:
                try: wait_seconds = int(msg.split('wait ')[1].replace(' seconds',''))
                except: wait_seconds = delay_minutes * 60
            else:
                # Other errors (e.g invalid link), mark done so it doesn't loop forever
                with get_db() as db:
                    g = db.query(TargetGroup).filter(TargetGroup.id == group_id).first()
                    if g: 
                        g.is_sender_joined = True
                        db.commit()
                wait_seconds = 10 

        if is_auto_joining:
            if wait_seconds > 60:
                bot.add_log(f"⏳ Auto-Join: Sleeping {wait_seconds//60} min before next...", "info")
            else:
                bot.add_log(f"⏳ Auto-Join: Sleeping {wait_seconds}s...", "info")
            for _ in range(wait_seconds):
                if not is_auto_joining: break
                await asyncio.sleep(1)
                
    bot.add_log("🛑 Auto-Join Manager stopped", "warn")

@app.post("/api/bot/start-auto-join")
async def start_auto_join():
    global _auto_join_task
    if _auto_join_task and not _auto_join_task.done():
        return {"status": "already_running"}
    _auto_join_task = asyncio.create_task(background_slow_join())
    return {"status": "started"}

@app.post("/api/bot/stop-auto-join")
async def stop_auto_join():
    global is_auto_joining, _auto_join_task
    is_auto_joining = False
    if _auto_join_task:
        _auto_join_task.cancel()
        _auto_join_task = None
    bot.add_log("🛑 Auto-Join Manager manually stopped.", "warn")
    return {"status": "stopped"}

@app.get("/api/bot/auto-join-status")
def get_auto_join_status():
    with get_db() as db:
        total = db.query(TargetGroup).count()
        joined = db.query(TargetGroup).filter(TargetGroup.is_sender_joined == True).count()
        pending_objs = db.query(TargetGroup).filter(TargetGroup.is_sender_joined == False).all()
        
        pending_list = [{"group_title": g.group_title, "group_id_or_username": g.group_id_or_username} for g in pending_objs]
    return {
        "is_running": is_auto_joining,
        "total_groups": total,
        "joined_groups": joined,
        "pending_groups": len(pending_list),
        "pending_list": pending_list
    }

@app.post("/api/bot/send-custom")
async def send_custom_broadcast(
    test_group: str = Form(...),
    text: str = Form(...),
    buttons_json: str = Form("[]"),
    bot_token: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None)
):
    with get_db() as db:
        sender = db.query(SenderConfig).first()
        if not sender:
            raise HTTPException(status_code=400, detail="Sender account not configured")
        snd_id, snd_hash, snd_ph = sender.api_id, sender.api_hash, sender.phone_number

    photo_path = None
    if photo:
        os.makedirs("temp_uploads", exist_ok=True)
        photo_path = os.path.join("temp_uploads", photo.filename)
        with open(photo_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

    try:
        buttons = json.loads(buttons_json)
        res = await bot.send_custom_message(snd_id, snd_hash, snd_ph, test_group, text, photo_path, buttons, bot_token)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error"))
        return res
    finally:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)

# Serve Frontend Static Files
# Check multiple locations to support both local dev and Docker container paths
dist_path = "./dist" if os.path.exists("./dist") else "../frontend/dist"

if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=f"{dist_path}/assets"), name="assets")

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # If the path looks like an API call, it already failed 404
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    
    return {"detail": "Backend is running. Frontend 'dist' folder not found."}

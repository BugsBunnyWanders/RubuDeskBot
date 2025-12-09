from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import JSONResponse
import boto3, io, os, json, asyncio, time
from uuid import uuid4
from pathlib import Path
from PIL import Image
from datetime import datetime

# ---------- AWS / Rekognition ----------
REGION, COLL = "ap-south-1", "doorcam-family"
rek = boto3.client("rekognition", region_name=REGION)

# Optional FaceId->name cache (we’ll also use ExternalImageId directly when available)
NAMES_FN = "face_map.json"
names = json.load(open(NAMES_FN)) if Path(NAMES_FN).exists() else {}

# ---------- Telegram ----------
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = "8424341748:AAGOkB3DVHiePOksp7ZDIzUJ1PAutLHy53I"
TELEGRAM_CHAT_ID = "1092486083"

PENDING_DIR = Path("images/pending"); PENDING_DIR.mkdir(parents=True, exist_ok=True)
pending: dict[str, Path] = {}   # token -> image path

# ---- notify & matching knobs ----
SIM_THRESHOLD = 80           # accept and notify at/above this %
SEARCH_THRESHOLD = 70        # allow Rekognition to return weaker candidates
TOPK = 3                     # look at top-3 matches per face
COOLDOWN_SECONDS = 10        # per-person notify cooldown; set 0 to disable while testing
MARGIN = 0.18                # expand crop by 18% to include some context
DEBUG_NOTIFY = True          # verbose prints for decisions



app = FastAPI()
tg_app: Application | None = None
tg_bot: Bot | None = None

# ---------- helpers ----------
def _jpeg_under_5mb(jpg_bytes: bytes) -> bytes:
    if len(jpg_bytes) <= 5 * 1024 * 1024:
        return jpg_bytes
    im = Image.open(io.BytesIO(jpg_bytes))
    im.thumbnail((1280, 1280))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()

def crop_bbox(full_img_bytes: bytes, box: dict, margin: float = MARGIN) -> bytes:
    from math import floor, ceil
    with Image.open(io.BytesIO(full_img_bytes)) as im:
        w, h = im.size
        left   = max(0.0, box["Left"] - margin * box["Width"])
        top    = max(0.0, box["Top"]  - margin * box["Height"])
        right  = min(1.0, box["Left"] + (1 + margin) * box["Width"])
        bottom = min(1.0, box["Top"]  + (1 + margin) * box["Height"])
        x1, y1 = int(floor(left * w)),  int(floor(top * h))
        x2, y2 = int(ceil(right * w)),  int(ceil(bottom * h))
        face = im.crop((x1, y1, x2, y2))
        out = io.BytesIO(); face.save(out, "JPEG", quality=90)
        return out.getvalue()

async def notify_recognized(name: str, crop_jpeg: bytes, similarity: float):
    if not tg_bot or not TELEGRAM_CHAT_ID:
        if DEBUG_NOTIFY: print("[notify] tg_bot/chat not set; skipping")
        return
    try:
        payload = _jpeg_under_5mb(crop_jpeg)
        caption = f"{name} is at the door! ({similarity:.0f}%)"
        await tg_bot.send_photo(chat_id=int(TELEGRAM_CHAT_ID), photo=payload, caption=caption)
        if DEBUG_NOTIFY: print("[notify] sent:", caption)
    except Exception as e:
        print("[notify] FAILED:", e)

async def ask_to_label(crop_jpeg: bytes, similarity: float | None = None) -> str:
    """Send the unknown face to Telegram and return its token."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping ask_to_label()")
        return ""
    token = uuid4().hex[:8]
    path = PENDING_DIR / f"{token}.jpg"
    path.write_bytes(crop_jpeg)
    caption = f"Unknown face (ID: {token}){f' ~{similarity:.0f}%' if similarity else ''}\n" \
              f"Reply with:\n/label {token} <Name>\n/ignore {token}"
    await tg_bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=path.read_bytes(), caption=caption)
    pending[token] = path
    return token

def _names_save():
    Path(NAMES_FN).write_text(json.dumps(names, indent=2))

async def label_token(token: str, person: str) -> str:
    """Index the pending crop under ExternalImageId=person; update local map."""
    path = pending.pop(token, None)
    if not path or not path.exists():
        return f"ID {token} not found or already handled."

    payload = _jpeg_under_5mb(path.read_bytes())
    resp = rek.index_faces(
        CollectionId=COLL,
        Image={"Bytes": payload},
        ExternalImageId=person,
        MaxFaces=1
    )
    face_ids = [r["Face"]["FaceId"] for r in resp.get("FaceRecords", [])]
    for fid in face_ids:
        names[fid] = person
    _names_save()
    path.unlink(missing_ok=True)
    return f"Saved as *{person}* ({len(face_ids)} face{'s' if len(face_ids)!=1 else ''} indexed)."

# ---------- Telegram command handlers ----------
async def cmd_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    if TELEGRAM_CHAT_ID and str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        return  # ignore other chats
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /label <ID> <Name>")
        return
    token = context.args[0].strip()
    person = " ".join(context.args[1:]).strip()
    msg = await label_token(token, person)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_ignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    if TELEGRAM_CHAT_ID and str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ignore <ID>")
        return
    token = context.args[0].strip()
    path = pending.pop(token, None)
    if path and path.exists(): path.unlink(missing_ok=True)
    await update.message.reply_text(f"Ignored {token}.")

# ---------- FastAPI lifecycle: start/stop the Telegram bot ----------
@app.on_event("startup")
async def _startup():
    global tg_app, tg_bot
    if TELEGRAM_BOT_TOKEN:
        tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        tg_app.add_handler(CommandHandler("label", cmd_label))
        tg_app.add_handler(CommandHandler("ignore", cmd_ignore))

        await tg_app.initialize()
        await tg_app.start()
        # 👇 this actually begins receiving /label, /ignore, etc.
        await tg_app.updater.start_polling(drop_pending_updates=True)

        tg_bot = tg_app.bot
        print("Telegram bot started (polling).")
    else:
        print("Telegram not configured (set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")

@app.on_event("shutdown")
async def _shutdown():
    if tg_app:
        # 👇 stop polling first, then stop+shutdown the app
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

COOLDOWN_SECONDS = 60
last_notified: dict[str, float] = {}   # name -> unix time

async def notify_recognized(name: str, crop_jpeg: bytes, similarity: float):
    """Send '<name> is at the door!' with the cropped face."""
    if not tg_bot or not TELEGRAM_CHAT_ID:
        return
    try:
        # make sure it’s a proper JPEG and under TG limits
        payload = _jpeg_under_5mb(crop_jpeg)
        caption = f"{name} is at the door! ({similarity:.0f}%)"
        await tg_bot.send_photo(
            chat_id=int(TELEGRAM_CHAT_ID),  # int is safest
            photo=payload,
            caption=caption
        )
        print("Telegram sent:", caption)
    except Exception as e:
        print("Telegram send failed:", e)

# ---------- Shared recognition logic ----------
def run_recognition(img_bytes: bytes) -> dict:
    det = rek.detect_faces(Image={"Bytes": img_bytes})
    if not det.get("FaceDetails"):
        if DEBUG_NOTIFY: print("[recog] no faces")
        return {"faces": []}

    results = []

    for fd in det["FaceDetails"]:
        crop = crop_bbox(img_bytes, fd["BoundingBox"])

        srch = rek.search_faces_by_image(
            CollectionId=COLL,
            Image={"Bytes": crop},
            FaceMatchThreshold=SEARCH_THRESHOLD,
            MaxFaces=TOPK
        )

        # collapse top-K by name (ExternalImageId preferred)
        scores = {}
        for m in srch.get("FaceMatches", []):
            face = m["Face"]
            nm = face.get("ExternalImageId") or names.get(face["FaceId"], "unknown")
            scores[nm] = max(scores.get(nm, 0.0), m["Similarity"])

        if DEBUG_NOTIFY: print("[recog] candidates:", [(k, round(v,1)) for k,v in scores.items()])

        if scores:
            best_name, best_sim = max(scores.items(), key=lambda kv: kv[1])
            best_sim = round(best_sim, 2)
            results.append({"name": best_name, "similarity": best_sim})

            if best_name != "unknown" and best_sim >= SIM_THRESHOLD:
                now = time.time()
                last = last_notified.get(best_name, 0)
                cooldown_ok = (now - last) >= COOLDOWN_SECONDS
                if DEBUG_NOTIFY:
                    print(f"[recog] best={best_name}@{best_sim}%, cooldown_ok={cooldown_ok}")
                if cooldown_ok:
                    asyncio.create_task(notify_recognized(best_name, crop, best_sim))
                    last_notified[best_name] = now
            else:
                if DEBUG_NOTIFY:
                    print(f"[recog] best below threshold or unknown → no notify (best={best_name}, sim={best_sim})")
        else:
            results.append({"name": "unknown", "similarity": 0})
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                if DEBUG_NOTIFY: print("[recog] unknown → ask_to_label()")
                asyncio.create_task(ask_to_label(crop))

    return {"faces": results}


# ---------- Endpoints ----------
@app.post("/recognize")  # multipart/form-data
async def recognize(image: UploadFile = File(...)):
    img_bytes = await image.read()
    return JSONResponse(run_recognition(img_bytes))

@app.post("/recognize-raw")  # raw JPEG body (for ESP32 simple POST)
async def recognize_raw(req: Request):
    img_bytes = await req.body()
    return JSONResponse(run_recognition(img_bytes))

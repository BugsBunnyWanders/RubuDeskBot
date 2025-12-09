import boto3, glob, hashlib, json, os, io
from pathlib import Path
from PIL import Image

REGION   = "ap-south-1"
COLL_ID  = "doorcam-family"
BASE_DIR = "images/known"                 # folders per person
CACHE_FN = "index_cache.json"

rek = boto3.client("rekognition", region_name=REGION)
cache = json.loads(Path(CACHE_FN).read_text()) if Path(CACHE_FN).exists() else {}

def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def shrink(path, max_side=1280, q=85):
    im = Image.open(path)
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return buf.getvalue()

for person in os.listdir(BASE_DIR):
    for img_path in glob.glob(f"{BASE_DIR}/{person}/*.jpg"):
        h = sha1(img_path)
        if h in cache:
            print(f"◎  skip (already indexed) {img_path}")
            continue

        payload = shrink(img_path)
        resp = rek.index_faces(
            CollectionId=COLL_ID,
            Image={"Bytes": payload},
            ExternalImageId=person,
            MaxFaces=1
        )
        for rec in resp["FaceRecords"]:
            face_id = rec["Face"]["FaceId"]
            cache[h] = {"face_id": face_id, "person": person}
            print(f"✓  {person:<8} → {face_id}")

# save the updated cache
Path(CACHE_FN).write_text(json.dumps(cache, indent=2))
print(f"👍  indexed {len(cache)} total unique images")

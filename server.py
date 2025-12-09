# requirements:
#   fastapi uvicorn[standard] insightface==0.7 onnxruntime opencv-python

import os, glob, cv2, numpy as np
from fastapi import FastAPI, UploadFile, File
from insightface.app import FaceAnalysis      # state-of-the-art toolkit :contentReference[oaicite:1]{index=1}
from fastapi.responses import JSONResponse
import numpy as np

app = FastAPI()

# ---- prepare detector & embedder ----
fa = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
fa.prepare(ctx_id=0, det_size=(640, 640))

# ---- load gallery (a few clear photos per person in /known/<name>/) ----
gallery = {}
for person in os.listdir("images/known"):
    embs = []
    for p in glob.glob(f"images/known/{person}/*"):
        faces = fa.get(cv2.imread(p))
        if faces: embs.append(faces[0].embedding)
    gallery[person] = np.mean(embs, axis=0)

# ---- inference endpoint ----
@app.post("/recognize")
async def recognize(image: UploadFile = File(...)):
    img = np.frombuffer(await image.read(), np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)
    results = []
    for face in fa.get(img):
        emb  = face.embedding / np.linalg.norm(face.embedding)
        best_name, best_dist = "unknown", 1.0
        for name, ref in gallery.items():
            dist = np.linalg.norm(emb - ref / np.linalg.norm(ref))
            if dist < best_dist:
                best_name, best_dist = name, dist
        if best_dist < 0.6:
            results.append(
                {
                    "name": best_name,
                    "dist": float(round(best_dist, 3))  # 👈 cast to Python float
                }
            )
        else:
            results.append({"name": "unknown"})

    return JSONResponse({"faces": results})

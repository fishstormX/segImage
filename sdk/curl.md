# curl examples

```bash
BASE=https://jev.fishmaple.cn/segImage

curl -s $BASE/api/v1/health
curl -s $BASE/api/v1/models

# one subject → transparent PNG
curl -s -F file=@photo.jpg -F method=rembg -F rembg_model=u2netp $BASE/api/v1/segment \
  | python3 -c "import sys,json,base64;d=json.load(sys.stdin);open('sticker.png','wb').write(base64.b64decode(d['image_png_b64']));print(d['engine'],d['elapsed_ms'],'ms')"

# GrabCut seeded by a point and a rect (normalized 0..1)
curl -s -F file=@photo.jpg -F method=grabcut \
  -F 'points_json=[{"x":0.5,"y":0.5,"label":1}]' -F 'rect_json=[0.05,0.05,0.9,0.9]' $BASE/api/v1/segment

# AI auto-box (free OpenRouter vision models only; falls back to rembg)
curl -s -F file=@photo.jpg -F method=ai $BASE/api/v1/segment

# multiple subjects
curl -s -F file=@photo.jpg $BASE/api/v1/multi
```

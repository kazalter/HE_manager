"""Generate HE monogram icons from vector geometry; requires Pillow."""
from pathlib import Path
from PIL import Image, ImageDraw

output = Path(__file__).resolve().parent.parent / 'public' / 'app-icons'
output.mkdir(exist_ok=True)
# All foreground geometry stays inside the central maskable safe area.
h = [(126,156),(165,156),(165,235),(222,235),(222,156),(261,156),(261,356),(222,356),(222,275),(165,275),(165,356),(126,356)]
e = [(286,156),(386,156),(386,192),(325,192),(325,236),(379,236),(379,272),(325,272),(325,320),(386,320),(386,356),(286,356)]
image = Image.new('RGB', (1024,1024))
pixels = image.load()
for y in range(1024):
    for x in range(1024):
        t = (x + y) / 2046
        pixels[x,y] = tuple(round(a + (b-a)*t) for a,b in zip((44,35,92),(111,102,232)))
draw = ImageDraw.Draw(image)
for polygon in [h,e]:
    draw.polygon([(x*2,y*2) for x,y in polygon], fill='white')
for name,size in [('he-180.png',180),('he-192.png',192),('he-512.png',512),('he-maskable-512.png',512)]:
    image.resize((size,size), Image.Resampling.LANCZOS).save(output/name)
paths = ' '.join('<polygon points="' + ' '.join(f'{x},{y}' for x,y in polygon) + '" fill="white"/>' for polygon in [h,e])
(output/'he.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="he" x2="1" y2="1"><stop stop-color="#2c235c"/><stop offset="1" stop-color="#6f66e8"/></linearGradient></defs><rect width="512" height="512" rx="112" fill="url(#he)"/>' + paths + '</svg>')

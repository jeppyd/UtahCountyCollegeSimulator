"""Draw the app icon (three linked people) → packaging/icon.ico."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([16, 16, S - 16, S - 16], radius=110, fill=(252, 252, 251, 255))
pts = {"a": (176, 208), "b": (348, 176), "c": (276, 356)}
d.line([pts["a"], pts["b"], pts["c"], pts["a"]], fill=(82, 81, 78, 255), width=18, joint="curve")
for (x, y), r, col in ((pts["a"], 78, (42, 120, 214)), (pts["b"], 64, (235, 104, 52)), (pts["c"], 80, (27, 175, 122))):
    d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,), outline=(252, 252, 251, 255), width=10)
out = Path(__file__).with_name("icon.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)

from flask import Flask, request, jsonify
from rectpack import newPacker
import os  # AGGIUNGI QUESTA IMPORT

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bin Pack API attiva"

@app.route("/pack", methods=["POST"])
def pack():
    data = request.get_json()

    bin_width = data["bin_width"]
    bin_height = data["bin_height"]
    rects = data["rectangles"]  # ciascuno: {id, w, h}

    packer = newPacker(rotation=True)

    for r in rects:
        packer.add_rect(r["w"], r["h"], r["id"])

    packer.add_bin(bin_width, bin_height)
    packer.pack()

    packed_rects = []
    for abin in packer:
        for rect in abin:
            packed_rects.append({
                "id": rect.rid,
                "x": rect.x,
                "y": rect.y,
                "w": rect.width,
                "h": rect.height,
                "rotated": rect.rotation
            })

    return jsonify(packed_rects)

# ⬇️ AGGIUNGI QUESTO BLOCCO IN FONDO
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Porta per Render
    app.run(host="0.0.0.0", port=port)

from flask import Flask, request, jsonify
from rectpack import newPacker

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

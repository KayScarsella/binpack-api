from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker

app = Flask(__name__)
CORS(app)

@app.route("/", methods=["GET"])
def home():
    return "Bin Pack API attiva"

@app.route("/pack", methods=["POST"])
def pack():
    data = request.get_json()
    
    if not data or 'bin_width' not in data or 'bin_height' not in data or 'rectangles' not in data:
        return jsonify({"error": "Dati mancanti o non validi"}), 400

    try:
        bin_width = int(data["bin_width"])
        bin_height = int(data["bin_height"])
        rects = data["rectangles"]

        packer = newPacker(rotation=True)

        for r in rects:
            packer.add_rect(int(r["w"]), int(r["h"]), r["id"])

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
                    # Rimuovi la linea seguente se non supportata
                    # "rotated": rect.rotation  # ⚠️ Questo causa l'errore
                })

        return jsonify(packed_rects)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker

app = Flask(__name__)
CORS(app)

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

        # Aggiungi tutti i rettangoli al packer
        for r in rects:
            packer.add_rect(int(r["w"]), int(r["h"]), r["id"])

        bins_used = 0
        max_bins = 100  # Limite massimo di contenitori per evitare cicli infiniti
        prev_unplaced = len(packer.rect_list)  # Numero di rettangoli non posizionati

        while packer.rect_list and bins_used < max_bins:
            packer.add_bin(bin_width, bin_height)
            bins_used += 1
            packer.pack()

            # Controlla se il numero di rettangoli non posizionati è invariato
            current_unplaced = len(packer.rect_list)
            if current_unplaced == prev_unplaced:
                break  # Esci dal ciclo se non ci sono progressi
            prev_unplaced = current_unplaced

        if packer.rect_list:
            return jsonify({"error": "Impossibile posizionare tutti i rettangoli"}), 400

        packed_rects = []
        for abin in packer:
            for rect in abin:
                packed_rects.append({
                    "id": rect.rid,
                    "x": rect.x,
                    "y": rect.y,
                    "w": rect.width,
                    "h": rect.height,
                    "bin": bins_used,
                })

        return jsonify(packed_rects)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
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

        # Verifica dimensioni valide
        if bin_width <= 0 or bin_height <= 0:
            return jsonify({"error": "Dimensioni del contenitore non valide"}), 400

        packer = newPacker(rotation=True)

        # Aggiungi tutti i rettangoli al packer
        for r in rects:
            w = int(r["w"])
            h = int(r["h"])
            if w <= 0 or h <= 0:
                return jsonify({"error": f"Dimensione rettangolo non valida: {r}"}), 400
            packer.add_rect(w, h, rid=r["id"])

        bins_used = 0
        max_bins = 100  # Limite massimo di contenitori
        packed_rects = []

        while packer.rect_list() and bins_used < max_bins:
            packer.add_bin(bin_width, bin_height)
            bins_used += 1
            packer.pack()

            # Aggiungi i rettangoli posizionati al risultato
            for rect in packer[0]:
                packed_rects.append({
                    "id": rect.rid,
                    "x": rect.x,
                    "y": rect.y,
                    "w": rect.width,
                    "h": rect.height,
                    "bin": bins_used,
                })

            # Rimuovi i rettangoli già posizionati
            packer.rect_list()[:] = [r for r in packer.rect_list() if r not in [rect.rid for rect in packer[0]]]

        if packer.rect_list():
            return jsonify({
                "error": f"Impossibile posizionare tutti i rettangoli (mancanti: {len(packer.rect_list())})",
                "packed": packed_rects
            }), 200  # Potresti voler usare 207 Partial Content invece

        return jsonify(packed_rects)

    except ValueError as e:
        return jsonify({"error": f"Valore non valido: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Errore interno: {str(e)}"}), 500
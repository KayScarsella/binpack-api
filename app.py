from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker
from ortools.sat.python import cp_model

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height):
    model = cp_model.CpModel()
    
    # Variabili
    delta_y = {r['id']: model.NewIntVar(0, 50, f'delta_{r["id"]}') for r in rectangles}
    cuts_y = [model.NewBoolVar(f'cut_y_{y}') for y in range(0, container_height+1)]
    
    # Vincoli
    for r in rectangles:
        y_new = r['y'] + delta_y[r['id']]
        model.Add(y_new + r['h'] <= container_height)  # No overflow
        
        # Vincolo di continuità del taglio
        for other in rectangles:
            if other != r:
                model.Add(y_new + r['h'] <= other['y'] + delta_y[other['id']]).OnlyEnforceIf(cuts_y[y_new + r['h']])
    
    # Funzione obiettivo
    model.Minimize(sum(cuts_y) + sum(delta_y.values()))
    
    # Risoluzione
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    return {r['id']: solver.Value(delta_y[r['id']]) for r in rectangles}

@app.route("/pack", methods=["POST"])
def pack():
    data = request.get_json()
    
    if not data or 'bin_width' not in data or 'bin_height' not in data or 'rectangles' not in data:
        return jsonify({"error": "Dati mancanti o non validi"}), 400

    try:
        bin_width = int(data["bin_width"])
        bin_height = int(data["bin_height"])
        rects = data["rectangles"]

        if bin_width <= 0 or bin_height <= 0:
            return jsonify({"error": "Dimensioni del contenitore non valide"}), 400

        packer = newPacker(rotation=True)

        for r in rects:
            w = int(r["w"])
            h = int(r["h"])
            if w <= 0 or h <= 0:
                return jsonify({"error": f"Dimensione rettangolo non valida: {r}"}), 400
            packer.add_rect(w, h, rid=r["id"])

        max_bins = 100
        for _ in range(max_bins):
            packer.add_bin(bin_width, bin_height)

        packer.pack()

        all_bins_output = []
        unplaced_rects = [rect for rect in packer.rect_list() if rect[5] is None]

        for bin_index, abin in enumerate(packer):
            packed_rects = []
            for rect in abin:
                packed_rects.append({
                    "id": rect.rid,
                    "x": rect.x,
                    "y": rect.y,
                    "w": rect.width,
                    "h": rect.height,
                    "bin": bin_index,
                })

            # Calcola l'ottimizzazione dei tagli per questo bin
            cut_plan = optimize_cuts(packed_rects, bin_width, bin_height)

            all_bins_output.append({
                "bin_index": bin_index,
                "packed": packed_rects,
                "optimization": cut_plan
            })

        response = {
            "bins": all_bins_output,
            "unplaced": len(unplaced_rects)
        }

        return jsonify(response)

    except ValueError as e:
        return jsonify({"error": f"Valore non valido: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Errore interno: {str(e)}"}), 500

from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker
from ortools.sat.python import cp_model
from collections import defaultdict

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height, max_dy=50):
    model = cp_model.CpModel()
    
    # 1. Genera tutte le possibili linee di taglio candidate
    all_y_coords = sorted({0, container_height} | 
                         {r['y'] for r in rectangles} | 
                         {r['y'] + r['h'] for r in rectangles})
    
    # 2. Variabili decisionali
    delta_y = {r['id']: model.NewIntVar(0, max_dy, f'dy_{r["id"]}') for r in rectangles}
    cut_active = {y: model.NewBoolVar(f'cut_{y}') for y in all_y_coords if 0 < y < container_height}
    
    # 3. Vincoli per ogni rettangolo e ogni linea di taglio
    for r in rectangles:
        y_new = r['y'] + delta_y[r['id']]
        
        # Vincolo contenitore
        model.Add(y_new + r['h'] <= container_height)
        
        # Vincoli per ogni possibile linea di taglio
        for y_cut in cut_active.keys():
            # Variabile: il rettangolo è sopra questa linea?
            is_above = model.NewBoolVar(f'above_{r["id"]}_{y_cut}')
            model.Add(y_new >= y_cut).OnlyEnforceIf(is_above)
            model.Add(y_new < y_cut).OnlyEnforceIf(is_above.Not())
            
            # Se il taglio è attivo, il rettangolo non può attraversarlo
            model.Add(y_new + r['h'] <= y_cut).OnlyEnforceIf(
                [cut_active[y_cut], is_above.Not()])
            model.Add(y_new >= y_cut).OnlyEnforceIf(
                [cut_active[y_cut], is_above])

    # 4. Funzione obiettivo (minimizza spostamenti e massimizza tagli attivi)
    model.Maximize(
        sum(cut_active.values()) * 1000 -  # Prioritizza più tagli possibili
        sum(delta_y.values())              # Poi minimizza gli spostamenti
    )
    
    # 5. Risoluzione
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    # 6. Risultati
    if status == cp_model.OPTIMAL:
        return {
            'adjustments': {r['id']: solver.Value(delta_y[r['id']]) for r in rectangles},
            'cuts': [y for y, var in cut_active.items() if solver.Value(var)],
            'total_displacement': sum(solver.Value(dy) for dy in delta_y.values())
        }
    return None

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

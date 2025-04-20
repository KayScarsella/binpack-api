from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker
from ortools.sat.python import cp_model

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height, max_dy=50):
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()

    # Crea variabili delta_y
    delta_y = {r['id']: model.NewIntVar(0, max_dy, f'dy_{r["id"]}') for r in rectangles}
    y_final = {r['id']: r['y'] + delta_y[r['id']] for r in rectangles}

    # Costruisci grafo di dipendenza (spostamento a cascata)
    dependencies = {r['id']: set() for r in rectangles}
    for i in range(len(rectangles)):
        for j in range(len(rectangles)):
            if i == j:
                continue
            r1 = rectangles[i]
            r2 = rectangles[j]
            if r1['x'] + r1['w'] > r2['x'] and r2['x'] + r2['w'] > r1['x']:
                if r2['y'] >= r1['y'] + r1['h']:
                    dependencies[r1['id']].add(r2['id'])

    # Vincoli a cascata
    def apply_dependencies(rid, visited=None):
        if visited is None:
            visited = set()
        visited.add(rid)
        for dep in dependencies[rid]:
            if dep not in visited:
                model.Add(delta_y[dep] >= delta_y[rid])
                apply_dependencies(dep, visited)

    for rid in dependencies:
        apply_dependencies(rid)

    # Vincolo: ogni rettangolo deve stare nel contenitore
    for r in rectangles:
        model.Add(y_final[r['id']] + r['h'] <= container_height)

    # Linee di taglio candidate
    all_y_coords = sorted({0, container_height} |
                          {r['y'] for r in rectangles} |
                          {r['y'] + r['h'] for r in rectangles})
    cut_active = {y: model.NewBoolVar(f'cut_{y}') for y in all_y_coords if 0 < y < container_height}

    # Vincoli: nessuna linea attiva può passare dentro un rettangolo
    for r in rectangles:
        r_id = r['id']
        y_new = y_final[r_id]
        for y_cut in cut_active:
            within = model.NewBoolVar(f"cut_{y_cut}_in_{r_id}")
            model.Add(y_new <= y_cut).OnlyEnforceIf(within)
            model.Add(y_new + r['h'] > y_cut).OnlyEnforceIf(within)
            model.AddBoolOr([within.Not(), cut_active[y_cut].Not()])  # Se within è True, cut deve essere False

    # Funzione obiettivo: più tagli, meno spostamenti
    model.Maximize(
        sum(cut_active.values()) * 1000 - sum(delta_y.values())
    )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL:
        return {
            'adjustments': {r['id']: solver.Value(delta_y[r['id']]) for r in rectangles},
            'cuts': [y for y, var in cut_active.items() if solver.Value(var)],
            'total_displacement': sum(solver.Value(delta_y[r['id']]) for r in rectangles)
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

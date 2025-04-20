from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker
from pulp import LpProblem, LpMinimize, LpVariable, LpBinary, LpContinuous, lpSum, PULP_CBC_CMD

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height, alpha=1, beta=0.05):
    # Passo 1: possibili linee di taglio
    H = sorted(set([0, container_height] + [r["y"] for r in rectangles] + [r["y"] + r["h"] for r in rectangles]))
    V = sorted(set([0, container_width] + [r["x"] for r in rectangles] + [r["x"] + r["w"] for r in rectangles]))

    # Step 2: modello
    model = LpProblem("Minimize_Cuts_and_Adjustments", LpMinimize)

    h_cuts = {y: LpVariable(f"h_{y}", cat=LpBinary) for y in H}
    v_cuts = {x: LpVariable(f"v_{x}", cat=LpBinary) for x in V}
    dy = {r["id"]: LpVariable(f"dy_{r['id']}", lowBound=0, cat=LpContinuous) for r in rectangles}

    # Step 3: vincoli
    for r in rectangles:
        rid = r["id"]
        x_left = r["x"]
        x_right = r["x"] + r["w"]
        y_top = r["y"]
        y_bottom = r["y"] + r["h"]

        model += lpSum([
            h_cuts[y] for y in H
            if abs(y_top - y) <= 0.01 or abs(y_bottom - y) <= 0.01
        ]) >= 1

        model += lpSum([
            v_cuts[x] for x in V
            if x == x_left or x == x_right
        ]) >= 1

    # Step 4: funzione obiettivo
    model += alpha * (lpSum(h_cuts.values()) + lpSum(v_cuts.values())) + beta * lpSum(dy.values())

    # Step 5: risoluzione
    model.solve(PULP_CBC_CMD(msg=0))

    # Step 6: output
    return {
        "h_cuts": [y for y in H if h_cuts[y].varValue == 1],
        "v_cuts": [x for x in V if v_cuts[x].varValue == 1],
        "adjustments": {r["id"]: dy[r["id"]].varValue for r in rectangles}
    }

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

from copy import deepcopy
from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker
from ortools.sat.python import cp_model

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height):
    resolved_rectangles = rectangles.copy()  # Copia dei rettangoli per modifiche
    current_cut_height = 0  # Altezza iniziale della linea di taglio

    while True:
        # Trova la criticità valida più alta sotto i 250
        selected_critical = None
        for rect in resolved_rectangles:
            rect_bottom_y = rect["y"] + rect["h"]
            if rect_bottom_y > current_cut_height:
                # Trova i rettangoli attraversati dalla linea orizzontale
                conflicts = []
                for other_rect in resolved_rectangles:
                    if rect["id"] == other_rect["id"]:
                        continue
                    if (
                        rect_bottom_y > other_rect["y"] and
                        rect_bottom_y < other_rect["y"] + other_rect["h"]
                    ):
                        conflicts.append(other_rect)
                        move_by = rect_bottom_y - (other_rect["y"])
                        total_area_to_move += move_by * other_rect["w"]
                if conflicts:
                    # Se la linea è valida (sotto i 250), aggiorna selected_critical
                    if rect_bottom_y - current_cut_height <= 250:
                        if (
                            selected_critical is None or
                            total_area_to_move < selected_critical["total_area_to_move"] or
                            (
                                total_area_to_move == selected_critical["total_area_to_move"] and
                                rect_bottom_y > selected_critical["line_y"]
                            )
                        ):
                            selected_critical = {
                                "line_y": rect_bottom_y,
                                "conflicts": conflicts,
                                "total_area_to_move": total_area_to_move
                            }
                    else:
                        break
                else:
                    if rect_bottom_y - current_cut_height <= 250:
                        current_cut_height = rect_bottom_y
                        selected_critical = None


        # Se non ci sono criticità valide, termina
        if not selected_critical:
            break
        max_bottom_y = max(rect["y"] + rect["h"] for rect in resolved_rectangles)
        if max_bottom_y - current_cut_height < 250:
            break

        # Risolvi la criticità selezionata
        current_cut_height = selected_critical["line_y"]
        resolved_rectangles = propose_solution(
            resolved_rectangles,
            selected_critical["line_y"],
            selected_critical["conflicts"],
            container_height
        )

    return resolved_rectangles

def propose_solution(rectangles, line_y, conflicts, container_height):
    moved_rectangles = {}  # Mappa per tracciare quanto è stato spostato ogni rettangolo

    def move_rectangle(rect_id, move_by, area):
        """
        Sposta un rettangolo verso il basso e aggiorna i rettangoli sottostanti.
        :param rect_id: ID del rettangolo da spostare.
        :param move_by: Quantità di spostamento verso il basso.
        :param area: Area di tocco (x_min, x_max) da considerare per i rettangoli sottostanti.
        """
        # Trova il rettangolo nella lista originale
        rect = next(r for r in rectangles if r["id"] == rect_id)

        if rect_id in moved_rectangles:
            # Se il rettangolo è già stato spostato, spostalo solo se necessario
            move_by = max(move_by, moved_rectangles[rect_id])
        moved_rectangles[rect_id] = move_by

        # Calcola la nuova posizione Y
        new_y = rect["y"] + move_by
        if new_y + rect["h"] > container_height:
            raise ValueError(f"Rettangolo {rect['id']} non può essere spostato oltre il contenitore.")

        rect["y"] = new_y

        # Espandi l'area di tocco per i rettangoli sottostanti
        new_area = (min(area[0], rect["x"]), max(area[1], rect["x"] + rect["w"]))

        # Propaga il movimento ai rettangoli sottostanti
        for other_rect in rectangles:
            if other_rect["id"] == rect["id"]:
                continue
            if (
                other_rect["y"] < rect["y"] + rect["h"] and
                other_rect["y"] + other_rect["h"] > rect["y"] and
                other_rect["x"] + other_rect["w"] > new_area[0] and
                other_rect["x"] < new_area[1]
            ):
                move_rectangle(other_rect["id"], move_by, new_area)

    # Sposta tutti i rettangoli coinvolti
    for conflict in conflicts:
        move_by = line_y - conflict["y"]
        if move_by > 0:
            # L'area iniziale di tocco è limitata al rettangolo stesso
            initial_area = (conflict["x"], conflict["x"] + conflict["w"])
            move_rectangle(conflict["id"], move_by, initial_area)

    return rectangles

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

            # Salva la disposizione originale
            original_disposition = deepcopy(packed_rects)

            # Calcola l'ottimizzazione dei tagli per questo bin
            optimized_disposition = optimize_cuts(deepcopy(packed_rects), bin_width, bin_height)

            all_bins_output.append({
                "bin_index": bin_index,
                "original": original_disposition,  # Disposizione originale
                "optimized": optimized_disposition  # Disposizione ottimizzata
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
from collections import defaultdict
from copy import deepcopy
import os
from flask import Flask, json, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height):
    unplaced = []
    current_cut_height = 0
    
    while True:
        selected = None
        rectangles.sort(key=lambda r: r["y"] + r["h"])
        for rect in rectangles:
            bottom = rect["y"] + rect["h"]
            if bottom <= current_cut_height:
                continue
            # find overlaps
            conflicts, area = [], 0
            for other in rectangles:
                if other["id"] == rect["id"]:
                    continue
                if bottom > other["y"] and bottom < other["y"] + other["h"]:
                    conflicts.append(other)
                    move_by = bottom - other["y"]
                    area += move_by * other["w"]
            if conflicts:
                 # Se la linea è valida (sotto i 250), aggiorna selected_critical
                if bottom - current_cut_height <= 250:
                    if (
                        selected is None or
                         area < selected["total_area_to_move"] or
                         (
                             area == selected["total_area_to_move"] and
                             bottom > selected["line"]
                         )
                    ):
                        selected = {
                             "line": bottom,
                             "conflicts": conflicts,
                             "total_area_to_move": area
                         }
                else:
                    break
            else:
                 if bottom - current_cut_height <= 250:
                     current_cut_height = bottom
                     selected = None
 
        if not selected:
            break

        if max(r["y"] + r["h"] for r in rectangles) - current_cut_height < 250:
            break

        line = selected["line"]
        below = [r for r in rectangles if r["y"] + r["h"] > line]
        rectangles = [r for r in rectangles if r["y"] + r["h"] <= line]

        packer = newPacker(rotation=True)
        for r in below:
            packer.add_rect(r["w"], r["h"], rid=r["id"])
        packer.add_bin(container_width, container_height - line)
        packer.add_bin(container_width, container_height - line)
        packer.pack()

        for bin_idx, abin in enumerate(packer):
            for r in abin:
                if bin_idx == 0:
                    rectangles.append({"id": r.rid, "x": r.x, "y": r.y + line, "w": r.width, "h": r.height})
                else:
                    unplaced.append({"id": r.rid, "w": r.width, "h": r.height})
        current_cut_height = line

    return rectangles, unplaced

@app.route("/pack", methods=["POST"])
def pack():
    data = request.get_json()
    if not data or 'bin_width' not in data or 'bin_height' not in data or 'rectangles' not in data:
        return jsonify({"error": "Dati mancanti o non validi"}), 400
    try:
        W, H = int(data["bin_width"]), int(data["bin_height"])
        rects = data["rectangles"]
        packer = newPacker(rotation=True)
        for r in rects:
            w, h = int(r["w"]), int(r["h"])
            if w <= 0 or h <= 0:
                return jsonify({"error": f"Dimensione rettangolo non valida: {r}"}), 400
            packer.add_rect(w, h, rid=r["id"])
        for _ in range(100):
            packer.add_bin(W, H)
        packer.pack()

        # Mappatura rettangoli per bin
        rects_by_bin = defaultdict(list)
        unplaced_rects = [rect for rect in packer.rect_list() if rect[5] is None]

        for bin_index, abin in enumerate(packer):
            for rect in abin:
                rects_by_bin[bin_index].append({
                    "id": rect.rid,
                    "x": rect.x,
                    "y": rect.y,
                    "w": rect.width,
                    "h": rect.height
                })

        all_bins_output = []
        remaining = []

        for bin_index, rect_list in rects_by_bin.items():
            original_disposition = deepcopy(rect_list)
            optimized_disposition, extra_unplaced = optimize_cuts(deepcopy(rect_list), W, H)
            all_bins_output.append({
                "bin_index": bin_index,
                "original": original_disposition,
                "optimized": optimized_disposition
            })
            remaining.extend(extra_unplaced)

        for u in unplaced_rects:
            remaining.append({"id": u[2], "w": u[3], "h": u[4]})

        for u in remaining:
            placed = False
            for b in all_bins_output:
                test = newPacker(rotation=True)
                for r in b["optimized"]:
                    test.add_rect(r["w"], r["h"], rid=r["id"])
                test.add_rect(u["w"], u["h"], rid=u["id"])
                test.add_bin(W, H)
                test.pack()

                if any(r[2] == u["id"] and r[5] is not None for r in test.rect_list()):
                    recs = []
                    for abin in test:
                        for r in abin:
                            recs.append({"id": r.rid, "x": r.x, "y": r.y, "w": r.width, "h": r.height})
                    optimized, _ = optimize_cuts(recs, W, H)
                    b["optimized"] = optimized
                    placed = True
                    break
            if not placed:
                init = [{"id": u["id"], "x": 0, "y": 0, "w": u["w"], "h": u["h"]}]
                opt, _ = optimize_cuts(init, W, H)
                all_bins_output.append({"bin_index": len(all_bins_output), "original": init, "optimized": opt})

        return jsonify({"bins": all_bins_output, "unplaced": len(remaining)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

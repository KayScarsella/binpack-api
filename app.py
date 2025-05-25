from collections import defaultdict
from copy import deepcopy
import os
from flask import Flask, json, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker

app = Flask(__name__)
CORS(app)

# LISTA per salvare i valori di current_cut_height
cut_heights_log = []

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
                    if (selected is None):
                        if area >= rect["w"] * rect["h"]:
                            continue 
                        selected = {
                            "line": bottom,
                            "conflicts": conflicts,
                            "total_area_to_move": area
                        }
                    break
            else:
                current_cut_height = bottom
                cut_heights_log.append(current_cut_height)
                selected = None

        if not selected:
            break

        if max(r["y"] + r["h"] for r in rectangles) - current_cut_height < 250:
            break

        line = selected["line"]
        below = [r for r in rectangles if r["y"] + r["h"] > line]
        above = [r for r in rectangles if r["y"] >= current_cut_height and r["y"] + r["h"] <= line]
        rectangles = [r for r in rectangles if not (r in below or r in above)]
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
        available_height =  line -current_cut_height
        if above and available_height > 0:
            packer_above = newPacker(rotation=True)
            for r in above:
                packer_above.add_rect(r["w"], r["h"], rid=r["id"])
            packer_above.add_bin(container_width, available_height)
            packer_above.pack()
            for abin in enumerate(packer_above):
                for r in abin:
                    rectangles.append({
                        "id": r.rid,
                        "x": r.x,
                        "y": r.y + current_cut_height,
                        "w": r.width,
                        "h": r.height
                    })

        current_cut_height = line
        # Aggiungo il valore alla lista
        cut_heights_log.append(current_cut_height)

    return rectangles, unplaced
@app.route("/pack", methods=["POST"])
def pack():
    # Pulisco il log a ogni nuova chiamata
    cut_heights_log.clear()

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
            bin_cut_heights_log = cut_heights_log[:]

            all_bins_output.append({
                "bin_index": bin_index,
                "original": original_disposition,
                "optimized": optimized_disposition,
                "scarti": len(extra_unplaced) > 0,
                "cuts": bin_cut_heights_log
            })
            cut_heights_log.clear()
            remaining.extend(extra_unplaced)

        for u in unplaced_rects:
            remaining.append({"id": u[2], "w": u[3], "h": u[4]})

        while remaining:
            target_bin = next((b for b in reversed(all_bins_output) if not b.get("scarti")), None)
            if target_bin:
                test = newPacker(rotation=True)
                for r in target_bin["optimized"]:
                    test.add_rect(r["w"], r["h"], rid=r["id"])
                for r in remaining:
                    test.add_rect(r["w"], r["h"], rid=r["id"])
                test.add_bin(W, H)
                test.add_bin(W, H)
                test.pack()

                new_rects = []
                not_placed = []
                for bin_idx, abin in enumerate(test):
                    for r in abin:
                        if bin_idx == 0:
                            new_rects.append({"id": r.rid, "x": r.x, "y": r.y, "w": r.width, "h": r.height})
                        else:
                            not_placed.append({"id": r.rid, "w": r.width, "h": r.height})

                optimized, extra_unplaced = optimize_cuts(deepcopy(new_rects), W, H)
                target_bin["optimized"] = optimized
                target_bin["scarti"] = len(extra_unplaced) > 0
                target_bin["cuts"] = cut_heights_log[:]
                cut_heights_log.clear()
                remaining = not_placed + extra_unplaced
            else:
                packer = newPacker(rotation=True)
                for r in remaining:
                    packer.add_rect(r["w"], r["h"], rid=r["id"])
                packer.add_bin(W, H)
                packer.pack()
                init = []
                for abin in packer:
                    for r in abin:
                        init.append({"id": r.rid, "x": r.x, "y": r.y, "w": r.width, "h": r.height})

                opt, ups = optimize_cuts(deepcopy(init), W, H)
                all_bins_output.append({
                    "bin_index": len(all_bins_output),
                    "original": [],
                    "optimized": opt,
                    "scarti": len(ups) > 0,
                    "cuts": cut_heights_log[:]
                })
                cut_heights_log.clear()
                remaining = ups

        return jsonify({
            "bins": all_bins_output,
            "unplaced": 0,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
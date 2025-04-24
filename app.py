from copy import deepcopy
from flask import Flask, request, jsonify
from flask_cors import CORS 
from rectpack import newPacker

app = Flask(__name__)
CORS(app)

def optimize_cuts(rectangles, container_width, container_height):
    resolved = rectangles.copy()
    unplaced = []
    current_cut_height = 0

    # Sorting for deterministic behavior
    resolved.sort(key=lambda r: r["y"] + r["h"])
    
    while True:
        selected = None
        for rect in resolved:
            bottom = rect["y"] + rect["h"]
            if bottom <= current_cut_height:
                continue
            # find overlaps
            conflicts, area = [], 0
            for other in resolved:
                if other["id"] == rect["id"]:
                    continue
                if bottom > other["y"] and bottom < other["y"] + other["h"]:
                    conflicts.append(other)
                    move_by = bottom - other["y"]
                    area += move_by * other["w"]
            if bottom - current_cut_height > 250:
                break
            if conflicts:
                if selected is None or area < selected["area"] or (area == selected["area"] and bottom > selected["line"]):
                    selected = {"line": bottom, "conflicts": conflicts, "area": area}
            else:
                current_cut_height = bottom
                selected = None
        if not selected:
            break

        if max(r["y"] + r["h"] for r in resolved) - current_cut_height < 250:
            break

        line = selected["line"]
        below = [r for r in resolved if r["y"] + r["h"] > line]
        resolved = [r for r in resolved if r["y"] + r["h"] <= line]

        # pack below
        packer = newPacker(rotation=True)
        for r in below:
            packer.add_rect(r["w"], r["h"], rid=r["id"])
        packer.add_bin(container_width, container_height - line)
        packer.pack()

        # retrieve placed
        for abin in packer:
            for r in abin:
                resolved.append({"id": r.rid, "x": r.x, "y": r.y + line, "w": r.width, "h": r.height})
        # retrieve unplaced of this stage
        stage_unplaced = [r for r in packer.rect_list() if r[5] is None]
        if stage_unplaced:
            unplaced.extend({"id": r[2], "w": r[3], "h": r[4]} for r in stage_unplaced)

        current_cut_height = line

    return resolved, unplaced

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
        for _ in range(100): packer.add_bin(W, H)
        packer.pack()

        # initial bins
        bins = []
        unplaced = [r for r in packer.rect_list() if r[5] is None]
        for idx, abin in enumerate(packer):
            rects0 = [{"id": r.rid, "x": r.x, "y": r.y, "w": r.width, "h": r.height} for r in abin]
            opt, ups = optimize_cuts(deepcopy(rects0), W, H)
            bins.append({"original": rects0, "optimized": opt, "unplaced": ups})

        # collect all unplaced
        all_unplaced = []
        for b in bins:
            all_unplaced.extend(b["unplaced"])

        # try fitting all_unplaced into existing bins
        remaining = []
        for u in all_unplaced:
            placed = False
            for b in bins:
                test = newPacker(rotation=True)
                for r in b["optimized"]:
                    test.add_rect(r["w"], r["h"], rid=r["id"])
                test.add_rect(u["w"], u["h"], rid=u["id"])
                test.add_bin(W, H)
                test.pack()
                if any(r[2]==u["id"] and r[5] is not None for r in test.rect_list()):
                    # rebuild bin
                    recs = []
                    for abin in test:
                        for r in abin:
                            recs.append({"id": r.rid, "x": r.x, "y": r.y, "w": r.width, "h": r.height})
                    b["optimized"], ups2 = optimize_cuts(recs, W, H)
                    b["unplaced"] = ups2
                    placed = True
                    break
            if not placed:
                remaining.append(u)

        # new bins for remaining
        for u in remaining:
            init = [{"id": u["id"], "x":0, "y":0, "w":u["w"], "h":u["h"]}]
            opt, ups = optimize_cuts(init, W, H)
            bins.append({"original": init, "optimized": opt, "unplaced": ups})

        # format output
        out = []
        for i,b in enumerate(bins):
            out.append({"bin_index": i, "original": b["original"], "optimized": b["optimized"]})
        return jsonify({"bins": out, "unplaced": len(remaining)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

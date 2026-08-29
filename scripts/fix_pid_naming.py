import json, os, glob

ROOT = r"D:\Sovereign_AI\data\pid_analysis"
json_dir = os.path.join(ROOT, "json")
raw_dir = os.path.join(ROOT, "raw")
crop_dir = os.path.join(ROOT, "crops")

for jf in glob.glob(os.path.join(json_dir, "*.json")):
    rec = json.load(open(jf, encoding="utf-8"))
    fname = rec["drawing"]["file_name"]            # e.g. 158.jpg (reliable)
    stem = os.path.splitext(fname)[0]
    old_did = str(rec["drawing"].get("drawing_id", stem))
    if old_did != stem:
        rec["drawing"]["reported_drawing_id"] = old_did   # model's guess, preserved
    rec["drawing"]["drawing_id"] = stem

    # rename raw + crops that used old_did
    for f in glob.glob(os.path.join(raw_dir, f"{old_did}_*")):
        new = os.path.join(raw_dir, os.path.basename(f).replace(old_did, stem, 1))
        os.rename(f, new)
    for f in glob.glob(os.path.join(crop_dir, f"{old_did}_*")):
        new = os.path.join(crop_dir, os.path.basename(f).replace(old_did, stem, 1))
        os.rename(f, new)

    # rewrite json under correct name, remove old
    new_json = os.path.join(json_dir, f"{stem}.json")
    json.dump(rec, open(new_json, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    if os.path.abspath(new_json) != os.path.abspath(jf):
        os.remove(jf)
    print(f"fixed {fname} -> {stem}.json (reported_drawing_id={old_did})")

print("done")

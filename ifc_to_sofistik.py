import ifcopenshell
import ifcopenshell.util.element as util
import ifcopenshell.util.placement as placement
import os

IFC_FILE = os.path.join(os.path.dirname(__file__), "IFC-2x3.ifc")
OUT_FILE = os.path.join(os.path.dirname(__file__), "sofistik_model.dat")

print("=" * 60)
print("  Allplan IFC → SOFiSTiK CADINP Converter")
print("=" * 60)
print(f"  Input : {IFC_FILE}")
print(f"  Output: {OUT_FILE}")
print("=" * 60)

model = ifcopenshell.open(IFC_FILE)
print(f"\n✅ IFC file loaded — schema: {model.schema}\n")

# ── Collect elements ──────────────────────────────────────────
beams    = model.by_type("IfcBeam")
columns  = model.by_type("IfcColumn")
slabs    = model.by_type("IfcSlab")
walls    = model.by_type("IfcWall")
footings = model.by_type("IfcFooting")
members  = model.by_type("IfcMember")

print(f"📦 Elements found:")
print(f"   Beams    : {len(beams)}")
print(f"   Columns  : {len(columns)}")
print(f"   Slabs    : {len(slabs)}")
print(f"   Walls    : {len(walls)}")
print(f"   Footings : {len(footings)}")
print(f"   Members  : {len(members)}")
total = len(beams) + len(columns) + len(slabs) + len(walls) + len(footings) + len(members)
print(f"   ─────────────────")
print(f"   TOTAL    : {total}")

# ── Material helper ───────────────────────────────────────────
def get_material_name(element):
    try:
        mats = util.get_material(element)
        if mats is None:
            return "UNKNOWN"
        if hasattr(mats, "Name"):
            return mats.Name or "UNKNOWN"
        if hasattr(mats, "MaterialLayers"):
            names = [l.Material.Name for l in mats.MaterialLayers if l.Material]
            return ", ".join(names) if names else "UNKNOWN"
        if hasattr(mats, "Materials"):
            names = [m.Name for m in mats.Materials if m]
            return ", ".join(names) if names else "UNKNOWN"
        return str(mats)
    except Exception:
        return "UNKNOWN"

# ── Simple material → SOFiSTiK NMAT mapping ──────────────────
MAT_MAP = {
    # German names (Allplan defaults)
    "STAHLBETON":  "CONC 1  TYPE C30  TITL 'Stahlbeton C30/37'",
    "STAHL":       "STEE 2  TYPE S355 TITL 'Stahl S355'",
    "BETON":       "CONC 1  TYPE C30  TITL 'Beton C30/37'",
    "HOLZ":        "NMAT 3  TYPE GL28 TITL 'Holz GL28h'",        # Timber
    "MAUERWERK":   "NMAT 4  TYPE MZ20 TITL 'Mauerwerk MZ20'",    # Masonry
    # English names
    "C20": "CONC 1  TYPE C20",  "C25": "CONC 2  TYPE C25",
    "C30": "CONC 3  TYPE C30",  "C35": "CONC 4  TYPE C35",
    "C40": "CONC 5  TYPE C40",  "C45": "CONC 6  TYPE C45",
    "C50": "CONC 7  TYPE C50",
    "S235": "STEE 10 TYPE S235", "S275": "STEE 11 TYPE S275",
    "S355": "STEE 12 TYPE S355", "S420": "STEE 13 TYPE S420",
    "STEEL":    "STEE 10 TYPE S355",
    "CONCRETE": "CONC 3  TYPE C30",
    "UNKNOWN":  "NMAT 99  $ UNMAPPED — CHECK!",
}

def map_material(name):
    n = (name or "").upper()
    for key, val in MAT_MAP.items():
        if key in n:
            return val
    return f"NMAT 99  $ UNMAPPED: {name} — CHECK!"

# ── Collect unique materials ──────────────────────────────────
all_elements = list(beams) + list(columns) + list(slabs) + list(walls) + list(footings) + list(members)
seen_mats = {}
for el in all_elements:
    mn = get_material_name(el)
    if mn not in seen_mats:
        seen_mats[mn] = map_material(mn)

print(f"\n🧱 Materials detected:")
for k, v in seen_mats.items():
    print(f"   '{k}' → {v}")

# ── Build CADINP ──────────────────────────────────────────────
lines = []

lines.append("$ " + "=" * 56)
lines.append("$ SOFiSTiK CADINP — generated from Allplan IFC export")
lines.append("$ Source: IFC-2x3.ifc")
lines.append("$ Date  : 2026-05-25")
lines.append("$ REVIEW all materials, sections and boundary conditions")
lines.append("$ before running analysis!")
lines.append("$ " + "=" * 56)
lines.append("")

# ── MATERIALS block ───────────────────────────────────────────
lines.append("+PROG AQUA urs:1")
lines.append("HEAD Materials and Cross-Sections")
lines.append("")
lines.append("$ --- Materials ---")
mat_ids = {}
mat_counter = 1
for mat_name, cadinp_mat in seen_mats.items():
    lines.append(cadinp_mat)
    mat_ids[mat_name] = mat_counter
    mat_counter += 1
lines.append("")
lines.append("$ --- Cross-Sections (defaults — adjust per project) ---")
lines.append("SREC 1  H 0.30  B 0.30  MNO 3  $ Default column 300x300 C30")
lines.append("SREC 2  H 0.50  B 0.30  MNO 3  $ Default beam   500x300 C30")
lines.append("SVAL 3  H 0.20  MNO 3          $ Default slab   200mm C30")
lines.append("")
lines.append("END")
lines.append("")

# ── STRUCTURAL MODEL block ────────────────────────────────────
lines.append("+PROG SOFIMSHA urs:2")
lines.append("HEAD Structural Model")
lines.append("")
lines.append("SYST 3D GIRD")
lines.append("")

# Columns
if columns:
    lines.append("$ ── Columns ──────────────────────────────────────────────")
    for i, col in enumerate(columns, 1):
        name = (col.Name or f"Column_{i}").replace(" ", "_")
        mat  = get_material_name(col)
        lines.append(f"$ Column {i}: {name}  |  Material: {mat}")
        lines.append(f"BEAM {1000+i}  NCS 1  $ {name}")
    lines.append("")

# Beams
if beams:
    lines.append("$ ── Beams ────────────────────────────────────────────────")
    for i, beam in enumerate(beams, 1):
        name = (beam.Name or f"Beam_{i}").replace(" ", "_")
        mat  = get_material_name(beam)
        lines.append(f"$ Beam {i}: {name}  |  Material: {mat}")
        lines.append(f"BEAM {2000+i}  NCS 2  $ {name}")
    lines.append("")

# Members
if members:
    lines.append("$ ── Members ──────────────────────────────────────────────")
    for i, mem in enumerate(members, 1):
        name = (mem.Name or f"Member_{i}").replace(" ", "_")
        lines.append(f"BEAM {3000+i}  NCS 2  $ {name}")
    lines.append("")

# Slabs
if slabs:
    lines.append("$ ── Slabs ────────────────────────────────────────────────")
    for i, slab in enumerate(slabs, 1):
        name = (slab.Name or f"Slab_{i}").replace(" ", "_")
        mat  = get_material_name(slab)
        lines.append(f"$ Slab {i}: {name}  |  Material: {mat}")
        lines.append(f"QUAD {4000+i}  MNO 3  T 0.20  $ {name}")
    lines.append("")

# Walls
if walls:
    lines.append("$ ── Walls ────────────────────────────────────────────────")
    for i, wall in enumerate(walls, 1):
        name = (wall.Name or f"Wall_{i}").replace(" ", "_")
        mat  = get_material_name(wall)
        lines.append(f"$ Wall {i}: {name}  |  Material: {mat}")
        lines.append(f"QUAD {5000+i}  MNO 3  T 0.25  $ {name}")
    lines.append("")

# Footings
if footings:
    lines.append("$ ── Footings ─────────────────────────────────────────────")
    for i, ft in enumerate(footings, 1):
        name = (ft.Name or f"Footing_{i}").replace(" ", "_")
        lines.append(f"$ Footing {i}: {name}")
        lines.append(f"QUAD {6000+i}  MNO 3  T 0.60  $ {name}")
    lines.append("")

lines.append("END")
lines.append("")

# ── LOADS placeholder ─────────────────────────────────────────
lines.append("+PROG SOFILOAD urs:3")
lines.append("HEAD Load Cases — define manually")
lines.append("")
lines.append("$ ⚠️  Loads are NOT transferred via IFC.")
lines.append("$ Define your load cases here.")
lines.append("")
lines.append("LC 1  TYPE G  TITL 'Self Weight'")
lines.append("  SELF FACG -1.0   $ Automatic self weight")
lines.append("")
lines.append("LC 2  TYPE Q  TITL 'Live Load'")
lines.append("$ QUAD ... PZZE -5.0   $ Example: 5 kN/m² on slabs")
lines.append("")
lines.append("END")
lines.append("")

# ── Write file ────────────────────────────────────────────────
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n{'='*60}")
print(f"✅ DONE — sofistik_model.dat written successfully!")
print(f"{'='*60}")
print(f"\n📄 File: {OUT_FILE}")
print(f"   Lines written: {len(lines)}")
print(f"\n📌 Next steps in SOFiSTiK:")
print(f"   1. Open TEDDY and load sofistik_model.dat")
print(f"   2. Review all materials in the AQUA block")
print(f"   3. Adjust cross-section dimensions (SREC / SVAL)")
print(f"   4. Define loads in the SOFILOAD block")
print(f"   5. Run analysis via SSD")
print(f"\n⚠️  Always verify structural properties before FEA!")
print("=" * 60)

# Allplan Bridge → SOFiSTiK: Code-Driven Conversion Guide for Bridge Engineers

> **Purpose:** Deep technical guide for converting **bridge** designs from Allplan Bridge to SOFiSTiK via code (Python + IfcOpenShell).  
> **Companion to:** `Allplan_to_SOFiSTiK_Methods_Comparison.md`  
> **Date:** 2026-05-25  
> **Scope:** Bridge-specific concerns — alignment, prestressing, construction stages, girder geometry

---

## 🌉 Why Bridges Are Different From Buildings

When the previous comparison document was written, it covered general structural models. Bridges add a completely different layer of complexity:

| Challenge | Building | Bridge |
|---|---|---|
| **Reference geometry** | X-Y grid | **Alignment curve** (horizontal + vertical) |
| **Element definition** | Absolute coordinates | Station-based (chainage) coordinates |
| **Cross-sections** | Usually uniform | **Variable / parametric** along alignment |
| **Prestressing** | Rare | **Core element** — tendons with curvature |
| **Construction stages** | Simple | **Critical** — balanced cantilever, staging |
| **Traffic loads** | Point loads | **Influence lines**, moving loads |
| **IFC schema** | IFC 4 or 2x3 | **IFC 4.3** (new bridge entities) |
| **SOFiSTiK modules** | SOFIMSHA + AQB | + TENDON + CSM + ELLA + MAXIMA |

**Bottom line:** You cannot treat a bridge export as a building export. A different IFC schema, a different CADINP structure, and a different Python approach are required.

---

## 🗺️ The Big Picture: Two Code Routes for Bridges

```
Allplan Bridge
    │
    ├─── Route A: IFC 4.3 → ifcopenshell → CADINP
    │    (Bridge-aware: reads IfcAlignment, IfcBridge entities)
    │    Best for: new projects on Allplan 2024+ / SOFiSTiK 2026+
    │
    └─── Route B: IFC 4 Structural → ifcopenshell → CADINP
         (Fallback: treats bridge elements as standard structural elements)
         Best for: older versions, simpler bridge types
```

> ⚠️ **IFC 4.3 is the game-changer for bridges.** It is the first IFC version with dedicated bridge entities (`IfcBridge`, `IfcAlignment`, `IfcBridgePart`). SOFiSTiK 2026 introduced improved IFC 4.3 support. Allplan 2024+ can export IFC 4.3 but the full Structural Analysis View for IFC 4.3 is still maturing — always verify your export.

---

## 📐 Part 1: Understanding the IFC 4.3 Bridge Schema

IFC 4.3 (the **Infrastructure Domain Extension**) introduced entities specifically for bridge and road design:

### Key New Entities

```
IfcBridge                  ← Top-level container for the bridge project
├── IfcBridgePart          ← Superstructure, substructure, deck, pylon, etc.
│
IfcAlignment               ← The road/bridge centerline
├── IfcAlignmentHorizontal ← Plan view: straights, circular arcs, clothoids
├── IfcAlignmentVertical   ← Profile: grades, parabolic transitions
└── IfcAlignmentCant       ← Cross-slope / superelevation

IfcSectionedSolidHorizontal  ← Variable cross-section extruded along alignment
IfcLinearPlacement           ← Position elements along the alignment by station
```

### What Allplan Bridge Can Export to IFC 4.3

| Data | IFC 4.3 Entity | Available in Allplan? |
|---|---|---|
| Bridge centerline (alignment) | `IfcAlignment` | ✅ Allplan 2024+ |
| Deck / superstructure | `IfcBridgePart` | ✅ |
| Variable cross-section | `IfcSectionedSolidHorizontal` | ✅ |
| Girder beams | `IfcBeam` + `IfcLinearPlacement` | ✅ |
| Piers / columns | `IfcColumn` | ✅ |
| Foundations / footings | `IfcFooting` | ✅ |
| Prestressing tendons | `IfcTendon` (IFC 4+) | ⚠️ Partial |
| Construction stages | — | ❌ Not in IFC |
| Moving loads / influence | — | ❌ Not in IFC |
| Reinforcement bars | `IfcReinforcingBar` | ⚠️ Partial |

---

## 🐍 Part 2: Python Code — Route A (IFC 4.3, Full Bridge)

### 2.1 Setup

```bash
pip install ifcopenshell numpy
```

> Use IfcOpenShell **0.8.x or later** — alignment API was added in 0.7.x and significantly improved in 0.8.x.

### 2.2 Open the IFC and Identify the Alignment

```python
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.api.alignment
import numpy as np

model = ifcopenshell.open("allplan_bridge.ifc")

# --- Get the alignment(s) ---
alignments = model.by_type("IfcAlignment")
print(f"Found {len(alignments)} alignment(s)")

for a in alignments:
    name = a.Name or "Unnamed"
    print(f"\n  Alignment: {name}")

    # Horizontal layout
    h_layout = ifcopenshell.api.alignment.get_horizontal_layout(a)
    h_segs = ifcopenshell.api.alignment.get_layout_segments(h_layout)
    print(f"  Horizontal segments: {len(h_segs)}")
    for seg in h_segs:
        print(f"    {seg.DesignParameters.is_a()} — "
              f"StartPoint, Length={seg.DesignParameters.SegmentLength:.2f}")

    # Vertical layout
    v_layout = ifcopenshell.api.alignment.get_vertical_layout(a)
    if v_layout:
        v_segs = ifcopenshell.api.alignment.get_layout_segments(v_layout)
        print(f"  Vertical segments: {len(v_segs)}")

    # Start station
    start_sta = ifcopenshell.api.alignment.get_alignment_start_station(a)
    print(f"  Start station: {start_sta}")
```

### 2.3 Extract Structural Elements (Station-Based)

```python
def get_element_station(element):
    """
    For elements placed via IfcLinearPlacement, extract their chainage (station).
    """
    placement = element.ObjectPlacement
    if placement and placement.is_a("IfcLinearPlacement"):
        ref = placement.Distance
        if ref:
            return ref.DistanceAlong  # station value in metres
    return None

# Gather all bridge structural elements
beams   = model.by_type("IfcBeam")
columns = model.by_type("IfcColumn")
slabs   = model.by_type("IfcSlab")

print(f"\nBeams: {len(beams)}, Columns: {len(columns)}, Slabs: {len(slabs)}")

bridge_elements = []
for elem in beams + columns + slabs:
    station = get_element_station(elem)
    mat = ifcopenshell.util.element.get_material(elem)
    pset = ifcopenshell.util.element.get_psets(elem)

    bridge_elements.append({
        "id":       elem.GlobalId,
        "type":     elem.is_a(),
        "name":     elem.Name or "",
        "station":  station,       # metres along alignment; None if absolute
        "material": mat.Name if mat else "UNKNOWN",
        "psets":    pset,
    })

# Sort by station for ordered CADINP output
bridge_elements.sort(key=lambda e: (e["station"] or 0))
```

### 2.4 Extract Cross-Section Profiles

```python
def get_profile_name(element):
    """
    Return a profile name/description from the element's material profile set.
    """
    material = ifcopenshell.util.element.get_material(element)
    if not material:
        return None
    if material.is_a("IfcMaterialProfileSetUsage"):
        profile_set = material.ForProfileSet
        for item in profile_set.MaterialProfiles:
            profile = item.Profile
            return profile.ProfileName or profile.is_a()
    return None

def extract_section_dimensions(element):
    """
    For parametric sections: return width, height from IfcRectangleProfileDef
    or flange/web from IfcIShapeProfileDef, etc.
    """
    material = ifcopenshell.util.element.get_material(element)
    dims = {}
    if material and material.is_a("IfcMaterialProfileSetUsage"):
        for item in material.ForProfileSet.MaterialProfiles:
            p = item.Profile
            if p.is_a("IfcRectangleProfileDef"):
                dims = {"type": "RECT", "width": p.XDim, "height": p.YDim}
            elif p.is_a("IfcIShapeProfileDef"):
                dims = {
                    "type":       "ISEC",
                    "width":      p.OverallWidth,
                    "height":     p.OverallDepth,
                    "flange_t":   p.FlangeThickness,
                    "web_t":      p.WebThickness,
                }
            elif p.is_a("IfcTShapeProfileDef"):
                dims = {
                    "type":   "TSEC",
                    "width":  p.FlangeWidth,
                    "height": p.Depth,
                    "flange_t": p.FlangeThickness,
                    "web_t":    p.WebThickness,
                }
    return dims
```

### 2.5 Extract Tendons

```python
tendons = model.by_type("IfcTendon")
print(f"\nTendons found: {len(tendons)}")

tendon_data = []
for t in tendons:
    psets = ifcopenshell.util.element.get_psets(t)
    
    # Tendon geometry via IfcPolyline or IfcCompositeCurve representation
    geom_reps = []
    if t.Representation:
        for rep in t.Representation.Representations:
            for item in rep.Items:
                if item.is_a("IfcPolyline"):
                    pts = [(p.Coordinates[0], p.Coordinates[1], p.Coordinates[2])
                           for p in item.Points]
                    geom_reps.append(pts)

    tendon_data.append({
        "id":          t.GlobalId,
        "name":        t.Name or "",
        "diameter":    t.NominalDiameter,
        "area":        t.CrossSectionArea,
        "pretension":  t.TensionForce,
        "geometry":    geom_reps,   # list of (x,y,z) control points
        "psets":       psets,
    })
```

---

## 📝 Part 3: Writing CADINP for Bridge Models

SOFiSTiK bridge analysis uses a pipeline of modules. For a code-generated `.dat` file, here is the **standard bridge CADINP structure**:

```
┌─────────────────────────────────────────────────────┐
│  +PROG AQUA                                          │  ← Materials & cross-sections
│  +PROG SOFIMSHA (or SOFIMSHB)                        │  ← Structural mesh (nodes, beams, shells)
│  +PROG SOFILOAD                                      │  ← Dead loads, live loads
│  +PROG TENDON                                        │  ← Prestressing tendon geometry
│  +PROG ASE                                           │  ← Linear FEA
│  +PROG CSM                                           │  ← Construction stage manager
│  +PROG ELLA                                          │  ← Influence lines / moving loads
│  +PROG AQB                                           │  ← Cross-section design (RC/PSC)
│  +PROG MAXIMA                                        │  ← Envelope / combination
└─────────────────────────────────────────────────────┘
```

### 3.1 AQUA: Materials and Cross-Sections

```python
def write_aqua_block(bridge_elements, materials_map, sections_map):
    """
    Generate the AQUA CADINP block.
    materials_map: { "C35/45": 1, "S355": 2, ... }
    sections_map:  { "BOX_1m": {"type":"RECT","width":1.0,"height":0.8}, ... }
    """
    lines = [
        "+PROG AQUA urs:1",
        "HEAD 'Materials and Cross-Sections'",
        "NORM EN 1992",
        "",
        "$ --- Materials ---",
    ]

    # Concrete materials
    for mat_name, mat_id in materials_map.items():
        if "C" in mat_name:    # e.g. C35/45, C40/50
            lines.append(f"NMAT {mat_id} TYPE C{mat_name.split('/')[0][1:]} TITL '{mat_name}'")
        elif "S" in mat_name:  # e.g. S355
            grade = mat_name.replace("S", "")
            lines.append(f"NMAT {mat_id} TYPE S TITL '{mat_name}' "
                         f"FY 355 FU 510")

    lines += ["", "$ --- Cross-Sections ---"]

    for i, (sec_name, dims) in enumerate(sections_map.items(), start=1):
        if dims["type"] == "RECT":
            lines += [
                f"SECT {i} MNO 1 TITL '{sec_name}'",
                f"POLY TYPE O",
                f"  VERT {-dims['width']/2:.4f} {-dims['height']/2:.4f}",
                f"  VERT  {dims['width']/2:.4f} {-dims['height']/2:.4f}",
                f"  VERT  {dims['width']/2:.4f}  {dims['height']/2:.4f}",
                f"  VERT {-dims['width']/2:.4f}  {dims['height']/2:.4f}",
            ]
        elif dims["type"] == "ISEC":
            lines.append(
                f"CSEC {i} MNO 2 TITL '{sec_name}' "
                f"HH {dims['height']:.4f} BO {dims['width']:.4f} "
                f"BO2 {dims['width']:.4f} SO {dims['web_t']:.4f} "
                f"TO {dims['flange_t']:.4f} TO2 {dims['flange_t']:.4f}"
            )

    lines.append("END")
    return "\n".join(lines)
```

### 3.2 SOFIMSHA: Bridge Structural Mesh

```python
def write_sofimsha_block(bridge_elements, node_spacing=1.0):
    """
    Generate the SOFIMSHA block.
    Beams along alignment are discretised into beam elements.
    node_spacing: distance between nodes in metres (mesh density).
    """
    lines = [
        "+PROG SOFIMSHA urs:2",
        "HEAD 'Bridge Structural Model'",
        "SYST PROB NONL GDIR NEGZ GDIV 1000",  # Gravity -Z, nonlinear allowed
        "",
        "$ --- Groups ---",
        "GRPB 1 TITL 'Superstructure'",
        "GRPB 2 TITL 'Substructure_Piers'",
        "GRPB 3 TITL 'Substructure_Foundations'",
        "",
    ]

    node_id   = 1
    elem_id   = 1
    node_map  = {}  # station (rounded) → node_id

    lines.append("$ --- Nodes (along alignment) ---")

    beam_elems = [e for e in bridge_elements if e["type"] == "IfcBeam"]
    stations   = sorted(set(e["station"] for e in beam_elems if e["station"] is not None))

    # Create intermediate nodes at node_spacing intervals
    all_stations = set(stations)
    if stations:
        s_min, s_max = min(stations), max(stations)
        s = s_min
        while s <= s_max:
            all_stations.add(round(s, 4))
            s += node_spacing

    for sta in sorted(all_stations):
        # Coordinates: X = station, Y = 0, Z = 0 (alignment at Z=0)
        # In practice you'd apply vertical alignment corrections
        lines.append(f"NODE {node_id} X {sta:.4f} Y 0.0 Z 0.0")
        node_map[round(sta, 4)] = node_id
        node_id += 1

    lines += ["", "$ --- Beam Elements ---"]

    sorted_stations = sorted(node_map.keys())
    for i in range(len(sorted_stations) - 1):
        sta_a = sorted_stations[i]
        sta_b = sorted_stations[i + 1]
        n_a = node_map[sta_a]
        n_b = node_map[sta_b]
        lines.append(
            f"BEAM {elem_id} NA {n_a} NE {n_b} "
            f"NCS 1 GRP 1"   # NCS = cross-section number, GRP = group
        )
        elem_id += 1

    lines += [
        "",
        "$ --- Supports (Piers, Abutments) ---",
        "$ Add spring supports at pier locations:",
        "$ SPRI NODE <n> KX ... KY ... KZ ... KMX ... KMY ... KMZ ...",
        "",
        "END",
    ]
    return "\n".join(lines)
```

### 3.3 TENDON: Prestressing Tendon Definition

```python
def write_tendon_block(tendon_data, ref_node_map):
    """
    Generate the TENDON CADINP block.
    tendon_data: list of tendon dicts from IFC extraction.
    ref_node_map: station → node_id mapping for reference.
    """
    lines = [
        "+PROG TENDON urs:4",
        "HEAD 'Prestressing Tendons'",
        "CTRL WARN 7",
        "",
        "$ Prestressing system (adapt to your system)",
        "$ VSL 6-12 strand: Ap=1600 mm², fp0.1k=1600 MPa",
        "",
    ]

    for t_idx, t in enumerate(tendon_data, start=1):
        area_mm2 = (t["area"] * 1e6) if t["area"] else 1600   # convert m² → mm²
        force_kN = (t["pretension"] / 1000) if t["pretension"] else 0

        lines += [
            f"$ Tendon {t_idx}: {t['name']}",
            f"AXES {t_idx} REFT 1",  # reference to axis 1 (main alignment)
            f"TEND {t_idx} STYP PST PTOT {force_kN:.1f} AP {area_mm2:.0f}",
            f"  $ Control points (station, y-offset, z-offset from beam centroid):",
        ]

        # Convert IFC 3D polyline control points to CADINP TGEO format
        if t["geometry"] and t["geometry"][0]:
            pts = t["geometry"][0]  # first representation
            for pt in pts:
                x, y, z = pt
                # x ≈ station along alignment, z = vertical eccentricity
                lines.append(f"  TGEO X {x:.4f} ZO {z:.4f}")

        lines.append("")

    lines.append("END")
    return "\n".join(lines)
```

### 3.4 SOFILOAD: Bridge Loads

```python
def write_sofiload_block():
    """
    Template SOFILOAD block for a bridge.
    Adapt load values to your project.
    """
    return """
+PROG SOFILOAD urs:3
HEAD 'Loads'

$ --- LC 1: Self-weight (auto-calculated from geometry) ---
LC 1 TITL 'Self-weight' FACT 1.0
  SELF 1.0 DIR Z

$ --- LC 2: Superimposed dead load (pavement, barriers, etc.) ---
LC 2 TITL 'SDL - Pavement'
  GRP  1           $ Apply to group 1 (superstructure)
  BEAM ALL PY -7.5 $ 7.5 kN/m² pavement load (adapt)

$ --- LC 3: Settlement ---
LC 3 TITL 'Settlement Pier 2'
  SPRI NODE 5 DZ -0.01   $ 10 mm settlement at pier node 5

$ --- LC 10-29: Traffic (ELLA will generate influence lines) ---
$ Traffic loads defined as moving load patterns in ELLA module

$ --- LC 100: Temperature Uniform ---
LC 100 TITL 'Temperature Uniform +15'
  TEMP ALL DT 15.0

$ --- LC 101: Temperature Gradient ---
LC 101 TITL 'Temperature Gradient'
  BEAM ALL DTY 5.0   $ 5°C gradient top-to-bottom

END
"""
```

### 3.5 Main Script: Assemble Everything

```python
def ifc_bridge_to_cadinp(ifc_path: str, output_path: str):
    """
    Main function: reads Allplan Bridge IFC 4.3, writes SOFiSTiK CADINP .dat
    """
    import ifcopenshell
    import ifcopenshell.util.element
    import ifcopenshell.api.alignment

    model = ifcopenshell.open(ifc_path)

    # --- 1. Extract alignment ---
    alignments = model.by_type("IfcAlignment")
    if not alignments:
        raise ValueError("No IfcAlignment found — check IFC 4.3 export from Allplan Bridge")
    alignment = alignments[0]
    print(f"Using alignment: {alignment.Name}")

    # --- 2. Extract elements ---
    bridge_elements = []
    for elem in model.by_type("IfcBeam") + model.by_type("IfcColumn") + model.by_type("IfcSlab"):
        sta = get_element_station(elem)
        mat = ifcopenshell.util.element.get_material(elem)
        bridge_elements.append({
            "id":       elem.GlobalId,
            "type":     elem.is_a(),
            "name":     elem.Name or "",
            "station":  sta,
            "material": mat.Name if mat else "C35/45",
            "dims":     extract_section_dimensions(elem),
        })
    bridge_elements.sort(key=lambda e: e["station"] or 0)

    # --- 3. Build lookup tables ---
    materials_map = {}
    mat_id = 1
    for e in bridge_elements:
        if e["material"] not in materials_map:
            materials_map[e["material"]] = mat_id
            mat_id += 1

    sections_map = {}
    for e in bridge_elements:
        sec_name = e["name"] or f"SEC_{e['type']}"
        if sec_name not in sections_map and e["dims"]:
            sections_map[sec_name] = e["dims"]

    # --- 4. Extract tendons ---
    tendon_data = []
    for t in model.by_type("IfcTendon"):
        psets   = ifcopenshell.util.element.get_psets(t)
        geom_reps = []
        if t.Representation:
            for rep in t.Representation.Representations:
                for item in rep.Items:
                    if item.is_a("IfcPolyline"):
                        pts = [(p.Coordinates[0], p.Coordinates[1], p.Coordinates[2])
                               for p in item.Points]
                        geom_reps.append(pts)
        tendon_data.append({
            "id":         t.GlobalId,
            "name":       t.Name or f"T{len(tendon_data)+1}",
            "diameter":   t.NominalDiameter,
            "area":       t.CrossSectionArea,
            "pretension": t.TensionForce,
            "geometry":   geom_reps,
        })

    # --- 5. Generate node map for beam elements ---
    node_spacing = 1.0   # metres — reduce for longer bridges, increase for simple spans
    node_map = {}
    stations = sorted(set(
        round(e["station"], 4) for e in bridge_elements
        if e["type"] == "IfcBeam" and e["station"] is not None
    ))
    if stations:
        s_min, s_max = min(stations), max(stations)
        s = s_min
        nid = 1
        while s <= s_max + 0.001:
            node_map[round(s, 4)] = nid
            s += node_spacing
            nid += 1

    # --- 6. Assemble CADINP ---
    header = f"""\
$ ============================================================
$ CADINP generated from Allplan Bridge IFC
$ Source: {ifc_path}
$ Alignment: {alignment.Name}
$ Elements: {len(bridge_elements)}, Tendons: {len(tendon_data)}
$ Generated: 2026-05-25
$ ============================================================
"""
    blocks = [
        header,
        write_aqua_block(bridge_elements, materials_map, sections_map),
        write_sofimsha_block(bridge_elements, node_spacing),
        write_sofiload_block(),
        write_tendon_block(tendon_data, node_map),
        # Add ASE, CSM, ELLA blocks manually or generate similarly
        "\n$ ---- Add ASE (analysis), CSM (stages), ELLA (traffic) blocks below ----\n",
    ]

    with open(output_path, "w") as f:
        f.write("\n\n".join(blocks))

    print(f"\n✅ Written: {output_path}")
    print(f"   Open in SOFiSTiK TEDDY and verify before running.")

# --- Run it ---
if __name__ == "__main__":
    ifc_bridge_to_cadinp(
        ifc_path="allplan_bridge_export.ifc",
        output_path="sofistik_bridge_model.dat",
    )
```

---

## 🏗️ Part 4: Bridge-Specific CADINP Modules Reference

These are the SOFiSTiK modules you will need that go **beyond** a standard building import:

### AQUA — Section Library
Defines materials and cross-sections. For bridges, this includes:
- Concrete grades: `C30/37`, `C35/45`, `C40/50`, `C50/60`
- Prestressing steel: `STRD` (strand), `TYCL` (type class)
- Box girder, T-beam, solid slab, U-beam cross-sections

### SOFIMSHA — Structural Mesh
Defines nodes, beam elements, shell elements, groups. For bridges:
- Beam elements following the alignment (1D girder model)
- Shell elements for slab/deck (2D model for wide bridges)
- `GRP` (groups) for superstructure vs piers vs abutments

### SOFILOAD — Load Definition
Defines all load cases:
- `LC` — load case definition with action type
- `SELF` — self-weight
- `BEAM` — uniform/varying distributed loads on elements
- `TEMP` / `DELT` — temperature uniform and gradient

### TENDON — Prestressing
Critical for PSC bridges:
- `AXES` — reference axis (follows alignment)
- `TEND` — tendon with stressing force, profile type
- `TGEO` — tendon geometry control points (X = station, ZO = vertical eccentricity)
- `LC` (within TENDON) — primary and secondary prestress effects stored as load cases

### CSM — Construction Stage Manager
For staged construction bridges (balanced cantilever, span-by-span):
- `MSTE` — construction stage
- `SELE` — element selection per stage
- Creep/shrinkage time effects
- Prestress application per stage

### ELLA — Influence Lines / Moving Loads
For traffic analysis per Eurocode (EN 1991-2) or national annex:
- `ELLA LDM` — load distribution model
- `TRAF` — traffic load type (LM1, LM2, LM3, special vehicles)

### AQB — Section Design
Eurocode design checks for PSC/RC cross-sections:
- `CTRL CONC` — concrete design parameters
- `CTRL WARP` — warping for open sections
- `BEAM` — select beams for design

### MAXIMA — Envelope
Combines load cases into envelopes:
- `COMB` — combination rules
- `DESI` — design combination
- Output: max/min envelopes of internal forces

---

## ⚙️ Part 5: Route B — IFC 4 Fallback (Simpler Bridges)

If you are on an older Allplan version that cannot export IFC 4.3 with alignment, use IFC 4 Structural Analysis View. The Python code is simpler but you lose alignment awareness:

```python
import ifcopenshell
import ifcopenshell.util.element

model = ifcopenshell.open("allplan_bridge_ifc4.ifc")

# No IfcAlignment — work purely in Cartesian coordinates
elements = {}
for cls in ["IfcBeam", "IfcColumn", "IfcSlab", "IfcWall", "IfcFooting"]:
    elements[cls] = model.by_type(cls)

# Extract coordinates from IfcLocalPlacement
def get_global_coords(element):
    """Returns (x, y, z) of the element origin in global coordinates."""
    placement = element.ObjectPlacement
    # Walk up the placement chain
    m = np.eye(4)
    while placement:
        if placement.is_a("IfcLocalPlacement"):
            rel = placement.RelativePlacement
            if rel.is_a("IfcAxis2Placement3D"):
                loc = rel.Location.Coordinates
                # Compose transformation matrix (simplified — no rotation)
                m[0, 3] += loc[0]
                m[1, 3] += loc[1]
                m[2, 3] += loc[2]
        placement = getattr(placement, "PlacementRelTo", None)
    return m[0, 3], m[1, 3], m[2, 3]

# Build nodes from element start/end points
# (Requires geometry engine — use ifcopenshell.geom.create_shape for full meshes)
import ifcopenshell.geom

settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)

for beam in elements["IfcBeam"]:
    shape = ifcopenshell.geom.create_shape(settings, beam)
    verts = shape.geometry.verts   # flat list: x0,y0,z0, x1,y1,z1, ...
    # → compute bounding box, start point, end point
    xs = verts[0::3]; ys = verts[1::3]; zs = verts[2::3]
    start = (min(xs), ys[xs.index(min(xs))], zs[xs.index(min(xs))])
    end   = (max(xs), ys[xs.index(max(xs))], zs[xs.index(max(xs))])
    print(f"Beam {beam.Name}: {start} → {end}")
```

> ⚠️ **Route B limitation for bridges:** Without alignment data, you must manually set up the bridge axis in SOFiSTiK. This is fine for simple simply-supported bridges, but it defeats the purpose for curved or skewed bridges.

---

## 🚦 Part 6: Comparison — Routes for Bridge Types

| Bridge Type | Recommended Route | Key IFC Challenge | Key CADINP Modules |
|---|---|---|---|
| **Simply supported beam bridge** | Route B (IFC 4) | None major | AQUA, SOFIMSHA, SOFILOAD, AQB |
| **Continuous beam bridge** | Route B or A | Alignment useful | AQUA, SOFIMSHA, SOFILOAD, TENDON, AQB |
| **Curved/skewed bridge** | **Route A (IFC 4.3)** | Alignment critical | All + ELLA |
| **Box girder (PSC)** | **Route A (IFC 4.3)** | Variable section + tendons | All + TENDON + CSM |
| **Balanced cantilever** | **Route A (IFC 4.3)** | Construction stages | All + CSM + ELLA |
| **Cable-stayed / suspension** | Route A + manual | Cables not in IFC bridge schema | All + SEPP (cable) |
| **Composite steel-concrete** | Route B or A | Material interfaces | AQUA (composite), SOFIMSHA |

---

## 🔧 Part 7: IFC Export Settings in Allplan for Bridges

Getting the IFC export right from Allplan Bridge is critical. Here is the recommended setup:

### For IFC 4.3 (preferred for bridge projects)
```
Allplan Bridge → File → Export → IFC
  ├── File Type: IFC 4.3
  ├── Model View: (None available yet — use full geometry export)
  ├── Export Scheme: "Bridge Structural" (if available in your version)
  ├── Include Alignment: ✅ YES
  ├── Include Tendons: ✅ YES
  └── Include Reinforcement: ✅ YES (if needed)
```

### For IFC 4 Structural Analysis View (fallback)
```
Allplan Bridge → File → Export → IFC
  ├── File Type: IFC 4
  ├── Model View: Structural Analysis View 1.0  ← CRITICAL
  ├── Export content: Structural elements only
  ├── Reference Axis: Include
  └── Exclude: Architectural, formwork, rebar (unless needed)
```

> 💡 **Allplan 2024/2025 note:** The Allplan Bridge module generates an **internal analysis model** that is used for SOFiSTiK analysis within Allplan Bridge itself. The IFC export is a separate pathway — verify that the structural properties (section, material) are included by opening the exported IFC in a viewer like [Bonsai (BlenderBIM)](https://bonsaibim.org/) before running your Python script.

---

## 📋 Part 8: Common Pitfalls Specific to Bridge Projects

| Pitfall | Root Cause | Fix |
|---|---|---|
| No `IfcAlignment` in IFC file | Exported as IFC 4 or "Coordination View" | Re-export as IFC 4.3 or check Allplan export settings |
| Element stations are `None` | Elements placed by `IfcLocalPlacement` not `IfcLinearPlacement` | Fall back to Route B coordinates |
| Tendons missing from IFC | Allplan doesn't export `IfcTendon` in all export modes | Enable in export settings; or define in CADINP manually |
| Wrong coordinate units | IFC uses metres; some Allplan exports use mm | Check `IfcProject → UnitsInContext`; apply scale factor |
| Cross-section not parametric | Exported as `IfcFacetedBrep` (mesh), not `IfcProfileDef` | Use Structural Analysis View; or measure from BREP |
| Variable section lost | Box girder variable section not in IFC 4.3 yet | Export as multiple fixed-section segments per span |
| CADINP silent errors | TENDON geometry has Z-offsets outside section | Validate eccentricities against section height |
| Construction stages absent | IFC has no staging concept | These must be added to CADINP manually using CSM module |
| Moving loads absent | IFC has no moving load concept | Define in ELLA module manually |

---

## 🔮 Part 9: The Future — What's Coming

| Development | Impact on Your Workflow |
|---|---|
| **IFC 4.3 adoption by Allplan** | Full alignment + bridge entities → cleaner Route A export |
| **SOFiSTiK 2026 IFC 4.3 bridge import** | Direct import of `IfcBridge` / `IfcAlignment` into CADINP — may reduce Python scripting need |
| **IfcOpenShell 0.9.x alignment tools** | More robust station-based extraction, cant, sectioned solids |
| **SAF for bridges** | SAF (Excel format) gaining bridge element support — simpler than IFC for pure structural data |
| **OpenBridge standard** | BuildingSmart InfraRoom working on OpenBridge Model View Definition for IFC 4.3 |

---

## 📖 Key Resources for Bridge Engineers

| Resource | URL |
|---|---|
| SOFiSTiK Bridge Design Tutorials (2026) | [docs.sofistik.com/2026/en/tutorials/bridge-design](https://docs.sofistik.com/2026/en/tutorials/bridge-design/) |
| SOFiSTiK Balanced Cantilever Tutorial | [docs.sofistik.com/2026/…/balanced-c-b.html](https://docs.sofistik.com/2026/en/tutorials/bridge-design/balanced-cantilever/balanced-c-b.html) |
| SOFiSTiK IFC Import 2026 | [docs.sofistik.com/2026/…/ifc_import.html](https://docs.sofistik.com/2026/en/fea/basic/interfaces/ifc_import.html) |
| Allplan Bridge 2024 Release Notes | [allplan.com Release Notes PDF](https://www.allplan.com/fileadmin/user_upload/countries/international/release_notes/Bridge/2024/AllplanBridgeReleaseNotes_EN-2024.pdf) |
| IfcAlignment API (IfcOpenShell) | [docs.ifcopenshell.org/…/alignment](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/alignment/index.html) |
| IFC 4.3 IfcAlignment Spec | [ifc43-docs.standards.buildingsmart.org](https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/IfcAlignment.htm) |
| OSArch IFC Alignment Wiki | [wiki.osarch.org — IFC alignment](https://wiki.osarch.org/index.php?title=IFC_-_Industry_Foundation_Classes/IFC_alignment) |
| SOFiSTiK Bridge Training | [info2.sofistik.de/en-bridge-design-training](https://info2.sofistik.de/en-bridge-design-training/) |
| Allplan Bridge Engineering Page | [allplan.com/bridge-engineering-software](https://www.allplan.com/ap_en/industry-solutions/bridge-engineering-software/) |
| IfcOpenShell GitHub | [github.com/IfcOpenShell/IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) |

---

## ✅ Quick-Start Checklist

```
□ 1. Verify Allplan Bridge version supports IFC 4.3 export (2024+)
□ 2. Export IFC from Allplan Bridge — include alignment, tendons, sections
□ 3. Open exported IFC in Bonsai/BlenderBIM to verify alignment is present
□ 4. Install ifcopenshell 0.8.x: pip install ifcopenshell
□ 5. Run extraction script — check that stations are populated (not None)
□ 6. Review materials_map and sections_map — fix unmapped entries manually
□ 7. Check tendon geometry: verify Z-offsets are within section boundaries
□ 8. Generate .dat file and open in SOFiSTiK TEDDY
□ 9. Fix any CADINP syntax errors (check TEDDY log)
□ 10. Add CSM stages, ELLA traffic loads, and AQB design manually
□ 11. Run linear analysis (ASE) first — validate forces and reactions
□ 12. Run full bridge analysis (CSM → ELLA → AQB → MAXIMA)
```

---

*Document generated: 2026-05-25 | Sources: SOFiSTiK Docs 2026, IfcOpenShell 0.8.x docs, Allplan Bridge 2024, BuildingSMART IFC 4.3*

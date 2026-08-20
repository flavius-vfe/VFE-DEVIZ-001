from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, getcontext
from math import cos, radians

getcontext().prec = 28
D = Decimal
SUPPORTED_DIAMETERS = {D(str(v)) for v in (6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32)}
GEOMETRY_TYPES = {"ROOM", "WALL", "FOUNDATION_STRIP", "SLAB", "BEAM", "COLUMN", "ROOF_GABLE", "REBAR", "STIRRUPS", "WELDED_MESH"}

def dec(value, name="valoare", *, positive=False, nonnegative=False) -> Decimal:
    try: value = D(str(value))
    except Exception as exc: raise ValueError(f"{name} trebuie să fie un număr valid.") from exc
    if positive and value <= 0: raise ValueError(f"{name} trebuie să fie mai mare decât zero.")
    if nonnegative and value < 0: raise ValueError(f"{name} nu poate fi negativă.")
    return value

def ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))

def with_waste(quantity: Decimal, waste_percent) -> Decimal:
    waste = dec(waste_percent, "Pierderile", nonnegative=True)
    return quantity * (D("1") + waste / D("100"))

def openings(data: dict) -> tuple[Decimal, Decimal]:
    area = D("0"); door_width = D("0")
    for opening in data.get("openings", []):
        width = dec(opening.get("width_m"), "Lățimea golului", positive=True)
        height = dec(opening.get("height_m"), "Înălțimea golului", positive=True)
        quantity = dec(opening.get("quantity", 1), "Numărul golurilor", positive=True)
        area += width * height * quantity
        if opening.get("type") == "DOOR": door_width += width * quantity
    return area, door_width

def room(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("length_m"),"Lungimea",positive=True); width=dec(data.get("width_m"),"Lățimea",positive=True); height=dec(data.get("height_m"),"Înălțimea",positive=True)
    perimeter=D("2")*(length+width); gross=perimeter*height; opening_area,doors=openings(data)
    if opening_area > gross: raise ValueError("Suprafața golurilor nu poate depăși suprafața brută a pereților.")
    return {"floor_area_m2":length*width,"ceiling_area_m2":length*width,"perimeter_m":perimeter,"gross_wall_area_m2":gross,"opening_area_m2":opening_area,"net_wall_area_m2":gross-opening_area,"skirting_length_m":perimeter-doors}

def wall(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("length_m"),"Lungimea",positive=True); height=dec(data.get("height_m"),"Înălțimea",positive=True); thickness=dec(data.get("thickness_m"),"Grosimea",positive=True)
    gross=length*height; opening_area,_=openings(data)
    if opening_area > gross: raise ValueError("Suprafața golurilor nu poate depăși suprafața peretelui.")
    return {"gross_area_m2":gross,"opening_area_m2":opening_area,"net_area_m2":gross-opening_area,"volume_m3":(gross-opening_area)*thickness}

def foundation(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("length_m"),"Lungimea",positive=True); ew=dec(data.get("excavation_width_m"),"Lățimea săpăturii",positive=True); ed=dec(data.get("excavation_depth_m"),"Adâncimea săpăturii",positive=True); cw=dec(data.get("concrete_width_m"),"Lățimea betonului",positive=True); ch=dec(data.get("concrete_height_m"),"Înălțimea betonului",positive=True); blind=dec(data.get("blinding_thickness_m",0),"Grosimea betonului de egalizare",nonnegative=True)
    return {"excavation_m3":length*ew*ed,"concrete_m3":length*cw*ch,"blinding_concrete_m3":length*ew*blind,"side_formwork_m2":D("2")*length*ch}

def slab(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("length_m"),"Lungimea",positive=True); width=dec(data.get("width_m"),"Lățimea",positive=True); thickness=dec(data.get("thickness_m"),"Grosimea",positive=True); area=length*width
    return {"area_m2":area,"concrete_volume_m3":area*thickness,"bottom_formwork_m2":area,"perimeter_m":D("2")*(length+width)}

def beam(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("length_m"),"Lungimea",positive=True); width=dec(data.get("width_m"),"Lățimea",positive=True); height=dec(data.get("height_m"),"Înălțimea",positive=True); quantity=dec(data.get("quantity",1),"Numărul grinzilor",positive=True); faces=set(data.get("exposed_faces",["bottom","side_left","side_right"]))
    form=D("0")
    if "bottom" in faces: form += length*width
    if "side_left" in faces: form += length*height
    if "side_right" in faces: form += length*height
    if "ends" in faces: form += D("2")*width*height
    return {"concrete_volume_m3":length*width*height*quantity,"formwork_area_m2":form*quantity}

def column(data: dict) -> dict[str, Decimal]:
    width=dec(data.get("width_m"),"Lățimea",positive=True); depth=dec(data.get("depth_m"),"Adâncimea",positive=True); height=dec(data.get("height_m"),"Înălțimea",positive=True); quantity=dec(data.get("quantity",1),"Numărul stâlpilor",positive=True)
    return {"concrete_volume_m3":width*depth*height*quantity,"formwork_area_m2":D("2")*(width+depth)*height*quantity}

def rebar(data: dict) -> dict[str, Decimal]:
    if data.get("group_type", "LONGITUDINAL") not in {"LONGITUDINAL", "DISTRIBUTION", "ADDITIONAL"}: raise ValueError("Tipul grupului de armătură nu este acceptat.")
    diameter=dec(data.get("diameter_mm"),"Diametrul",positive=True)
    if diameter not in SUPPORTED_DIAMETERS: raise ValueError("Diametrul armăturii nu este acceptat.")
    length=dec(data.get("bar_length_m"),"Lungimea barei",positive=True); quantity=dec(data.get("quantity"),"Numărul barelor",positive=True); lap=dec(data.get("lap_allowance_m",0),"Suprapunerea",nonnegative=True); hook=dec(data.get("hook_allowance_m",0),"Lungimea ciocurilor",nonnegative=True)
    total=quantity*(length+lap+hook); kgm=diameter*diameter/D("162"); base=total*kgm
    return {"kg_per_m":kgm,"total_length_m":total,"base_weight_kg":base,"total_weight_kg":with_waste(base,data.get("waste_percent",0))}

def stirrups(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("beam_length_m"),"Lungimea grinzii",positive=True); width=dec(data.get("beam_width_m"),"Lățimea grinzii",positive=True); height=dec(data.get("beam_height_m"),"Înălțimea grinzii",positive=True); cover=dec(data.get("concrete_cover_mm"),"Acoperirea cu beton",nonnegative=True)/D("1000"); diameter=dec(data.get("stirrup_diameter_mm"),"Diametrul etrierului",positive=True); spacing=dec(data.get("spacing_mm"),"Pasul etrierilor",positive=True)/D("1000"); hooks=dec(data.get("hook_length_m",0),"Lungimea ciocurilor",nonnegative=True)
    if diameter not in SUPPORTED_DIAMETERS: raise ValueError("Diametrul etrierului nu este acceptat.")
    iw=width-D("2")*cover; ih=height-D("2")*cover
    if iw <= 0 or ih <= 0: raise ValueError("Acoperirea cu beton este prea mare pentru secțiunea grinzii.")
    count=ceil_decimal(length/spacing)+1; cutting=D("2")*(iw+ih)+D("2")*hooks; total_length=D(count)*cutting; weight=total_length*diameter*diameter/D("162")
    return {"number_of_stirrups":D(count),"cutting_length_m":cutting,"total_length_m":total_length,"total_weight_kg":with_waste(weight,data.get("waste_percent",0))}

def mesh(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("coverage_length_m"),"Lungimea acoperită",positive=True); width=dec(data.get("coverage_width_m"),"Lățimea acoperită",positive=True); sl=dec(data.get("sheet_length_m"),"Lungimea foii",positive=True); sw=dec(data.get("sheet_width_m"),"Lățimea foii",positive=True); ox=dec(data.get("overlap_x_m",0),"Suprapunerea longitudinală",nonnegative=True); oy=dec(data.get("overlap_y_m",0),"Suprapunerea transversală",nonnegative=True); layers=dec(data.get("layers",1),"Numărul straturilor",positive=True); weight=dec(data.get("weight_kg_per_sheet"),"Greutatea foii",positive=True)
    if ox >= sl or oy >= sw: raise ValueError("Suprapunerea trebuie să fie mai mică decât dimensiunea foii.")
    sx=1 if length<=sl else 1+ceil_decimal((length-sl)/(sl-ox)); sy=1 if width<=sw else 1+ceil_decimal((width-sw)/(sw-oy)); sheets=D(sx*sy)*layers; sheets=with_waste(sheets,data.get("waste_percent",0)); total=D(ceil_decimal(sheets))
    return {"sheets_x":D(sx),"sheets_y":D(sy),"total_sheets":total,"total_weight_kg":total*weight}

def roof(data: dict) -> dict[str, Decimal]:
    length=dec(data.get("building_length_m"),"Lungimea clădirii",positive=True); width=dec(data.get("building_width_m"),"Lățimea clădirii",positive=True); pitch=dec(data.get("pitch_degrees"),"Panta",positive=True); eave=dec(data.get("eave_overhang_m",0),"Streașina",nonnegative=True); gable=dec(data.get("gable_overhang_m",0),"Prelungirea frontonului",nonnegative=True)
    if pitch >= D("89"): raise ValueError("Panta acoperișului trebuie să fie între 0 și 89 de grade.")
    roof_length=length+D("2")*gable; projected_width=width+D("2")*eave; cosine=D(str(cos(radians(float(pitch))))); slope=(projected_width/D("2"))/cosine
    return {"projected_area_m2":roof_length*projected_width,"slope_length_m":slope,"total_roof_surface_m2":D("2")*roof_length*slope,"ridge_length_m":roof_length,"eave_length_m":D("2")*roof_length}

CALCULATORS={"ROOM":room,"WALL":wall,"FOUNDATION_STRIP":foundation,"SLAB":slab,"BEAM":beam,"COLUMN":column,"REBAR":rebar,"STIRRUPS":stirrups,"WELDED_MESH":mesh,"ROOF_GABLE":roof}
UNITS={"floor_area_m2":"m2","ceiling_area_m2":"m2","gross_wall_area_m2":"m2","opening_area_m2":"m2","net_wall_area_m2":"m2","gross_area_m2":"m2","net_area_m2":"m2","area_m2":"m2","bottom_formwork_m2":"m2","side_formwork_m2":"m2","formwork_area_m2":"m2","projected_area_m2":"m2","total_roof_surface_m2":"m2","excavation_m3":"m3","concrete_m3":"m3","blinding_concrete_m3":"m3","volume_m3":"m3","concrete_volume_m3":"m3","base_weight_kg":"kg","total_weight_kg":"kg","perimeter_m":"ml","skirting_length_m":"ml","total_length_m":"ml","slope_length_m":"ml","ridge_length_m":"ml","eave_length_m":"ml","total_sheets":"buc","number_of_stirrups":"buc","cutting_length_m":"ml","kg_per_m":"kg"}

def calculate(geometry_type: str, data: dict) -> dict[str, Decimal]:
    if geometry_type not in CALCULATORS: raise ValueError("Tipul geometriei nu este acceptat.")
    return CALCULATORS[geometry_type](data)

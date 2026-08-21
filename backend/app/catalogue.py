from __future__ import annotations
import json
from pathlib import Path
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import WorkCategory,Material,LaborResource,WorkItem,WorkRecipe,RecipeResource
from .estimation import gross_from_net_exact

SEED_DIR=Path(__file__).resolve().parent.parent/"seeds"
def read(name): return json.loads((SEED_DIR/name).read_text(encoding="utf-8"))

def seed_catalogue(db:Session)->dict:
    cats=read("categories.json"); mats=read("materials.json")["materials"]; labor=read("labor.json")["labor"]; works=read("works.json")["works"]; recipes=read("recipes.json")["recipes"]
    for order,(code,name) in enumerate(cats["categories"]):
        row=db.scalar(select(WorkCategory).where(WorkCategory.code==code)) or WorkCategory(code=code); row.name=name; row.sort_order=order; db.add(row)
    for code,name,category,unit in mats:
        row=db.scalar(select(Material).where(Material.code==code)) or Material(code=code); row.name=name; row.category=category; row.base_unit=unit; row.description="Resursă generică independentă de comerciant."; row.attributes={"source":"STANDARD","catalogue_version":cats["catalogue_version"]}; row.active=True; db.add(row)
    for code,name,unit,rate in labor:
        row=db.scalar(select(LaborResource).where(LaborResource.code==code)) or LaborResource(code=code); row.name=name; row.unit=unit; row.rate_net=Decimal(rate); row.vat_rate=Decimal("21"); row.rate_gross=gross_from_net_exact(row.rate_net,row.vat_rate); row.active=True; db.add(row)
    db.flush(); category_names={x.code:x.name for x in db.scalars(select(WorkCategory))}
    for code,name,category,unit in works:
        row=db.scalar(select(WorkItem).where(WorkItem.code==code)) or WorkItem(code=code); row.name=name; row.category=f"{category} {category_names[category]}"; row.unit=unit; row.description="Coeficienții rețetei sunt estimări inițiale editabile, nu norme legale obligatorii."; row.active=True; db.add(row)
    db.flush(); resource_models={"MATERIAL":Material,"LABOR":LaborResource}
    for data in recipes:
        work=db.scalar(select(WorkItem).where(WorkItem.code==data["work"])); recipe=db.scalar(select(WorkRecipe).where(WorkRecipe.work_item_id==work.id,WorkRecipe.version==data["version"]))
        if recipe is None: recipe=WorkRecipe(work_item_id=work.id,version=data["version"],scope="STANDARD"); db.add(recipe); db.flush()
        if db.scalar(select(RecipeResource.id).where(RecipeResource.recipe_id==recipe.id).limit(1)) is None:
            for typ,code,quantity,waste,unit in data["resources"]:
                model=resource_models[typ]; resource=db.scalar(select(model).where(model.code==code)); db.add(RecipeResource(recipe_id=recipe.id,resource_type=typ,resource_id=resource.id,description=resource.name,unit=unit,quantity_per_unit=Decimal(quantity),waste_percent=Decimal(waste),notes="Coeficient standard inițial, editabil."))
    db.commit(); return {"catalogue_version":cats["catalogue_version"],"categories":len(cats["categories"]),"materials":len(mats),"labor":len(labor),"works":len(works),"recipes":len(recipes)}

def export_catalogue(db:Session)->dict:
    return {"schema_version":"1","catalogue_version":read("categories.json")["catalogue_version"],"categories":[{"code":x.code,"name":x.name,"sort_order":x.sort_order} for x in db.scalars(select(WorkCategory))],"resources":{"materials":[{"id":x.id,"code":x.code,"name":x.name,"category":x.category,"unit":x.base_unit,"active":x.active} for x in db.scalars(select(Material))],"labor":[{"id":x.id,"code":x.code,"name":x.name,"unit":x.unit,"rate_net":str(x.rate_net),"vat_rate":str(x.vat_rate),"active":x.active} for x in db.scalars(select(LaborResource))]},"works":[{"id":x.id,"code":x.code,"name":x.name,"category":x.category,"unit":x.unit,"description":x.description,"active":x.active} for x in db.scalars(select(WorkItem))],"recipes":[{"id":x.id,"work_item_id":x.work_item_id,"scope":x.scope,"project_id":x.project_id,"version":x.version,"resources":[{"resource_type":r.resource_type,"resource_id":r.resource_id,"description":r.description,"unit":r.unit,"quantity_per_unit":str(r.quantity_per_unit),"waste_percent":str(r.waste_percent)} for r in db.scalars(select(RecipeResource).where(RecipeResource.recipe_id==x.id))]} for x in db.scalars(select(WorkRecipe))]}

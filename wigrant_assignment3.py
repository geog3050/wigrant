def hawkid():
    return["Will Grant", "wigrant"]

import arcpy
from pathlib import Path
import csv

CLASS_FOLDER = Path("S:/2026_Fall/SEES-3050/STUDENT/wigrant/wigrant_assignment3")

DATA_FOLDER = CLASS_FOLDER / "data"
OUTPUT_FOLDER = CLASS_FOLDER / "outputs"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

# Problem 1
def prepare_data(input_fc, output_geodatabase, out_coordinate_system,
                 join_table=None, join_field=None, value_field=None):

    try:
        # Create or reuse output folder and geodatabase
        gdb = str(OUTPUT_FOLDER / output_geodatabase)
        if not arcpy.Exists(gdb):
            arcpy.management.CreateFileGDB(str(OUTPUT_FOLDER), output_geodatabase)
        arcpy.env.workspace = gdb
        # Check input feature class
        input_fc = str(input_fc)
        if not arcpy.Exists(input_fc):
            raise FileNotFoundError(f"Missing input: {input_fc}")
        desc = arcpy.Describe(input_fc)
        # Create output name using input base name
        output_name = Path(input_fc).stem
        output_fc = str(Path(gdb) / output_name)
        if arcpy.Exists(output_fc):
            raise FileExistsError(f"Output already exists: {output_fc}")
        # Project feature class
        arcpy.management.Project(
            input_fc,
            output_fc,
            out_coor_system = arcpy.SpatialReference(26916)
        )
        # Join CSV
        if join_table is not None:
            if join_field is None or value_field is None:
                raise ValueError("Provide all three join arguments.")
            if desc.shapeType != "Polygon":
                raise ValueError("Join table can only be used with polygons.")
            # Create the output table
            table_name = Path(join_table).stem
            pop_table = str(Path(gdb) / table_name)
            if arcpy.Exists(pop_table):
                raise FileExistsError(f"Table already exists: {pop_table}")
            arcpy.management.CreateTable(gdb, table_name)
            # Add fields
            arcpy.management.AddField(pop_table, join_field, "TEXT", field_length=12)
            arcpy.management.AddField(pop_table, value_field, "DOUBLE")
            # Read CSV and import records
            with open(join_table, encoding="utf-8-sig", newline="") as file:
                records = csv.DictReader(file)
                with arcpy.da.InsertCursor(pop_table, [join_field, value_field]) as cursor:
                    for row in records:
                        cursor.insertRow([row[join_field], float(row[value_field])
                        ])
            # Join population to polygons
            arcpy.management.JoinField(
                output_fc, join_field, pop_table, join_field, [value_field]
            )
        print(f"Successfully prepared: {output_fc}")
        return output_fc
    except Exception as e:
        print(f"Error preparing data: {e}")
        raise

DATA_FOLDER = Path.cwd() / "data"

prepared_bg = prepare_data(
    DATA_FOLDER / "block_groups.shp",
    "outputs.gdb",
    arcpy.SpatialReference(26916),
    DATA_FOLDER / "population.csv",
    "GEOID",
    "POP_TOTAL"
)

# Problem 2
def estimatePopulationInZone(source_polygons, population_field, study_zone,
                             output_fc):
    try:
        source_polygons = str(Path(source_polygons))
        study_zone = str(Path(study_zone))
        output_fc = str(Path(output_fc))
        # Check input datasets
        if not arcpy.Exists(source_polygons):
            raise FileNotFoundError("Source polygons not found.")
        if not arcpy.Exists(study_zone):
            raise FileNotFoundError("Study zone not found.")
        # Check geometry types
        source_desc = arcpy.Describe(source_polygons)
        zone_desc = arcpy.Describe(study_zone)
        if source_desc.shapeType != "Polygon":
            raise ValueError("Source data must contain polygons.")
        if zone_desc.shapeType != "Polygon":
            raise ValueError("Study zone must contain polygons.")
        # Check coordinate systems
        source_sr = source_desc.spatialReference
        zone_sr = zone_desc.spatialReference
        if source_sr.type != "Projected" or zone_sr.type != "Projected":
            raise ValueError("Inputs must use a projected coordinate system.")
        if source_sr.linearUnitName.lower() not in ["meter", "metre"]:
            raise ValueError("Coordinate system must use meters.")
        if source_sr.factoryCode != zone_sr.factoryCode:
            raise ValueError("Inputs must use the same coordinate system.")
        # Check population field
        fields = [f.name for f in arcpy.ListFields(source_polygons)]
        if population_field not in fields:
            raise ValueError("Population field not found.")
        # Check output name
        if arcpy.Exists(output_fc):
            raise FileExistsError(f"Output already exists: {output_fc}")
        # Create a working copy to preserve original polygons
        source_fc = str(
            Path(output_fc).parent / "source_polygons_working"
        )
        if arcpy.Exists(source_fc):
            raise FileExistsError(f"Working copy already exists: {source_fc}")
        arcpy.management.CopyFeatures(source_polygons, source_fc)
        # Calc og polygon area
        working_fields = [f.name for f in arcpy.ListFields(source_fc)]
        if "SRC_KM2" not in working_fields:
            arcpy.management.AddField(source_fc, "SRC_KM2", "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            source_fc, [["SRC_KM2", "AREA"]], area_unit="SQUARE_KILOMETERS"
        )
        arcpy.analysis.Intersect([source_fc, study_zone], output_fc, join_attributes="ALL"
        )
        # Calc overlapping area
        arcpy.management.AddField(output_fc, "PART_KM2", "DOUBLE")
        arcpy.management.AddField(output_fc, "EST_POP", "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            output_fc, [["PART_KM2", "AREA"]], area_unit="SQUARE_KILOMETERS"
        )
        fields = [population_field, "SRC_KM2", "PART_KM2", "EST_POP"]
        total_population = 0
        with arcpy.da.UpdateCursor(output_fc, fields) as rows:
            for row in rows:
                population, source_area, part_area, estimate = row
                if population is None or population < 0:
                    raise ValueError("Population must be nonnegative.")
                if source_area is None or source_area <= 0:
                    raise ValueError("Source polygon area must be positive.")
                if part_area is None or part_area < 0:
                    raise ValueError("Overlap area must be nonnegative.")
                estimate = population * (part_area / source_area)
                row[3] = estimate
                total_population += estimate
                rows.updateRow(row)
        print("Estimated population inside study zone:", total_population)
        return total_population
    except Exception as e:
        print(f"Error estimating population: {e}")
        raise

practice_gdb = OUTPUT_FOLDER / "practice.gdb"

if arcpy.Exists(str(practice_gdb)):
    arcpy.management.Delete(str(practice_gdb))

practice_polygons = prepare_data(
    DATA_FOLDER / "practice_polygons.shp",
    "practice.gdb",
    arcpy.SpatialReference(26916)
)
practice_zone = prepare_data(
    DATA_FOLDER / "practice_zone.shp",
    "practice.gdb",
    arcpy.SpatialReference(26916)
)

total = estimatePopulationInZone(practice_polygons, "POP_TOTAL", practice_zone,
    str(Path(arcpy.Describe(practice_polygons).path) / "population_overlap")
)
print(total)

# Problem 3
def summarizeLineLength(lines, polygons, polygon_id_field, output_fc):
    try:
        lines = str(Path(lines))
        polygons = str(Path(polygons))
        output_fc = str(Path(output_fc))
        # Check input datasets
        if not arcpy.Exists(lines):
            raise FileNotFoundError("Lines dataset not found.")
        if not arcpy.Exists(polygons):
            raise FileNotFoundError("Polygons dataset not found.")
        # Check geometry types
        line_desc = arcpy.Describe(lines)
        polygon_desc = arcpy.Describe(polygons)
        if line_desc.shapeType != "Polyline":
            raise ValueError("Lines input must contain line geometry.")
        if polygon_desc.shapeType != "Polygon":
            raise ValueError("Polygons input must contain polygon geometry.")
        # Check coordinate systems
        line_sr = line_desc.spatialReference
        polygon_sr = polygon_desc.spatialReference
        if line_sr.type != "Projected" or polygon_sr.type != "Projected":
            raise ValueError("Inputs must use projected coordinate systems.")
        if line_sr.linearUnitName.lower() not in ["meter", "metre"]:
            raise ValueError("Coordinate systems must use meters.")
        if line_sr.factoryCode != polygon_sr.factoryCode:
            raise ValueError("Inputs must use the same coordinate system.")
        # Check polygon ID field
        fields = [f.name for f in arcpy.ListFields(polygons)]
        if polygon_id_field not in fields:
            raise ValueError("Polygon ID field not found.")
        # Check output name
        if arcpy.Exists(output_fc):
            raise FileExistsError(f"Output already exists: {output_fc}")
        # Intersect lines with polygons
        intersect_fc = str(
            Path(output_fc).parent / (Path(output_fc).name + "_intersect")
        )
        if arcpy.Exists(intersect_fc):
            raise FileExistsError(f"Intersect output already exists: {intersect_fc}")
        arcpy.analysis.Intersect(
            [lines, polygons], intersect_fc,  join_attributes="ALL"
        )
        # Calc line lengths
        arcpy.management.AddField(intersect_fc, "LINE_KM", "DOUBLE")
        arcpy.management.CalculateGeometryAttributes(
            intersect_fc, [["LINE_KM", "LENGTH"]], length_unit="KILOMETERS"
        )
        summary_table = str(
            Path(output_fc).parent / (Path(output_fc).name + "_summary")
        )
        if arcpy.Exists(summary_table):
            raise FileExistsError(f"Summary table already exists: {summary_table}")
        arcpy.analysis.Statistics(intersect_fc, summary_table, [["LINE_KM", "SUM"]], polygon_id_field
        )
        arcpy.management.CopyFeatures(polygons, output_fc)
        arcpy.management.AddField(output_fc, "LINE_KM", "DOUBLE")
        arcpy.management.JoinField(output_fc, polygon_id_field, summary_table, polygon_id_field,["SUM_LINE_KM"]
        )
        with arcpy.da.UpdateCursor(output_fc, ["SUM_LINE_KM", "LINE_KM"]) as rows:
            for row in rows:
                row[1] = row[0] if row[0] is not None else 0
                rows.updateRow(row)
        arcpy.management.DeleteField(output_fc, "SUM_LINE_KM")
        print("Successfully summarized line lengths.")
        return output_fc
    except Exception as e:
        print(f"Error summarizing line lengths: {e}")
        raise

line_output = summarizeLineLength(
    lines=practice_lines,polygons=practice_polygons, polygon_id_field="ZONE_ID",
    output_fc=str(Path(arcpy.Describe(practice_polygons).path) / "polygon_lengths")
)
print(line_output)

with arcpy.da.SearchCursor(
    line_output,
    ["ZONE_ID", "LINE_KM"]
) as rows:
    for row in rows:
        print(row)

######################################################################
# MAKE NO CHANGES BEYOND THIS POINT.
######################################################################
if __name__ == "__main__" and hawkid()[1] == "hawkid":
    print("### Error: YOU MUST provide your HawkID in the hawkid() function.")



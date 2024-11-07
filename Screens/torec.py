import xml.etree.ElementTree as ET

# Load and parse the XML file
tree = ET.parse(r'L:\basic\divg\coreReits\Screens\multifile\NIRHTa+001.companion.ome.xml')
root = tree.getroot()
namespace = {'ome': root.tag.split('}')[0].strip('{')}

# Find the Plate element
plate = root.find('.//ome:Plate', namespace)

# Initialize values
row_naming_convention = column_naming_convention = None
columns = rows = images_per_well = None
first_axis = "column"  # Default assumption

if plate is not None:
    # Extract the Row and Column naming conventions
    row_naming_convention = plate.get('RowNamingConvention')
    column_naming_convention = plate.get('ColumnNamingConvention')
    columns = int(plate.get('Columns'))
    rows = int(plate.get('Rows'))
    
    # Determine the First Axis by examining the order of Well elements
    wells = plate.findall('.//ome:Well', namespace)
    if wells:
        first_well = wells[0]
        second_well = wells[1] if len(wells) > 1 else None
        
        if second_well is not None:
            # Compare Row and Column values between the first two wells
            first_row = int(first_well.get('Row'))
            first_col = int(first_well.get('Column'))
            second_row = int(second_well.get('Row'))
            second_col = int(second_well.get('Column'))
            
            # Check if Column increments before Row or vice versa
            if first_row == second_row and second_col > first_col:
                first_axis = "column"
            elif first_col == second_col and second_row > first_row:
                first_axis = "row"
    
    # Count images per well using the first Well
    images_per_well = len(first_well.findall('.//ome:WellSample', namespace)) if first_well else 0

# Print extracted values
print(f"RowNamingConvention: {row_naming_convention}")
print(f"ColumnNamingConvention: {column_naming_convention}")
print(f"Columns: {columns}")
print(f"Rows: {rows}")
print(f"Images per well: {images_per_well}")
print(f"First Axis: {first_axis}")

# Output these values as script_params for OMERO
script_params = {
    "First_Axis": first_axis,
    "First_Axis_Count": columns if first_axis == "column" else rows,
    "Images_Per_Well": images_per_well,
    "Row_Names": row_naming_convention,
    "Column_Names": column_naming_convention
}

print("Script parameters for OMERO:")
print(script_params)
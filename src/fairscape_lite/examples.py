from fairscape_models.rocrate import ROCrateMetadataElem
from fairscape_models.sql.conversion.construct import ConvertROCrateToSQL

with open("src/fairscape_lite/test.json", "r") as jsonfile:
    input_crate = ROCrateMetadataElem.model_validate_json(jsonfile.read())

crate_sql = ConvertROCrateToSQL(input_crate)
-- Model info structure
local generic_collections = {};
local info_struct = {};

for i = 1, studies do
    generic_collections[i] = Generic(i);
end

local info_existence_log = load_model_info(generic_collections, info_struct);

local dashboard = Dashboard();
create_operation_report(dashboard, studies, info_struct, info_existence_log, true);
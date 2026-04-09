function future_cost(i, suffix)
    local generic<const> = Generic(i or 1);
    local costs_by_category = generic:load("objcop" .. (suffix or ""));
    
    local study<const> = Study(i or 1);
    if study:is_hourly() then
        return costs_by_category:select_agent(1);
    else
        return costs_by_category:select_agent(-1);
    end
end

-- Macros
EXECUTION_MODE_OPERATION     = 0
EXECUTION_MODE_EXPANSION_IT  = 1
EXECUTION_MODE_EXPANSION_SIM = 2
LANGUAGE = "en"
PERCENT_OF_OBJ_COST = 0.2

REP_DIFF_TOL = 0.05 -- 10%

CONVERGENCE_GAP_TOL = 0.01; -- absolute value

LEGEND_MAX_CHAR = 20; -- maximum number of characters in legend before truncating with "..."

-- Setting global colors
main_global_color = { "#4E79A7", "#F28E2B", "#8CD17D", "#B6992D", "#E15759", "#76B7B2", "#FF9DA7", "#D7B5A6", "#B07AA1", "#59A14F", "#F1CE63", "#A0CBE8", "#E15759" };
light_global_color = { "#B7C9DD", "#FAD2AA", "#D1EDCB", "#E9DAA4", "#F3BCBD", "#C8E2E0", "#FFD8DC", "#EFE1DB", "#DFCAD9", "#BBDBB7", "#F9EBC1", "#D9EAF6", "#F3BCBD" };

PSR.set_global_colors(main_global_color);

-- Initialization of Advisor class
local advisor = Advisor();

-- Study dimension
studies = PSR.studies();

-----------------------------------------------------------------------------------------------
-- Useful fuctions
-----------------------------------------------------------------------------------------------
function trim(s)
    return (s:gsub("^%s*(.-)%s*$", "%1"))
end

function split(s, delimiter)
    result = {};
    for match in (s..delimiter):gmatch("(.-)"..delimiter) do
        table.insert(result, trim(match));
    end
    return result;
end

function tableFind(table, search_value)
    for _, value in ipairs(table) do
        if value == search_value then
            return true
        end
    end
    return false
end

function subrange(t, first, last)
    return table.move(t, first, last, 1, {})
end

function my_to_number(arg,default)
    if arg then
        return tonumber(arg);
    else
        return default;
    end
end

function tableContains(tbl, item) -- will be deprecated soon (next PSRIO version)
    local trim_item = trim(item);
    for _, value in ipairs(tbl) do
        -- info(trim(value))
        -- info(trim_item)
        -- info(trim(value) == trim_item)
        if trim(value) == trim_item then
            return true
        end
    end
    return false
end

function compare_agents(vec_agents_1,vec_agents_2) -- will be deprecated soon (next PSRIO version)
    local uniqueElements = {};
    for _, element in ipairs(vec_agents_1) do
        -- info(element)
        -- info(vec_agents_2)
        -- info(tableContains(vec_agents_2, element))
        -- info(uniqueElements)
        -- info(tableContains(uniqueElements, element))
        if not tableContains(vec_agents_2, element) and not tableContains(uniqueElements, element) then
            table.insert(uniqueElements, element)
        end
    end
    return uniqueElements
end

function create_zero_agents(data_2,uniqueElements) -- will be deprecated soon (next PSRIO version)
    local zero_data = data_2:aggregate_agents(BY_SUM(),"zero"):fill(0);
    local result_data = data_2;
    for _,element in ipairs(uniqueElements) do
        result_data = concatenate(result_data,zero_data:rename_agent(element));
    end
    return result_data
end

function adjust_data_for_add_categories(table_aux) -- will be deprecated soon (next PSRIO version)
    local adjusted_table = table_aux;
    for i,data_1 in ipairs(table_aux) do
        for j,data_2 in ipairs(table_aux) do
            if i ~= j then
                local agents_1 = data_1:agents();
                local agents_2 = data_2:agents();
                local unique_elements = compare_agents(agents_1,agents_2)
                if #unique_elements > 0 then
                    local adjusted_data = create_zero_agents(data_2,unique_elements)
                    adjusted_table[j] = adjusted_data;
                end
            end
        end
    end
    return adjusted_table
end

function Expression.change_currency_configuration(self,index)
    if self:loaded() then
        local study = Study(index or 1);
        local replacement = study:get_parameter("CurrencyReference","none");
        if replacement ~= "none" then
            local original_string = self:unit();
            if string.find(original_string, "k%$") then
                return self:force_unit("k"..replacement);
            elseif string.find(original_string, "$/MWh") then
                return self:force_unit(replacement .. "/MWh");
            end
        end
    end
    return self;
end

function Generic.username(self)
    local generic = Generic(1);
    local index = self:get_study_index();

    local user_name_file = generic:load_table_without_header("case_compare.metadata");

    local user_name = "";
    if #user_name_file >= index then
        user_name = user_name_file[index][1];
    else
        user_name = self:dirname();
    end
    return user_name;
end
-----------------------------------------------------------------------------------------------
-- Overloads
-----------------------------------------------------------------------------------------------

-- Temporary solution to SDDP remap executions (including typical days)
function Expression.aggregate_blocks_by_duracipu(self,i)
    local generic = Generic(i or 1);
    local duracipu = generic:load("duracipu");
    return (self * duracipu):aggregate_blocks(BY_SUM());
end

-----------------------------------------------------------------------------------------------
-- Auxiliary functions
-----------------------------------------------------------------------------------------------

function fix_conv_map_file(file_name, col_struct, study_index)

    -- Local
    local convertion_status = -1; -- -1: unsuccessful, 0: successful
    local header            = {};
    local indexes           = {};
    local input_lines       = {};
    local output_lines      = {};
    local stage_indexes     = {};
    local scenario_indexes  = {};
    
    local file_name_csv = file_name .. ".csv";
    local reader = col_struct.generic[study_index]:create_reader(file_name_csv);
    
    if(not reader:is_open()) then
        return convertion_status;
    end
   
    -- Read graph file header (first 4 lines)
    table.insert(header,reader:get_line()); 
    table.insert(header,reader:get_line());
    table.insert(header,reader:get_line());
    table.insert(header,reader:get_line());
    
    -- Iterate over remaining lines
    local counter = 0;
    while reader:good() do
        counter = counter + 1;
        table.insert(indexes, counter);
        
        local row = reader:get_line();
        table.insert(input_lines,row);
        
        -- Get stage and scenario indexes (1st and 2nd columns)
        columns          = string.gmatch(row, '([^,]+),');
        col1 = columns();
        col2 = columns();
        
        if col1 == nil or col2 == nil then
            break;
        end
        
        table.insert(stage_indexes   ,tonumber(col1));
        table.insert(scenario_indexes,tonumber(col2));
    end
    reader:close();
    
    -- Apply sorting procedure using stage and scenario indexes as criteria
    table.sort(indexes, function(a,b)
                            if stage_indexes[a] ~= nil and scenario_indexes[b] ~= nil then
                                if stage_indexes[a] == stage_indexes[b] then
                                    return scenario_indexes[a] < scenario_indexes[b];
                                elseif stage_indexes[a] < stage_indexes[b] then
                                    return true;
                                else
                                    return false;
                                end
                            end
                        end);
    
    -- Load sorted lines into array
    for _,i in ipairs(indexes) do
        table.insert(output_lines,input_lines[i]);
    end
    
    -- Write fixed file
    local writer = col_struct.generic[study_index]:create_writer(file_name_csv);
    
    local is_open = writer:is_open();
    
    if is_open then
        for iheader = 1, #header do
            writer:write_line(header[iheader]);
        end
        for iline = 1, #output_lines do
            writer:write_line(output_lines[iline]);
        end
        writer:close();
        
        convertion_status = 0;
    end

    return convertion_status;
end

function push_tab_to_tab(tab_from, tab_to)
    if #tab_from > 0 then
        tab_to:push(tab_from);
    end
end

function Tab.push_chart_to_tab(self, chart)
    if #chart > 0 then
        self:push(chart);
    end
end

function is_greater_than_zero(output)

    if not output:loaded() then
        return false;
    end 
    
    local x = output:abs():aggregate_agents(BY_SUM(), "CheckZeros"):aggregate_stages(BY_SUM()):to_list();
    if x[1] > 0.0 then
        return true;
    else
        return false;
    end
end

function load_info_file(file_name,case_index)

    -- Initialize struct
    info_struct = {{model = ""}, {user = ""}, {version = ""}, {hash = ""}, {model = ""}, {status = ""}, {infrep = ""}, {dash_name = ""}, {cloud = ""}, {exe_mode=0}, {arch = ""}, {total_nodes = 1}, {total_processes = 1}, {processing_type = ""}};

    local toml      = Generic(case_index):load_toml(file_name);
    model           = toml:get_string("model", "-");
    user            = toml:get_string("user", "-");
    version         = toml:get_string("version", "-");
    hash            = toml:get_string("hash", "-");
    status          = toml:get_string("status", "-");
    infrep          = toml:get_string("infrep", "-");
    dash_name       = toml:get_string("dash", "-");
    cloud           = toml:get_string("cloud", "-");
    exe_mode        = toml:get_integer("mode", 0);
	arch            = toml:get_string("arch", "-");
    total_nodes     = toml:get_integer("total_nodes", 1);
    total_processes = toml:get_integer("total_process", 1);
    processing_type = toml:get_string("processing_type", "-");

    info_struct.model           = model;
    info_struct.user            = user;
    info_struct.version         = version;
    info_struct.hash            = hash;
    info_struct.status          = tonumber(status);
    info_struct.infrep          = infrep;
    info_struct.dash_name       = dash_name;
    info_struct.cloud           = cloud;
    info_struct.exe_mode        = exe_mode;
	info_struct.arch            = arch;
    info_struct.total_nodes     = total_nodes;
    info_struct.total_processes = total_processes;
    info_struct.processing_type = processing_type;

    return info_struct;
end

function load_model_info(generic_cols, info_struct)
    local file_exists;
    local info_file_name = "SDDP.info";
    local existence_log = {}

    for i = 1, studies do
        -- Verify whether info file exists for each case
        file_exists = generic_cols[i]:file_exists(info_file_name);
        table.insert(existence_log,file_exists);

        -- Loading info files from each case
        if existence_log[i] then
            info_struct[i] = load_info_file(info_file_name,i);
        end
    end

    return existence_log;
end

function load_collections(col_struct, info_struct)
    for i = 1, studies do
        table.insert(col_struct.battery        , Battery(i));
        table.insert(col_struct.bus            , Bus(i));
        table.insert(col_struct.circuit        , Circuit(i));
        table.insert(col_struct.dclink         , DCLink(i));
        table.insert(col_struct.generic        , Generic(i));
        table.insert(col_struct.hydro          , Hydro(i));
        table.insert(col_struct.interconnection, Interconnection(i));
        table.insert(col_struct.power_injection, PowerInjection(i));
        table.insert(col_struct.renewable      , Renewable(i));
        table.insert(col_struct.csp            , ConcentratedSolarPower(i));
        table.insert(col_struct.study          , Study(i));
        table.insert(col_struct.system         , System(i));
        table.insert(col_struct.thermal        , Thermal(i));

        table.insert(col_struct.case_dir_list  , Generic(i):username());
    end
end

function remove_case_info(col_struct, info_struct, case_index)
    table.remove(col_struct.battery        , case_index);
    table.remove(col_struct.bus            , case_index);
    table.remove(col_struct.circuit        , case_index);
    table.insert(col_struct.dclink         , case_index);
    table.remove(col_struct.generic        , case_index);
    table.remove(col_struct.hydro          , case_index);
    table.remove(col_struct.interconnection, case_index);
    table.remove(col_struct.power_injection, case_index);
    table.remove(col_struct.renewable      , case_index);
    table.remove(col_struct.study          , case_index);
    table.remove(col_struct.system         , case_index);
    table.remove(col_struct.thermal        , case_index);

    table.remove(col_struct.case_dir_list  , case_index);

    -- Loading info files from each case
    table.remove(info_struct, case_index);
end

local function load_language()
    local language = Study(1):get_parameter("Idioma", 0);

    if language == 1 then
        return "es";
    elseif language == 2 then
        return "pt";
    else -- language == 0
        return "en";
    end
end

function Expression.select_stages_of_outputs(self)
    if self:loaded() then
        local index = self:study_index();
        local last_stage = Study(index):stages_without_buffer_years();
        if Study(index):get_parameter("NumeroAnosAdicionaisParm2",-1) == 1 then
            last_stage = Study(index):stages();
        end

        return self:select_stages(1,last_stage)
    end
    return self
end

-----------------------------------------------------------------------------------------------
-- Get language
-----------------------------------------------------------------------------------------------
LANGUAGE = load_language();

-----------------------------------------------------------------------------------------------
-- Infeasibility report function
-----------------------------------------------------------------------------------------------
function dash_infeasibility(tab,file_name,case_index)

    local inv_table = Study(case_index):load_table_without_header(file_name);

    if not inv_table or (#inv_table == 0) then
        warning("The file " .. file_name .. " was not found or is empty.");
    else
        for lin=1,#inv_table do
            local data=(inv_table[lin][1]);
            local col = 2
            local stg_concat = data;
            if not data then
                tab:push(" ");
            else
                local data_2=(inv_table[lin][col]);
                while data_2 do
                    stg_concat = stg_concat..","..data_2;
                    col = col + 1;
                    data_2=(inv_table[lin][col]);
                end
                tab:push(stg_concat);
            end
        end
    end
end
-----------------------------------------------------------------------------------------------
-- Case summary report function
-----------------------------------------------------------------------------------------------

function get_nonconv_info(col_struct, file_name, nonconv_list, nonconv_order, case_index)
    -- Loading file
    local nonconv = col_struct.generic[case_index]:load_table(file_name);

    if not nonconv or (#nonconv == 0) then
        warning("The file " .. file_name .. " was not found or is empty.");
    else
        local nonconv_size = #nonconv;
        for i = 1, nonconv_size do
            
            local key = trim(nonconv[i]["Type"]);

            local translated_label = non_convexities_labels[key]
            if translated_label == nil then
                translated_label = key;
            end

            if nonconv_list[translated_label] then
                nonconv_list[translated_label]["case_" .. case_index] = trim(nonconv[i]["Dimension"]);
            else
                table.insert(nonconv_order, translated_label);
                nonconv_list[translated_label] = {
                    ["case_" .. case_index] = trim(nonconv[i]["Dimension"])
                }
            end
        end
    end
end

function create_tab_summary(col_struct, info_struct)

    local tab = Tab(dictionary.tab_info[LANGUAGE]);
    tab:set_icon("info");

    tab:push("# " .. dictionary.case_summary[LANGUAGE]);

    local exe_status_str;

    local label = {};
    local path = {};

    local model = {};
    local user = {}
    local version = {};
    local hash = {};
    local description = {};

    for i = 1, studies do
        table.insert(label,col_struct.generic[i]:cloudname());
        table.insert(path, col_struct.generic[i]:path());

        local study = Study(i);
        table.insert(description, study:get_parameter("Descricao", ""));
    end

    local case             = dictionary.cell_case[LANGUAGE];
    local directory_name   = dictionary.cell_directory_name[LANGUAGE];
    local path_cell        = dictionary.cell_path[LANGUAGE];
    local execution_status = dictionary.cell_execution_status[LANGUAGE];
    local model            = dictionary.cell_model[LANGUAGE];
    local user             = dictionary.cell_user[LANGUAGE];
    local version          = dictionary.cell_version[LANGUAGE];
    local ID               = dictionary.cell_ID[LANGUAGE];
	local cloud_arch       = dictionary.cell_arch[LANGUAGE];
    local title            = dictionary.cell_title[LANGUAGE];
    local execution_type   = dictionary.cell_execution_type[LANGUAGE];
    local total_process    = dictionary.cell_total_processes[LANGUAGE];
    local total_nodes      = dictionary.cell_total_nodes[LANGUAGE];

	-- Execution status
    if studies == 1 then 
        tab:push("| " .. directory_name .. " | " .. path_cell .. " | " .. execution_status .. " |");
        tab:push("|:--------------:|:----:|:----------------:|");
        for i = 1, studies do
            exe_status_str = dictionary.cell_success[LANGUAGE];
            if info_struct[i].status > 0 then
                exe_status_str = "FAIL";
            end

            tab:push("| " .. label[i] .. " | " .. path[i].. " | " .. exe_status_str);
        end
    else
        tab:push("| " .. case .. " | " .. directory_name .. " | " .. path_cell .. " | " .. execution_status .. " |");
        tab:push("|:----:|:--------------:|:----:|:----------------:|");
        for i = 1, studies do
            exe_status_str = dictionary.cell_success[LANGUAGE];
            if info_struct[i].status > 0 then
                exe_status_str = "FAIL";
            end

            tab:push("| " .. i .. " | " .. label[i] .. " | " .. path[i] .. " | " .. exe_status_str);
        end
    end

	-- About the model (hash, version name...)
    tab:push("## " .. dictionary.about_model[LANGUAGE]);
    if studies == 1 then
        tab:push("| " .. model .. " | " .. user .. " | " .. version .. " | " .. ID ..  "|" .. cloud_arch .. " |");
        tab:push("|:-------:|:-------:|:-------:|:-------:|:-------:|");
        for i = 1, studies do
            tab:push("| " .. info_struct[i].model .. " | " .. info_struct[i].user .. " | " .. info_struct[i].version .. " | " .. info_struct[i].hash .. " | " .. info_struct[i].arch .. " |");
        end
    else
        tab:push("| " .. case .. " | " .. model .. " | " .. user .. " | " .. version .." | " .. ID .. "|" .. cloud_arch .. " |");
        tab:push("|:-------:|:-------:|:-------:|:-------:|:-------:|:-------:|");
        for i = 1, studies do
            tab:push("| " .. i .. " | " .. info_struct[i].model .. " | " .. info_struct[i].user .. " | " .. info_struct[i].version .. " | " .. info_struct[i].hash .. " | " .. info_struct[i].arch .. " |");
        end
    end

    -- About nodes
    tab:push("## " .. dictionary.about_nodes[LANGUAGE]);
    if studies == 1 then
        tab:push("| " .. execution_type .. " | "  .. total_nodes .. " | " .. total_process .. " |");
        tab:push("|:-----------------:|:-----------------:|:-----------------:|");
        tab:push("| " .. info_struct[1].processing_type .. " | " .. info_struct[1].total_nodes .. " | " .. info_struct[1].total_processes .. " |");

    else
        tab:push("| " .. case .. " | " .. execution_type .. " | " .. total_nodes .. " | " .. total_process .. " |");
        tab:push("|:----:|:-----------------:|:-----------------:|:-----------------:|");
        for i = 1, studies do
            tab:push("| " .. i .. " | " .. info_struct[i].processing_type .. " | " .. info_struct[i].total_nodes .. " | " .. info_struct[i].total_processes .. " |");
        end

    end



	-- Cases' titles
    tab:push("## " .. dictionary.case_title[LANGUAGE]);
    if studies == 1 then
        tab:push("| " .. title .. " |");
        tab:push("|:-----------:|");
        for i = 1, studies do
            tab:push("| " .. description[i] .. " | ");
        end
    else
        tab:push("| " .. case .. " | " .. title .. " |");
        tab:push("|:----:|:-----------:|");
        for i = 1, studies do
            tab:push("| " .. i .. " | " .. description[i] .. " | ");
        end
    end

	-- Horizon, resolution, execution options
    tab:push("## " .. dictionary.hor_resol_exec[LANGUAGE]);

    local header_string              = "| " .. dictionary.cell_case_parameters[LANGUAGE];
    local lower_header_string        = "|---------------";
    local exe_type_string            = "| " .. dictionary.cell_execution_type[LANGUAGE];
    local case_type_string           = "| " .. dictionary.cell_case_type[LANGUAGE];
    local nstg_string                = "| " .. dictionary.cell_stages[LANGUAGE];
    local ini_date_string            = "| " .. dictionary.cell_ini_date[LANGUAGE];
    local plc_resolution             = "| " .. dictionary.cell_plc_resolution[LANGUAGE];
    local sim_resolution             = "| " .. dictionary.cell_sim_resolution[LANGUAGE];
    local nforw_string               = "| " .. dictionary.cell_fwd_series[LANGUAGE];
    local nback_string               = "| " .. dictionary.cell_bwd_series[LANGUAGE];
    local sim_series                 = "| " .. dictionary.cell_sim_series[LANGUAGE];
    local hrep_string                = "| " .. dictionary.cell_hourly_representation[LANGUAGE];
    local netrep_string              = "| " .. dictionary.cell_network_representation[LANGUAGE];
    local typday_string              = "| " .. dictionary.cell_typicalday_representation[LANGUAGE];
    local loss_representation_string = "| " .. dictionary.cell_loss_representation[LANGUAGE];
    local type_of_inflows            = "| " .. dictionary.inflows_type[LANGUAGE];
    local inflows_initial_year       = "| " .. dictionary.inflows_initial_year[LANGUAGE];
    local hrep_val   = {};
    local netrep_val = {};
    local typday_val = {};
    local loss_repr  = {};
    local inflow_repr  = {};
    local inf_initial_year  = {};
    local exe_type   = {};
    local case_type  = {};

    local show_net_data = false;

    for i = 1, studies do
        -- Number of stages
        local number_of_stages = col_struct.study[i]:stages_without_buffer_years();
        if col_struct.study[i]:get_parameter("NumeroAnosAdicionaisParm2",-1) == 1 then
            number_of_stages = col_struct.study[i]:stages();
        end

        -- type of execution
        exe_type[i] = dictionary.cell_policy[LANGUAGE];
        local number_of_blocks = col_struct.study[i]:get_parameter("NumberBlocks", -1);
        local policy_number_of_blocks = number_of_blocks .. " " .. dictionary.cell_blocks[LANGUAGE]
        local resolution_of_simulation = policy_number_of_blocks;
        local number_of_openings = tostring(col_struct.study[i]:openings());
        local number_of_forwards = tostring(col_struct.study[i]:scenarios());
        local mumber_of_simulated_series = number_of_forwards;
        if col_struct.study[i]:get_parameter("Objetivo", -100) == 2 then
            policy_number_of_blocks = " - ";
            number_of_openings = " - ";
            number_of_forwards = " - ";
            exe_type[i] = dictionary.cell_simulation[LANGUAGE];
        end
        if col_struct.study[i]:get_parameter("Objetivo", -100) == -2 then
            policy_number_of_blocks = " - ";
            number_of_openings = " - ";
            number_of_forwards = " - ";
            exe_type[i] = dictionary.cell_commercial_simulation[LANGUAGE];
        end
        exe_type_string = exe_type_string .. " | " .. exe_type[i];

        if col_struct.study[i]:is_hourly() then
            resolution_of_simulation = dictionary.cell_hourly[LANGUAGE];
        end

        if col_struct.study[i]:get_parameter("Series_Simular", 0) == 1 then
            mumber_of_simulated_series = #(col_struct.study[i]:selected_scenarios());
        end
        -- type of resolution
        case_type[i] = dictionary.cell_monthly[LANGUAGE];
        if col_struct.study[i]:stage_type() == 1 then
            case_type[i] = dictionary.cell_weekly[LANGUAGE];
        end
        case_type_string = case_type_string .. " | " .. case_type[i];


        header_string = header_string             .. " | " .. col_struct.case_dir_list[i];
        lower_header_string = lower_header_string .. "|-----------";

        nstg_string      = nstg_string      .. " | " .. tostring(number_of_stages);
        ini_date_string  = ini_date_string  .. " | " .. tostring(col_struct.study[i]:initial_stage()) .. "/" 
                                                     .. tostring(col_struct.study[i]:initial_year());
        plc_resolution   = plc_resolution   .. " | " .. policy_number_of_blocks;
        sim_resolution   = sim_resolution   .. " | " .. resolution_of_simulation;
        nforw_string     = nforw_string     .. " | " .. number_of_forwards;
        nback_string     = nback_string     .. " | " .. number_of_openings;
        sim_series       = sim_series       .. " | " .. mumber_of_simulated_series;

        hrep_val[i] = "❌";
        if col_struct.study[i]:get_parameter("SIMH", -1) == 2 then
            hrep_val[i] = "✔️";
        end
        hrep_string = hrep_string .. " | " .. hrep_val[i];

        netrep_val[i] = "❌";
        if col_struct.study[i]:get_parameter("Rede", -1) == 1 then
            netrep_val[i] = "✔️";
            if not show_net_data then
                show_net_data = true
            end
        end
        netrep_string = netrep_string .. " | " .. netrep_val[i];

        typday_val[i] = "❌";
        if col_struct.study[i]:get_parameter("TDAY", -1) == 1 then
            typday_val[i] = "✔️";
        end
        typday_string = typday_string .. " | " .. typday_val[i];

        loss_repr[i] = "❌";
        if col_struct.study[i]:get_parameter("Perdas", -1) == 1 then
            loss_repr[i] = "✔️";
        end
        loss_representation_string = loss_representation_string .. " | " .. loss_repr[i];

        local sddp_inflow_type = col_struct.study[i]:get_parameter("Vazoes", -1);
        if sddp_inflow_type > 0 then
            if sddp_inflow_type == 1 then
                inflow_repr[i] = dictionary.arp[LANGUAGE];
            elseif sddp_inflow_type == 2 then
                inflow_repr[i] = dictionary.historical[LANGUAGE];
            elseif sddp_inflow_type == 3 then
                inflow_repr[i] = dictionary.external_f_b[LANGUAGE];
            elseif sddp_inflow_type == 4 then
                inflow_repr[i] = dictionary.external_f[LANGUAGE];
            else
                inflow_repr[i] = "-";
            end
            
        end
        type_of_inflows = type_of_inflows .. " | " .. inflow_repr[i];

        inf_initial_year[i] = col_struct.study[i]:get_parameter("Ano_Inicial_Hidro", 0);
        inflows_initial_year = inflows_initial_year .. " | " .. inf_initial_year[i];

    end
    header_string                    = header_string              .. "|";
    lower_header_string              = lower_header_string        .. "|";
    exe_type_string                  = exe_type_string            .. "|";
    case_type_string                 = case_type_string           .. "|";
    nstg_string                      = nstg_string                .. "|";
    ini_date_string                  = ini_date_string            .. "|";
    plc_resolution                   = plc_resolution             .. "|";
    sim_resolution                   = sim_resolution             .. "|";
    nforw_string                     = nforw_string               .. "|";
    nback_string                     = nback_string               .. "|";
    sim_series                       = sim_series                 .. "|";
    hrep_string                      = hrep_string                .. "|";
    netrep_string                    = netrep_string              .. "|";
    typday_string                    = typday_string              .. "|";
    loss_representation_string       = loss_representation_string .. "|";
    type_of_inflows                  = type_of_inflows .. "|";
    inflows_initial_year             = inflows_initial_year .. "|";

    tab:push(header_string);
    tab:push(lower_header_string);
    tab:push(exe_type_string);
    tab:push(case_type_string);
    tab:push(nstg_string);
    tab:push(ini_date_string);
    tab:push(plc_resolution);
    tab:push(sim_resolution);
    tab:push(nforw_string);
    tab:push(nback_string);
    tab:push(sim_series);
    tab:push(hrep_string);
    tab:push(netrep_string);
    tab:push(typday_string);
    tab:push(loss_representation_string);
    tab:push(type_of_inflows);
    tab:push(inflows_initial_year);

    tab:push("## " .. dictionary.dimentions[LANGUAGE]);

    local sys_string        = "| " .. dictionary.cell_system[LANGUAGE];
    local battery_string    = "| " .. dictionary.cell_batteries[LANGUAGE];
    local bus_string        = "| " .. dictionary.cell_buses[LANGUAGE];
    local ac_circuit_string = "| " .. dictionary.cell_ac_circuits[LANGUAGE];
    local dc_circuit_string = "| " .. dictionary.cell_dc_circuits[LANGUAGE];
    local interc_string     = "| " .. dictionary.cell_interconnections[LANGUAGE];
    local hydro_string      = "| " .. dictionary.cell_hydro_plants[LANGUAGE];
    local pinj_string       = "| " .. dictionary.cell_power_injections[LANGUAGE];
    local renw_w_string     = "| " .. dictionary.cell_renewable_wind[LANGUAGE];
    local renw_s_string     = "| " .. dictionary.cell_renewable_solar[LANGUAGE];
    local renw_sh_string    = "| " .. dictionary.cell_renewable_small_hydro[LANGUAGE];
    local renw_csp_string   = "| " .. dictionary.cell_renewable_csp[LANGUAGE];
    local renw_oth_string   = "| " .. dictionary.cell_renewable_other[LANGUAGE];
    local thermal_string    = "| " .. dictionary.cell_thermal_plants[LANGUAGE];

    for i = 1, studies do
        sys_string = sys_string             .. " | " .. tostring(#col_struct.system[i]:labels());
        battery_string = battery_string     .. " | " .. tostring(#col_struct.battery[i]:labels());

        if show_net_data and studies <= 1 then
            bus_string        = bus_string        .. " | " .. tostring(#col_struct.bus[i]:labels());
            ac_circuit_string = ac_circuit_string .. " | " .. tostring(#col_struct.circuit[i]:labels());
            dc_circuit_string = dc_circuit_string .. " | " .. tostring(#col_struct.dclink[i]:labels());
        else
            interc_string = interc_string   .. " | " .. tostring(#col_struct.interconnection[i]:labels());
        end

        hydro_string    = hydro_string    .. " | " .. tostring(#col_struct.hydro[i]:labels());
        pinj_string     = pinj_string     .. " | " .. tostring(#col_struct.power_injection[i]:labels());

        total_renw = #col_struct.renewable[i]:labels();
        renw_wind  = col_struct.renewable[i].tech_type:select_agents(col_struct.renewable[i].tech_type:eq(1)):agents_size();
        renw_solar = col_struct.renewable[i].tech_type:select_agents(col_struct.renewable[i].tech_type:eq(2)):agents_size();
        renw_sh    = col_struct.renewable[i].tech_type:select_agents(col_struct.renewable[i].tech_type:eq(4)):agents_size();
        renw_oth   = total_renw - renw_wind - renw_solar - renw_sh;

        renw_csp = #col_struct.csp[i]:labels();

        renw_sh_string  = renw_sh_string  .. " | " .. tostring(renw_sh);
        renw_w_string   = renw_w_string   .. " | " .. tostring(renw_wind);
        renw_s_string   = renw_s_string   .. " | " .. tostring(renw_solar);
        renw_csp_string = renw_csp_string .. " | " .. tostring(renw_csp);
        renw_oth_string = renw_oth_string .. " | " .. tostring(renw_oth);

        thermal_string  = thermal_string  .. " | " .. tostring(#col_struct.thermal[i]:labels());
    end

    tab:push(header_string);
    tab:push(lower_header_string);
    tab:push(sys_string);
    tab:push(hydro_string);
    tab:push(thermal_string);
    tab:push(renw_w_string);
    tab:push(renw_s_string);
    tab:push(renw_sh_string)
    tab:push(renw_oth_string);
    tab:push(renw_csp_string);
    tab:push(battery_string);
    tab:push(pinj_string);
    if show_net_data and studies <= 1 then
        tab:push(bus_string);
        tab:push(ac_circuit_string);
        tab:push(dc_circuit_string);
    else
        tab:push(interc_string);
    end

    -- Non-convexities dimension report


    local nconv_file_name = "nonconvrep.csv";
    local nonconv_list = {};
    local nonconv_order = {};

    for i = 1, studies do
        get_nonconv_info(col_struct,nconv_file_name,nonconv_list, nonconv_order,i);
    end

    if #nonconv_order then
        tab:push("## " .. dictionary.non_convexities[LANGUAGE]);

        header_string       = "| " .. dictionary.cell_non_convexities_type[LANGUAGE];
        lower_header_string = "|-------------------";

        for i = 1, studies do
            if studies == 1 then
                header_string       = header_string       .. "| " .. dictionary.cell_count[LANGUAGE];
                lower_header_string = lower_header_string .. "|-------------------";
            else
                header_string       = header_string       .. "|" .. col_struct.case_dir_list[i];
                lower_header_string = lower_header_string .. "|-------------------";
            end
        end

        tab:push(header_string .. "|");
        tab:push(lower_header_string .. "|");

        for _, non_convexity_name in ipairs(nonconv_order) do
            local non_convexity_line = "| " .. non_convexity_name;
            for j = 1, studies do
                if nonconv_list[non_convexity_name]["case_" .. j] then
                    non_convexity_line = non_convexity_line .. " | " .. nonconv_list[non_convexity_name]["case_" .. j];
                else
                    non_convexity_line = non_convexity_line .. " | - ";
                end
            end
            tab:push(non_convexity_line .. "|");
        end
        
    end

    return tab;
end

-----------------------------------------------------------------------------------------------
-- Inflow energy report function
-----------------------------------------------------------------------------------------------

function create_inflow_energy(col_struct)
    local tab = Tab(dictionary.tab_inflow_energy[LANGUAGE]);

    local inferg = {};
    for i = 1, studies do
        inferg[i] = col_struct.generic[i]:load("sddp_dashboard_input_enaflu");
    end

    -- Color vectors
    local chart = Chart(dictionary.inflow_energy[LANGUAGE]);
    if studies > 1 then
        for i = 1, studies do

            -- Confidence interval
            chart:add_area_range(inferg[i]:select_agent(1):add_prefix(col_struct.case_dir_list[i] .. " - "), inferg[i]:select_agent(3), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { light_global_color[i], light_global_color[i] }, legendSizeLimit = LEGEND_MAX_CHAR });
            chart:add_line(inferg[i]:select_agent(2):add_prefix(col_struct.case_dir_list[i] .. " - "), { legendSizeLimit = LEGEND_MAX_CHAR }); -- average
        end
    else
        -- Confidence interval
        chart:add_area_range(inferg[1]:select_agent(1), inferg[1]:select_agent(3), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { light_global_color[1], light_global_color[1] }, legendSizeLimit = LEGEND_MAX_CHAR });
        chart:add_line(inferg[1]:select_agent(2), { legendSizeLimit = LEGEND_MAX_CHAR }); -- average
    end

    if #chart > 0 then
        tab:push(chart);
    end

    return tab;
end

-----------------------------------------------------------------------------------------------
-- Policy report functions
-----------------------------------------------------------------------------------------------

function get_conv_file_info(col_struct, file_name, pol_struct, file_names, case_index)
    -- Loading file
    local sddppol = col_struct.generic[case_index]:load_table(file_name);

    if not sddppol or (#sddppol == 0) then
        warning("The file " .. file_name .. " was not found or is empty.");
    else
        for i = 1, #sddppol do
            local system = trim(sddppol[i]["System"]);
            if system == "INTEGRATED" then
                system = dictionary.integrated[LANGUAGE];
            end
            local file_name = sddppol[i]["FileNames"];
            file_name = string.sub(file_name, 1, #file_name - 4);

            local horizon = sddppol[i]["InitialHorizon"] .. " - " .. sddppol[i]["FinalHorizon"];
            if file_name then
                if pol_struct[file_name] then
                    table.insert(pol_struct[file_name]["Cases"], case_index);
                else
                    table.insert(file_names, file_name);
                    pol_struct[file_name] = {
                        ["Cases"] = {case_index},
                        ["System"] = system,
                        ["Horizon"] = horizon
                    }
                end
            end
        end
    end
end

function Tab.draw_simularion_cost(self,col_struct, aux_data, chart, case_index)
    -- Get operation mode parameter
    local oper_mode =  col_struct.study[case_index]:get_parameter("Opcion", -1); -- 1=AIS; 2=COO; 3=INT;
    local rol_horiz =  col_struct.study[case_index]:get_parameter("RHRZ", 0);
    local num_syste = #col_struct.system[case_index]:labels();

    local has_results_for_add_years = col_struct.study[case_index]:get_parameter("NumeroAnosAdicionaisParm2",-1) == 1;

    -- If there is only one FCF file in the case and no rolling horizons, print final simulation cost as columns
    if (rol_horiz == 0 and (num_syste == 1 or oper_mode == 3)) then

        local objcop = col_struct.generic[case_index]:load("objcop");
        local discount_rate = require("sddp/discount_rate")(1);

        local immediate_cost;
        local future_cost_age;
        if col_struct.study[case_index]:get_parameter("SIMH", -1) == 2 then -- Hourly model writes objcop with different columns
            if not has_results_for_add_years then
                future_cost_age = objcop:select_agent(1):aggregate_scenarios(BY_AVERAGE());
            end

            -- Remove first column(Future cost) of hourly objcop
            immediate_cost = (objcop:remove_agent(1) / discount_rate):aggregate_agents(BY_SUM(), "Immediate cost"):aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM()):to_list()[1];
        else
            -- Select total cost and future cost agents
            local total_cost_age = objcop:select_agent(1):aggregate_scenarios(BY_AVERAGE());
            future_cost_age = objcop:select_agent(-1):aggregate_scenarios(BY_AVERAGE());

            -- Calculating total cost as sum of immediate costs per stage
            immediate_cost = ((total_cost_age - future_cost_age) / discount_rate):aggregate_stages(BY_SUM()):rename_agent("Total cost"):to_list()[1];
        end

        if not has_results_for_add_years then
            local fcf_last_stage_index = future_cost_age:last_stage();
            local fcf_last_stage_cost  = future_cost_age:select_stage(fcf_last_stage_index):to_list()[1];
            local last_stage_disc      = discount_rate:select_stage(fcf_last_stage_index):to_list()[1];

            immediate_cost = immediate_cost + fcf_last_stage_cost / last_stage_disc;
        end

        -- Take expression and use it as mask for "final_sim_cost"

        -- Deviation error
        local zsup = aux_data:select_agent(10);
        local last_zsup = zsup:to_list()[zsup:stages()];
        if last_zsup and immediate_cost then
            local rel_diff = (immediate_cost - last_zsup)/immediate_cost;
            if rel_diff > REP_DIFF_TOL or -rel_diff < -REP_DIFF_TOL then
                self:push("**"..dictionary.warning[LANGUAGE].."**");
                self:push(dictionary.deviation_error[1][LANGUAGE] .. string.format("%.1f",100*rel_diff) .. dictionary.deviation_error[2][LANGUAGE]);
                self:push(dictionary.deviation_error[3][LANGUAGE]);
            
                advisor:push_warning("simulation_cost");
            end
        end

        chart:add_line(aux_data:select_agent(1):fill(immediate_cost):rename_agent(dictionary.final_simulation[LANGUAGE]), 
                                { colors = { "#D37295" }, xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR })

        self:push(chart);

        self:push("**" ..dictionary.additional_years_mensage[LANGUAGE].."**");
        self:push("* **"..dictionary.final_simulation[LANGUAGE].."**: "..dictionary.final_simulation_mensage[LANGUAGE]);
        self:push("* **Zsup (IC + FCF)**: "..dictionary.zsup_mensage[LANGUAGE]);

    end
end

function get_convergence_map_status(col_struct, file_list, conv_status, case_index)
    local convertion_status = {};
    for i, file in ipairs(file_list) do
        -- Rewrite file
        local status = fix_conv_map_file(file,col_struct,case_index);
        table.insert(convertion_status,status);
        
        -- Load file
        local conv_map_file = col_struct.generic[case_index]:load(file);
        conv_status[i] = conv_map_file; -- Convergence status
    end
    
    for i = 1, #convertion_status do
        info("Convergence map rewrite status" .. tostring(convertion_status[i]));
    end
    
    return convertion_status;
end

function make_convergence_graphs(dashboard, conv_age, systems, horizon)
    for i, conv in ipairs(conv_age) do
        local chart = Chart(dictionary.convergence[LANGUAGE] .. " | " .. dictionary.system[LANGUAGE] .. " : " .. systems[i] .. " | " .. dictionary.horizon[LANGUAGE] .. " : " .. horizon[i]);
        chart:add_area_range(conv:select_agents({ 2 }), conv:select_agents({ 4 }), { colors = { "#ACD98D", "#ACD98D" }, xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR }); -- Confidence interval
        chart:add_line(conv:select_agents({ 1 }), { colors = { "#3CB7CC" }, xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR }); -- Zinf
        chart:add_line(conv:select_agents({ 3 }), { colors = { "#32A251" }, xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR }); -- Zsup
        dashboard:push(chart);
    end
end

function make_added_cuts_graphs(dashboard, cuts_age, systems, horizon)
    for i, cuts in ipairs(cuts_age) do
        local chart = Chart(dictionary.number_of_added_cut[LANGUAGE] .. " | " .. dictionary.system[LANGUAGE] .. " : " .. systems[i] .. dictionary.horizon[LANGUAGE] .. " : " .. horizon[i]);
        chart:add_column(cuts:select_agents({ 1 }), { xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR }); -- Opt
        chart:add_column(cuts:select_agents({ 2 }), { xAllowDecimals = false, legendSizeLimit = LEGEND_MAX_CHAR }); -- Feas
        dashboard:push(chart);
    end
end

function calculate_number_of_systems(sys_vec)
    local sys_name = sys_vec[1];
    local counter = 1;
    for i, name in ipairs(sys_vec) do
        if (sys_name ~= name) then
            counter = counter + 1;
            sys_name = name
        end
    end

    return counter;
end

-----------------------------------------------------------------------------------------------
-- Heatmap report functions
-----------------------------------------------------------------------------------------------

function create_penalty_proportion_graph(tab, col_struct, i)
    local output_name  = "sddppenp";
    local report_title = dictionary.violation_penalties[LANGUAGE];
    local penp = col_struct.generic[i]:force_load(output_name);

    if not penp:loaded() then
        info(output_name .. " could not be loaded. ".. "'" .. report_title .. "'" .. "report will not be displayed");
        return
    end

    local chart = Chart(report_title .. " (%)");
    chart:add_heatmap_series(penp, { yLabel = dictionary.cell_scenarios[LANGUAGE], xLabel = dictionary.cell_stage[LANGUAGE], showInLegend = false, stops = { { 0.0, "#4E79A7" }, { 0.5, "#FBEEB3" }, { 1.0, "#C64B3E" } }, stopsMin = 0.0, stopsMax = 100.0, legendSizeLimit = LEGEND_MAX_CHAR });
    tab:push(chart);
end

function create_conv_map_graph(tab, file_name, col_struct, i)
    local conv_map = col_struct.generic[i]:force_load(file_name);
    local report_title = dictionary.convergence_map[LANGUAGE];

    if not conv_map:loaded() then
        info(file_name .. " could not be loaded. ".. "'" .. report_title .. "'" .. "report will not be displayed");
        return
    end

    local options = {
        yLabel = dictionary.iteration[LANGUAGE],
        xLabel = dictionary.cell_stages[LANGUAGE],
        showInLegend = false,
        stopsMin = 0,
        stopsMax = 2,
        dataClasses = {
            { color = "#C64B3E", from = -0.5, to = 0.5, name = "not converged" },
            { color = "#4E79A7", from =  0.5, to = 1.5, name = "converged"     },
            { color = "#FBEEB3", from =  1.5, to = 2.5, name = "warning"       }
        }, 
        legendSizeLimit = LEGEND_MAX_CHAR
    };

    local chart = Chart(report_title);
    chart:add_heatmap(conv_map,options);
    tab:push(chart);
end

function create_hourly_sol_status_graph(tab, col_struct, i)
    local output_name  = "hrstat";
    local report_title = dictionary.solution_status[LANGUAGE];
    local status = col_struct.generic[i]:load(output_name);

    if not status:loaded() then
        info(output_name .. " output could not be loaded. ".. "'" .. report_title .. "'" .. "report will not be displayed");
        return
    end

    local options = {
    yLabel = "Scenario",
    xLabel = dictionary.cell_stages[LANGUAGE],
    showInLegend = false,
    stopsMin = 0,
    stopsMax = 3,
    dataClasses = {
                  { color = "#8ACE7E", to = 0          , name = "Optimal solution" },
                  { color = "#4E79A7", from = 1, to = 2, name = "Feasible solution"},
                  { color = "#FBEEB3", from = 3        , name = "Relaxed solution" },
                  { color = "#C64B3E", from = 2, to = 3, name = "No solution"      }
                  },
    legendSizeLimit = LEGEND_MAX_CHAR
    };
    

    local chart = Chart(report_title);
    chart:add_heatmap(status,options);
    tab:push(chart);

    if status:remove_zeros():loaded() then
        advisor:push_warning("mip_convergence");
    end
end

function create_mipgap_graph(tab, col_struct, i)
    local output_name  = "mipgap";
    local report_title = dictionary.mip_gap[LANGUAGE];
    local mip_gap = col_struct.generic[i]:load(output_name);

    if not mip_gap:loaded() then
        info(output_name .. " output could not be loaded. ".. "'" .. report_title .. "'" .. "report will not be displayed");
        return
    else
        -- Check if any mip problem was solved in the simulation
        mip_gap_check = mip_gap:aggregate_scenarios(BY_MIN()):aggregate_stages(BY_MIN()):to_list()[1];
        if mip_gap_check < 0 then
            info(output_name .. ": invalid MIP Gaps found. Assumed no MIP problem was solved. The report will not be displayed");
            return
        end
    end

    local options = {
    yLabel = dictionary.cell_scenarios[LANGUAGE],
    xLabel = dictionary.cell_stages[LANGUAGE],
    showInLegend = false,
    stops = {{ 0.0, "#4E79A7" }, { 0.5, "#FBEEB3" }, { 1.0, "#C64B3E" }}, 
    stopsMin = 0.0, 
    stopsMax = 100.0,
    legendSizeLimit = LEGEND_MAX_CHAR
    };

    local chart = Chart(report_title);
    chart:add_heatmap(mip_gap,options);
    
    tab:push(chart);
end

-- Execution times per scenario (dispersion)
function create_exe_timer_per_scen(tab, col_struct, i)
    local extime_chart;
    local output_name  = "extime";
    local extime = col_struct.generic[i]:load(output_name):aggregate_agents(BY_SUM(), "total"):save_cache();

    if not extime:loaded() then
        info(output_name .. " output could not be loaded. 'Dispersion of execution times per scenario' report will not be displayed");
        return
    end
    
    local extime_disp = concatenate(extime:aggregate_scenarios(BY_MIN()):rename_agent("MIN"), extime:aggregate_scenarios(BY_AVERAGE()):rename_agent(dictionary.cell_average[LANGUAGE]), extime:aggregate_scenarios(BY_MAX()):rename_agent("MAX")):save_cache();
    if is_greater_than_zero(extime_disp) then
        local unit = "hour";
        local extime_disp_data = extime_disp:aggregate_scenarios(BY_MAX()):aggregate_stages(BY_MAX());

        if extime_disp_data:loaded() then
            local extime_disp_data_list = extime_disp_data:to_list()[1];
            if extime_disp_data_list < 1.0 then
                unit = "ms";
            elseif extime_disp_data_list < 3600.0 then
                unit = "s";
            end
        end

        extime_chart = Chart(dictionary.dispersion_of_time[LANGUAGE]);
        extime_chart:add_area_range(extime_disp:select_agent("MIN"):convert(unit),
                                    extime_disp:select_agent("MAX"):convert(unit),
                                    { xUnit = dictionary.cell_stage[LANGUAGE], colors = { "#EA6B73", "#EA6B73" }, legendSizeLimit = LEGEND_MAX_CHAR }); -- Confidence interval
        extime_chart:add_line(extime_disp:select_agent(dictionary.cell_average[LANGUAGE]):convert(unit),
                              { xUnit = dictionary.cell_stages[LANGUAGE], colors = { "#F02720" }, legendSizeLimit = LEGEND_MAX_CHAR });                  -- Average

        if #extime_chart > 0 then
            tab:push(extime_chart);
        end
    end
end

function create_pol_report(col_struct)
    local tab = Tab(dictionary.tab_policy[LANGUAGE]);

    local total_cost_age;
    local future_cost_age;
    local immediate_cost;
    local fcf_last_stage_cost;
    local rel_diff;

    local pol_struct = {};
    local file_names = {};
    local total_iter = 0;
    local aux_data;
    local convm_file_list = {};

    local conv_data         = {};
    local cuts_data         = {};
    local time_data         = {};
    local conv_status       = {};
    local convertion_status = {};

    local conv_file;

    local has_results_for_add_years;
    local zsup_is_visible = true;

    
    -- -- Convergence map report
    -- get_conv_file_info(col_struct, "sddpconvm.csv", convm_file_list, systems, horizon, 1);
    -- convertion_status = get_convergence_map_status(col_struct, convm_file_list, conv_status, 1);
    -- for i = 1, #convertion_status do
    --     if not convertion_status[i] then
    --         error("Error converting convergence map file " .. convm_file_list[i]);
    --     end
    -- end
    
    -- Convergence report
    local pol_file = "sddppol.csv";
    for i = 1, studies do
        get_conv_file_info(col_struct, pol_file, pol_struct, file_names, i);
    end

    if #file_names < 1 then
        tab:push("### " .. dictionary.error_load_sddppol[LANGUAGE]);
    end

    -- Creating policy report
    for _, file in ipairs(file_names) do
        local system = pol_struct[file]["System"];
        local horizon = pol_struct[file]["Horizon"];
        local pol_studies = pol_struct[file]["Cases"];

        tab:push("## " .. dictionary.system[LANGUAGE] .. ": " .. system .. " | " .. dictionary.horizon[LANGUAGE] .. ": " .. horizon);

        local chart_conv      = Chart(dictionary.convergence[LANGUAGE]);
        local chart_cut_opt   = Chart(dictionary.new_cut_per_iteration_optimality[LANGUAGE]);
        local chart_cut_feas  = Chart(dictionary.new_cut_per_iteration_feasibility[LANGUAGE]);
        local chart_policy_simulation  = Chart(dictionary.policy_simulation[LANGUAGE]);
        chart_conv:horizontal_legend();
        chart_cut_opt:horizontal_legend();
        chart_cut_feas:horizontal_legend();
        chart_policy_simulation:horizontal_legend();

        for _,std in ipairs(pol_studies) do

            local prefix = "";
            if studies > 1 then
                prefix = col_struct.case_dir_list[std] .. " - ";
            end

            local conv_file = col_struct.generic[std]:force_load(file);
            total_iter = conv_file:last_stage();
            aux_data = conv_file;

            local aux_vector = {};
            for i = 1, total_iter do
                table.insert(aux_vector, tostring(i));
            end

            if conv_file:loaded() then
                local lb_str = dictionary.lower_bound[LANGUAGE];
                local ub_str = dictionary.upper_bound[LANGUAGE];
                local tol_str = dictionary.tolerance[LANGUAGE];
                local conv_age = conv_file:select_agents({ 1, 2, 3, 4 }); -- Zinf        ,Zsup - Tol  ,Zsup        ,Zsup + Tol
                local cuts_opt = conv_file:select_agents({5}):stages_to_agents():rename_agents(aux_vector);
                local cuts_feas = conv_file:select_agents({6}):stages_to_agents():rename_agents(aux_vector);

                -- Confidence interval
                chart_conv:add_area_range(conv_age:select_agents({ 2 }):rename_agent("(" .. prefix .. ub_str .. " - " .. tol_str .. ")"), 
                                          conv_age:select_agents({ 4 }):rename_agent("(" .. prefix .. ub_str .. " + " .. tol_str .. ")"), 
                                          { colors = { light_global_color[std],
                                            light_global_color[std] },
                                            xUnit = dictionary.iteration[LANGUAGE],
                                            xAllowDecimals = false,
                                            showInLegend = true,
                                            legendSizeLimit = LEGEND_MAX_CHAR });

                chart_policy_simulation:add_area_range(conv_age:select_agents({ 2 }):rename_agent("(" .. prefix .. ub_str .. " - " .. tol_str .. ")"), 
                                                       conv_age:select_agents({ 4 }):rename_agent("(" .. prefix .. ub_str .. " + " .. tol_str .. ")"), 
                                                       { colors = { light_global_color[std],
                                                       light_global_color[std] },
                                                       xUnit = dictionary.iteration[LANGUAGE],
                                                       xAllowDecimals = false,
                                                       showInLegend = true,
                                                       legendSizeLimit = LEGEND_MAX_CHAR });
                -- Zsup
                chart_conv:add_line(conv_age:select_agents({ 3 }):rename_agent(prefix .. " " .. ub_str),
                                    { colors = { main_global_color[std] }, xAllowDecimals = false, visible = zsup_is_visible, legendSizeLimit = LEGEND_MAX_CHAR });

                chart_policy_simulation:add_line(conv_age:select_agents({ 3 }):rename_agent(prefix .. " " .. ub_str),
                                    { colors = { main_global_color[std] }, xAllowDecimals = false, visible = zsup_is_visible, legendSizeLimit = LEGEND_MAX_CHAR });
                -- Zinf
                chart_conv:add_line(conv_age:select_agents({ 1 }):rename_agent(prefix .. " " .. lb_str),
                                    { colors = { main_global_color[std] }, xAllowDecimals = false, dashStyle = "dash", legendSizeLimit = LEGEND_MAX_CHAR }); -- Zinf

                -- Cuts - optimality
                chart_cut_opt:add_categories(cuts_opt,col_struct.case_dir_list[std],
                                        { colors = { main_global_color[std] }, xUnit = dictionary.iteration[LANGUAGE], xAllowDecimals = false, showInLegend = studies > 1, legendSizeLimit = LEGEND_MAX_CHAR });

                -- Cuts - feasibility
                if is_greater_than_zero(cuts_feas) then
                    chart_cut_feas:add_categories(cuts_feas,col_struct.case_dir_list[std],
                                             { colors = { main_global_color[std] }, xUnit = dictionary.iteration[LANGUAGE], xAllowDecimals = false, showInLegend = studies > 1, legendSizeLimit = LEGEND_MAX_CHAR });
                end

                -- Validation
                if studies > 1 then
                    local zinf_final     = tonumber(conv_age:select_agents({ 1 }):select_stage(total_iter):to_list()[1]);
                    local zsup_tol_final = tonumber(conv_age:select_agents({ 2 }):select_stage(total_iter):to_list()[1]);
                    if zinf_final and zsup_tol_final then
                        local diff = zsup_tol_final - zinf_final;
                        if (diff > 0) then
                            if diff > CONVERGENCE_GAP_TOL then
                                local sugestions = {};
                                -- For stochastic cases, add the increase number of forwards series additional message
                                if (Study():get_series_forward() > 1) then
                                    table.insert(sugestions, 'FORW');
                                end
                                advisor:push_warning("convergence_gap",1, sugestions);
                            end
                        else
                            -- to_do: negative gap msg
                        end
                    end
                end
            else
                tab:push("#### ⚠️ " .. dictionary.error_load_sddppol_files[1][LANGUAGE] .. "case " .. col_struct.case_dir_list[std] .. " " .. file .. ".csv" .. dictionary.error_load_sddppol_files[2][LANGUAGE]);
            end


            -----------------------------------------------------------------------------------------------------------
            -- Convergence map
            -----------------------------------------------------------------------------------------------------------
            -- create_conv_map_graph(tab, convm_file_list[i], col_struct, 1);
        end

        if #chart_conv > 0 then
            tab:push(chart_conv);
            if studies == 1 then
                tab:draw_simularion_cost(col_struct, aux_data, chart_policy_simulation, 1);
            end
        end
        if #chart_cut_opt > 0 then
            tab:push(chart_cut_opt);
        end
        if #chart_cut_feas > 0 then
            tab:push(chart_cut_feas);
        end
    end

    return tab;
end

function Tab.final_cost_table(self, col_struct)
    local discount_rate = require("sddp/discount_rate");

    self:push("## " .. dictionary.final_cost[LANGUAGE]);

    self:push("| " .. dictionary.cell_case[LANGUAGE] .. " | " .. dictionary.cell_average_total_cost[LANGUAGE] .. " | " .. dictionary.cell_std_total_cost[LANGUAGE] .." | ".. dictionary.cell_min_total_cost[LANGUAGE] .. " | " .. dictionary.cell_max_total_cost[LANGUAGE] .. " |");
    self:push("|:-:|:-:|:-:|:-:|:-:|");
    for i = 1, studies do

        local ime_cost = require("sddp/costs")(i);
        local fut_cost = future_cost(i);
        if ime_cost:loaded() then
            
            local study_discount_rate = discount_rate(i):select_stages_of_outputs();
            local cost = ime_cost / study_discount_rate;

            local obj_cost = cost:aggregate_agents(BY_SUM(), "Total cost"):aggregate_stages(BY_SUM()):save_cache();
            local future_cost = fut_cost:aggregate_stages(BY_LAST_VALUE()) / study_discount_rate:aggregate_stages(BY_LAST_VALUE());

            local total_cost = obj_cost + future_cost;

            if total_cost:loaded() then
                local average_cost = total_cost:aggregate_scenarios(BY_AVERAGE()):to_list()[1];
                local minimum_cost = total_cost:aggregate_scenarios(BY_MIN()):to_list()[1];
                local maximum_cost = total_cost:aggregate_scenarios(BY_MAX()):to_list()[1];
                local std_cost = total_cost:aggregate_scenarios(BY_STDDEV()):to_list()[1];

                local replacement = col_struct.study[i]:get_parameter("CurrencyReference","k$");

                self:push("| " .. col_struct.case_dir_list[i] .. " | " .. replacement .. " " .. string.format("%.2f", average_cost) .. " | " .. replacement .. " " .. string.format("%.2f", std_cost) .. " | " .. replacement .. " " .. string.format("%.2f", minimum_cost) .. " | " .. replacement .. " " .. string.format("%.2f", maximum_cost) .. " |");
            else
                warn("Total cost not loaded")
            end
        end
    end
end
-----------------------------------------------------------------------------------------------
-- Simulation objetive function cost terms report function
-----------------------------------------------------------------------------------------------

function create_sim_report(col_struct)
    local tab = Tab(dictionary.tab_simulation[LANGUAGE]);

    local costs;
    local costs_agg;
    local exe_times;

    tab:final_cost_table(col_struct);
    
    local cost_chart    = Chart(dictionary.breakdown_cost_time[LANGUAGE]);
    local revenue_chart = Chart(dictionary.breakdown_revenue_time[LANGUAGE]);

    local objcop = require("sddp/costs");
    local discount_rate = require("sddp/discount_rate");

    if studies > 1 then
        local aux_table = {};
        for i = 1, studies do
            costs = objcop(i) / discount_rate(i):select_stages_of_outputs();
            -- sddp_dashboard_cost_tot
            costs_agg = costs:aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM()):remove_zeros();
            table.insert(aux_table,costs_agg);
        end
        local adjusted_table = adjust_data_for_add_categories(aux_table);  -- will be deprecated soon (next PSRIO version)
        local agents_order = adjusted_table[1]:agents();
        for i = 1, studies do
            cost_chart:horizontal_legend();
            cost_chart:add_column_categories(adjusted_table[i]:reorder_agents(agents_order):change_currency_configuration(i), col_struct.case_dir_list[i], {legendSizeLimit = LEGEND_MAX_CHAR});
        end
    else
        costs = objcop() / discount_rate():select_stages_of_outputs();
        costs_agg = costs:aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM()):remove_zeros():save_cache();

        if is_greater_than_zero(costs_agg) then
            local obj_cost    = max(costs_agg, 0):remove_zeros();
            local obj_revenue = min(costs_agg, 0):remove_zeros();

            local total_obj_cost  = my_to_number(obj_cost:aggregate_agents(BY_SUM(),"Total cost"):to_list()[1],0.0);
            local pen_obj_cost = my_to_number(obj_cost:select_agents_by_regex("(Pen:)(.*)"):aggregate_agents(BY_SUM(),"Pen costs"):to_list()[1],0.0);

            if total_obj_cost * PERCENT_OF_OBJ_COST <= pen_obj_cost then
                advisor:push_warning("obj_costs");
            end

            if obj_cost:loaded() then
                cost_chart:add_pie(obj_cost:change_currency_configuration(), {colors = main_global_color, legendSizeLimit = LEGEND_MAX_CHAR});

                --time = TimeSeries();
                --time:add(obj_cost:change_currency_configuration());
                -- time:add(obj_cost:rename_agents({"nome1", "nome2"...}):change_currency_configuration());
                --time:save("obj_cost");
                obj_cost:save("cost", {csv=true});
            end

            if obj_revenue:loaded() then
                revenue_chart:add_pie(obj_revenue:abs():change_currency_configuration(), {colors = main_global_color, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            
        end
    end

    if #cost_chart > 0 then
        tab:push(cost_chart);
    end

    if #revenue_chart > 0 then
        tab:push(revenue_chart);
    end

    -- Add stage-wise cost reports
    create_costs_and_revs(col_struct,tab);
    
    -- Heatmap after the pizza graph in dashboard
    if studies == 1 then
        -- Creating simulation heatmap graphics
        if col_struct.study[1]:get_parameter("SIMH", -1) == 2 then
            create_hourly_sol_status_graph(tab, col_struct, 1);
        end
        
        -- MIP Gap heat map
        create_mipgap_graph(tab, col_struct, 1);

        create_penalty_proportion_graph(tab, col_struct, 1);
    end

    return tab;
end

-----------------------------------------------------------------------------------------------
-- Execution times report function
-----------------------------------------------------------------------------------------------

function create_times_report(col_struct)
    local tab = Tab(dictionary.execution_times[LANGUAGE]);

    ---------
    -- Policy
    ---------
    local pol_struct = {};
    local file_names = {};
    local systems = {};
    local horizon = {};
    
    local conv_data         = {};
    local cuts_data         = {};
    local time_data         = {};
    local conv_status       = {};
    
   -- Convergence report
   local pol_file = "sddppol.csv";
   for i = 1, studies do
       get_conv_file_info(col_struct, pol_file, pol_struct, file_names, i);
   end
   if #file_names < 1 then
       info(dictionary.error_load_sddppol_times[LANGUAGE]);
   end

   -- Creating policy report
   for _, file in ipairs(file_names) do
       local system = pol_struct[file]["System"];
       local horizon = pol_struct[file]["Horizon"];
       local pol_studies = pol_struct[file]["Cases"];

       tab:push("## " .. dictionary.system[LANGUAGE] .. ": " .. system .. " | " .. dictionary.horizon[LANGUAGE] .. ": " .. horizon);

       local chart_time_forw = Chart(dictionary.forward_time[LANGUAGE]);
       local chart_time_back = Chart(dictionary.backward_time[LANGUAGE]);
       local chart_exe_pol = Chart(dictionary.exe_pol_times[LANGUAGE]);
       chart_time_forw:horizontal_legend();
       chart_time_back:horizontal_legend();
       chart_exe_pol:horizontal_legend();

       for i,std in ipairs(pol_studies) do
            local conv_file = col_struct.generic[std]:force_load(file);
            local total_iter = conv_file:last_stage();
            local aux_vector = {};
            for i = 1, total_iter do
                table.insert(aux_vector, tostring(i));
            end

            local time_forw = conv_file:select_agents({ 7 }):stages_to_agents():rename_agents(aux_vector);
            local time_back = conv_file:select_agents({ 8 }):stages_to_agents():rename_agents(aux_vector);

            if conv_file:loaded() then
                -- Execution time - forward
                chart_time_forw:add_categories(time_forw, col_struct.case_dir_list[std], { xUnit = dictionary.iteration[LANGUAGE], 
                                                                                       yUnit = "s", 
                                                                                       xAllowDecimals = false, 
                                                                                       showInLegend = studies > 1,
                                                                                       legendSizeLimit = LEGEND_MAX_CHAR });

                -- Execution time - backward
                chart_time_back:add_categories(time_back, col_struct.case_dir_list[std], { xUnit = dictionary.iteration[LANGUAGE], 
                                                                                       yUnit = "s", 
                                                                                       xAllowDecimals = false, 
                                                                                       showInLegend = studies > 1,
                                                                                       legendSizeLimit = LEGEND_MAX_CHAR });
            else
                info("Comparing cases have different policy horizons! Policy will only contain the main case data.");
            end

            local exe_times = col_struct.generic[std]:force_load("sddptimes");
            if conv_file:loaded() then
                chart_exe_pol:add_categories(exe_times:select_agent(2),col_struct.case_dir_list[std], {showInLegend = studies > 1, legendSizeLimit = LEGEND_MAX_CHAR});
            end
        end

        if #chart_exe_pol > 0 then
            tab:push(chart_exe_pol);
        end

        if #chart_time_forw > 0 then
            tab:push(chart_time_forw);
        end

        if #chart_time_back > 0 then
            tab:push(chart_time_back);
        end
    end
    
    -------------
    -- Simulation
    -------------
    tab:push("## " .. dictionary.tab_simulation[LANGUAGE]);
    
    if studies > 1 then
        local chart_exe_sim = Chart(dictionary.exe_sim_times[LANGUAGE]);
        chart_exe_sim:horizontal_legend();

        for istudy = 1, studies do
            -- Execution times
            local exe_times = col_struct.generic[istudy]:load("sddptimes");
            chart_exe_sim:add_column(exe_times:select_agent(1):rename_agent(col_struct.case_dir_list[istudy]), {legendSizeLimit = LEGEND_MAX_CHAR});
        end
        
        if #chart_exe_sim > 0 then
           tab:push(chart_exe_sim);
        end

    else
        local chart_exe_sim = Chart(dictionary.exe_sim_times[LANGUAGE]);
        
        -- Simulation execution times
        local exe_times = col_struct.generic[1]:load("sddptimes");
        chart_exe_sim:add_column(exe_times:select_agent(1), {showInLegend = false, legendSizeLimit = LEGEND_MAX_CHAR});
        
        if #chart_exe_sim > 0 then
           tab:push(chart_exe_sim);
        end
        
        -- Execution times per scenario
        if col_struct.study[1]:get_parameter("SCEN", 0) == 0 then -- SDDP scenarios does not have execution times per scenario
            create_exe_timer_per_scen(tab, col_struct, 1);
        end
    end
    
    return tab;
end 

-----------------------------------------------------------------------------------------------
-- Simulation costs report function
-----------------------------------------------------------------------------------------------

function create_costs_and_revs(col_struct, tab)

    local chart = Chart(dictionary.disp_of_operation_cost[LANGUAGE]);
    chart:horizontal_legend();
    local chart_avg = Chart(dictionary.avg_operation_cost[LANGUAGE]);
    chart_avg:horizontal_legend();

    for i = 1, studies do
        local objcop = require("sddp/costs");
        local discount_rate = require("sddp/discount_rate");
        local costs = (max(objcop(i), 0) / discount_rate(i):select_stages_of_outputs()):save_cache();

        -- sddp_dashboard_cost_tot
        if studies == 1 then
            costs:remove_zeros():save("sddp_dashboard_cost_tot");
        end

        local costs_agg = costs:aggregate_agents(BY_SUM(), "Total cost");
        local disp = concatenate(costs_agg:aggregate_scenarios(BY_PERCENTILE(10)):rename_agent("P10"), costs_agg:aggregate_scenarios(BY_AVERAGE()):rename_agent(dictionary.cell_average[LANGUAGE]), costs_agg:aggregate_scenarios(BY_PERCENTILE(90)):rename_agent("P90")):save_cache();

        if studies > 1 then
            if is_greater_than_zero(disp) then
                chart:add_area_range(disp:select_agent(1):add_prefix(col_struct.case_dir_list[i] .. " - "):change_currency_configuration(i), disp:select_agent(3):change_currency_configuration(i), { xUnit=dictionary.cell_stage[LANGUAGE], colors = light_global_color[i], legendSizeLimit = LEGEND_MAX_CHAR }); -- Confidence interval
                chart:add_line(disp:select_agent(2):add_prefix(col_struct.case_dir_list[i] .. " - "):change_currency_configuration(i),{xUnit=dictionary.cell_stage[LANGUAGE], colors = {main_global_color[i]}, legendSizeLimit = LEGEND_MAX_CHAR }); -- Average
            end
        else
            if is_greater_than_zero(disp) then
                chart:add_area_range(disp:select_agent(1):change_currency_configuration(i), disp:select_agent(3):change_currency_configuration(), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { "#EA6B73", "#EA6B73" }, legendSizeLimit = LEGEND_MAX_CHAR }); -- Confidence interval
                chart:add_line(disp:select_agent(2):change_currency_configuration(), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { "#F02720" }, legendSizeLimit = LEGEND_MAX_CHAR }); -- Average
            end
        end

        -- sddp_dashboard_cost_avg
        local costs_avg = costs:aggregate_scenarios(BY_AVERAGE()):remove_zeros();
        if studies == 1 and is_greater_than_zero(costs_avg) then
            chart_avg:add_column_stacking(costs_avg:change_currency_configuration(),{xUnit=dictionary.cell_stage[LANGUAGE], legendSizeLimit = LEGEND_MAX_CHAR});
        end
    end

    if #chart_avg > 0 then
        tab:push(chart_avg);
    end

    if #chart > 0 then
        tab:push(chart);
    end
    
    return;
end

-----------------------------------------------------------------------------------------------
-- Marginal cost report function
-----------------------------------------------------------------------------------------------

function create_marg_costs(col_struct)
    local tab = Tab(dictionary.tab_cmo[LANGUAGE]);

    local cmg = {};
    local cmg_aggsum;
    local cmg_aggyear;

    local sys = {};
    for i = 1, studies do
        sys[i] = col_struct.system[i];
    end

    for i = 1, studies do
        cmg[i] = sys[i]:load("cmgdem");
    end

    -- Marginal cost aggregated by average
    tab:push("## " .. dictionary.annual_cmo[LANGUAGE]);
    if studies > 1 then
        local system_data = {};
        local system_unit = {};
        for i = 1, studies do
            cmg_aggyear = cmg[i]:aggregate_blocks_by_duracipu(i):aggregate_stages_weighted(BY_AVERAGE(), col_struct.study[i].hours:select_stages_of_outputs(), Profile.PER_YEAR):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), Collection.SYSTEM):save_cache();

            for _,system in ipairs(cmg_aggyear:agents()) do
                local cmgdem_data = cmg_aggyear:select_agent(system):rename_agent(col_struct.case_dir_list[i]):change_currency_configuration(i);
                table.insert(system_unit, cmgdem_data:unit());
                if system_data[system] then
                    table.insert(system_data[system], cmgdem_data);
                else
                    system_data[system] = {cmgdem_data};
                end
            end
        end
        
        local count_sys = 1;
        for system, data in pairs(system_data) do
            local chart = Chart(system);

            -- Add marginal costs outputs
            for _,individual_data in ipairs(data) do
                chart:add_column(individual_data:force_unit(system_unit[count_sys]), {legendSizeLimit = LEGEND_MAX_CHAR});-- Annual Marg. cost
            end
            -- chart:add_column(concatenate(data):force_unit(system_unit[count_sys])); 
            tab:push(chart);
            count_sys = count_sys + 1;
        end
    else
        local chart = Chart();
        cmg_aggyear = cmg[1]:aggregate_blocks_by_duracipu():aggregate_stages_weighted(BY_AVERAGE(), col_struct.study[1].hours:select_stages_of_outputs(), Profile.PER_YEAR):aggregate_scenarios(BY_AVERAGE());
        chart:add_column(cmg_aggyear:change_currency_configuration(), { xUnit=dictionary.cell_year[LANGUAGE], legendSizeLimit = LEGEND_MAX_CHAR });
        tab:push(chart);
    end

    tab:push("## " .. dictionary.stg_cmo[LANGUAGE]);
    if studies > 1 then
        local agents = cmg[1]:agents();
        for _, agent in ipairs(agents) do
            local chart = Chart(agent);
            local aux_tab = {};
            for j = 1, studies do
                cmg_aggsum = cmg[j]:aggregate_blocks_by_duracipu(j):aggregate_scenarios(BY_AVERAGE());
                local cmg_aggsum_agents = cmg_aggsum:select_agent(agent):rename_agent(col_struct.case_dir_list[j]);
               
                chart:add_line(cmg_aggsum_agents:change_currency_configuration(j),{xUnit=dictionary.cell_stage[LANGUAGE], legendSizeLimit = LEGEND_MAX_CHAR});
            end
            tab:push(chart);
        end
    else
        local chart = Chart();
        cmg_aggsum = cmg[1]:aggregate_blocks_by_duracipu():aggregate_scenarios(BY_AVERAGE());
        chart:add_column(cmg_aggsum:change_currency_configuration(),{xUnit=dictionary.cell_stage[LANGUAGE], legendSizeLimit = LEGEND_MAX_CHAR, colors = main_global_color});
        tab:push(chart);
    end

    -- Area range marginal cost chart
    show_sto_rep = false;
    for istudy = 1, studies do
        if col_struct.study[istudy]:scenarios() > 1 then
            show_sto_rep = true;
            break;
        end 
    end

    if show_sto_rep then 
        tab:push("## " .. dictionary.stg_cmo_sto[LANGUAGE]);
        local systems = col_struct.system[1]:labels(); -- First case sets base agents
        for i,system in ipairs(systems) do
            local chart = Chart(system);
            for istudy = 1, studies do
            
                
                local cmg_agg = cmg[istudy]:aggregate_blocks_by_duracipu():select_agents({system}):save_cache();
	    
                local disp = concatenate(cmg_agg:aggregate_scenarios(BY_PERCENTILE(10)):rename_agent("P10"),
                                         cmg_agg:aggregate_scenarios(BY_AVERAGE()):rename_agent(dictionary.cell_average[LANGUAGE]),
                                         cmg_agg:aggregate_scenarios(BY_PERCENTILE(90)):rename_agent("P90")):save_cache();
	    
                if studies > 1 then
                    chart:add_area_range(disp:select_agent(1):add_prefix(col_struct.case_dir_list[istudy] .. " - "):change_currency_configuration(), -- Area range
                                         disp:select_agent(3):change_currency_configuration(),
                                         {xUnit = dictionary.cell_stage[LANGUAGE],
                                         colors = { light_global_color[istudy], light_global_color[istudy] },
                                        legendSizeLimit = LEGEND_MAX_CHAR });
                    chart:add_line(disp:select_agent(2):add_prefix(col_struct.case_dir_list[istudy] .. " - "):change_currency_configuration(), {legendSizeLimit = LEGEND_MAX_CHAR}); -- Average
                
                else
                    chart:add_area_range(disp:select_agent(1):change_currency_configuration(), -- Area range
                                         disp:select_agent(3):change_currency_configuration(),
                                         {xUnit = dictionary.cell_stage[LANGUAGE],
                                         colors = { light_global_color[istudy], light_global_color[istudy] },
                                         legendSizeLimit = LEGEND_MAX_CHAR });
                    chart:add_line(disp:select_agent(2):change_currency_configuration(), {legendSizeLimit = LEGEND_MAX_CHAR}); -- Average
                end
            end
            tab:push(chart);
        end
    end
    
    return tab;
end

-----------------------------------------------------------------------------------------------
-- Generation report function
-----------------------------------------------------------------------------------------------

function create_gen_report(col_struct)
    local tab = Tab(dictionary.tab_generation[LANGUAGE]);

    -- Color preferences
    if studies == 1 then
        color_hydro = '#4E79A7';
        color_thermal = '#F28E2B';
        color_renw_other = '#7a5950';
        color_wind = '#8CD17D';
        color_solar = '#F1CE63';
        color_small_hydro = '#A0CBE8';
        color_csp = '#70AD47';
        color_battery = '#4bc9b2';
        color_deficit = '#000000';
        color_pinj = '#BAB0AC';
    end

    local total_hydro_gen;
    local total_batt_gen;
    local total_deficit;
    local total_pot_inj;
    local total_other_renw_gen;
    local total_wind_gen;
    local total_solar_gen;
    local total_small_hydro_gen;
    local total_csp_gen;
    local total_thermal_gen;

    local total_hydro_gen_age;
    local total_batt_gen_age;
    local total_deficit_age;
    local total_pot_inj_age;
    local total_other_renw_gen_age;
    local total_wind_gen_age;
    local total_solar_gen_age;
    local total_small_hydro_gen_age;
    local total_thermal_gen_age;
    local total_csp_gen_age;

    local hydro_agent_name;
    local thermal_agent_name;
    local battery_agent_name;
    local deficit_agent_name;
    local pinj_agent_name;
    local renw_ot_agent_name;
    local renw_wind_agent_name;
    local renw_solar_agent_name;
    local renw_shydro_agent_name;
    local renw_csp_agent_name;

    local hydro_report_name;
    local thermal_report_name;
    local battery_report_name;
    local deficit_report_name;
    local pinj_report_name;

    local renw_ot_report_name;
    local renw_wind_report_name;
    local renw_solar_report_name;
    local renw_shydro_report_name;

    local gerter = {};
    local gerhid = {};
    local gergnd = {};
    local gercsp = {};
    local wind = {};
    local solar = {};
    local gerbat = {};
    local potinj = {};
    local defcit = {};

    -- Loading generations files
    for i = 1, studies do

        gerter[i] = col_struct.thermal[i]:load("gerter"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
        gerhid[i] = col_struct.hydro[i]:load("gerhid"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
        gergnd[i] = col_struct.renewable[i]:load("gergnd"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
        gercsp[i] = col_struct.csp[i]:load("cspgen"):convert("GWh"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
        gerbat[i] = col_struct.battery[i]:load("gerbat"):convert("GWh"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache(); -- Explicitly converting to GWh
        potinj[i] = col_struct.power_injection[i]:load("powinj"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
        defcit[i] = col_struct.system[i]:load("defcit"):select_stages_of_outputs():aggregate_blocks():aggregate_scenarios(BY_AVERAGE()):save_cache();
    end

    if studies > 1 then
        chart_tot_gerhid     = Chart(dictionary.total_hydro[LANGUAGE]);
        chart_tot_sml_hid    = Chart(dictionary.total_small_hydro[LANGUAGE]);
        chart_tot_gerter     = Chart(dictionary.total_thermal[LANGUAGE]);
        chart_tot_other_renw = Chart(dictionary.total_renewable_other[LANGUAGE]);
        chart_tot_renw_wind  = Chart(dictionary.total_renewable_wind[LANGUAGE]);
        chart_tot_renw_solar = Chart(dictionary.total_renewable_solar[LANGUAGE]);
        chart_tot_renw_shyd  = Chart(dictionary.total_renewable_small_hydro[LANGUAGE]);
        chart_tot_renw_csp   = Chart(dictionary.total_renewable_csp[LANGUAGE]);
        chart_tot_gerbat     = Chart(dictionary.total_battery[LANGUAGE]);
        chart_tot_potinj     = Chart(dictionary.total_power_injection[LANGUAGE]);
        chart_tot_defcit     = Chart(dictionary.total_deficit[LANGUAGE]);
    else
        chart = Chart("");
    end

    -- Total generation report
    for i = 1, studies do

        if studies > 1 then
            total_hydro_gen_age       = col_struct.case_dir_list[i];
            total_batt_gen_age        = col_struct.case_dir_list[i];
            total_deficit_age         = col_struct.case_dir_list[i];
            total_pot_inj_age         = col_struct.case_dir_list[i];
            total_other_renw_gen_age  = col_struct.case_dir_list[i];
            total_wind_gen_age        = col_struct.case_dir_list[i];
            total_solar_gen_age       = col_struct.case_dir_list[i];
            total_small_hydro_gen_age = col_struct.case_dir_list[i];
            total_thermal_gen_age     = col_struct.case_dir_list[i];
            total_csp_gen_age         = col_struct.case_dir_list[i];
        else
            total_hydro_gen_age       = "Hydro";
            total_batt_gen_age        = "Battery";
            total_deficit_age         = "Deficit";
            total_pot_inj_age         = "P. Inj.";
            total_other_renw_gen_age  = "Renewable - Other tech.";
            total_wind_gen_age        = "Renewable - Wind";
            total_solar_gen_age       = "Renewable - Solar";
            total_small_hydro_gen_age = "Renewable - Small hydro";
            total_thermal_gen_age     = "Thermal";
            total_csp_gen_age         = "Renewable - CSP";
        end

        -- Data processing
        total_hydro_gen = gerhid[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_hydro_gen_age);
        total_batt_gen  = gerbat[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_batt_gen_age);
        total_deficit   = defcit[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_deficit_age);
        total_pot_inj   = potinj[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_pot_inj_age);

        -- Renewable generation is broken into 3 types
        local wind_agents  = col_struct.renewable[i].tech_type:eq(1):remove_zeros():agents();
        local solar_agents = col_struct.renewable[i].tech_type:eq(2):remove_zeros():agents();
        local small_hydro_agents = col_struct.renewable[i].tech_type:eq(4):remove_zeros():agents();

        total_other_renw_gen  = gergnd[i]:remove_agents(wind_agents)
                                         :remove_agents(solar_agents)
                                         :remove_agents(small_hydro_agents);

        total_other_renw_gen  = total_other_renw_gen:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_other_renw_gen_age);
        total_wind_gen        = gergnd[i]:select_agents(wind_agents):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_wind_gen_age);
        total_solar_gen       = gergnd[i]:select_agents(solar_agents):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_solar_gen_age);
        total_small_hydro_gen = gergnd[i]:select_agents(small_hydro_agents):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_small_hydro_gen_age);
        total_csp_gen         = gercsp[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_csp_gen_age);
        total_thermal_gen = gerter[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):aggregate_agents(BY_SUM(), total_thermal_gen_age);

        if studies > 1 then
            if total_hydro_gen:loaded() then
                chart_tot_gerhid:add_column(total_hydro_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_hydro }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_thermal_gen:loaded() then
                chart_tot_gerter:add_column(total_thermal_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_thermal }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_other_renw_gen:loaded() then
                chart_tot_other_renw:add_column(total_other_renw_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_renw_other }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_wind_gen:loaded() then
                chart_tot_renw_wind:add_column(total_wind_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_wind }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_solar_gen:loaded() then
                chart_tot_renw_solar:add_column(total_solar_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_solar }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_small_hydro_gen:loaded() then
                chart_tot_renw_shyd:add_column(total_small_hydro_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_small_hydro }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_csp_gen:loaded() then
                chart_tot_renw_csp:add_column(total_csp_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_csp }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_batt_gen:loaded() then
                chart_tot_gerbat:add_column(total_batt_gen, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_battery }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_pot_inj:loaded() then
                chart_tot_potinj:add_column(total_pot_inj, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_pinj }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
            if total_deficit:loaded() then
                chart_tot_defcit:add_column(total_deficit, { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_deficit }, legendSizeLimit = LEGEND_MAX_CHAR});
            end
        else
            local colors_vector = {};
            local total_vector = {};
            if total_thermal_gen:loaded() then
                table.insert(colors_vector, color_thermal);
                table.insert(total_vector, total_thermal_gen);
            end
            if total_hydro_gen:loaded() then
                table.insert(colors_vector, color_hydro);
                table.insert(total_vector, total_hydro_gen);
            end
            if total_wind_gen:loaded() then
                table.insert(colors_vector, color_wind);
                table.insert(total_vector, total_wind_gen);
            end
            if total_solar_gen:loaded() then
                table.insert(colors_vector, color_solar);
                table.insert(total_vector, total_solar_gen);
            end
            if total_small_hydro_gen:loaded() then
                table.insert(colors_vector, color_small_hydro);
                table.insert(total_vector, total_small_hydro_gen);
            end
            if total_csp_gen:loaded() then
                table.insert(colors_vector, color_csp);
                table.insert(total_vector, total_csp_gen);
            end
            if total_other_renw_gen:loaded() then
                table.insert(colors_vector, color_renw_other);
                table.insert(total_vector, total_other_renw_gen);
            end
            if total_batt_gen:loaded() then
                table.insert(colors_vector, color_battery);
                table.insert(total_vector, total_batt_gen);
            end
            if total_pot_inj:loaded() then
                table.insert(colors_vector, color_pinj);
                table.insert(total_vector, total_pot_inj);
            end
            if total_deficit:loaded() then
                table.insert(colors_vector, color_deficit);
                table.insert(total_vector, total_deficit);
            end
            local total_generation = concatenate(total_vector);
            chart:add_area_stacking(total_generation, {xUnit=dictionary.cell_stage[LANGUAGE], colors = colors_vector, legendSizeLimit = LEGEND_MAX_CHAR});
        end
    end

    tab:push("## ".. dictionary.total_generation[LANGUAGE]);
    if studies > 1 then
        if #chart_tot_gerhid > 0 then
            tab:push(chart_tot_gerhid);
        end
        if #chart_tot_gerter > 0 then
            tab:push(chart_tot_gerter);
        end
        if #chart_tot_other_renw > 0 then
            tab:push(chart_tot_other_renw);
        end
        if #chart_tot_renw_wind > 0 then
            tab:push(chart_tot_renw_wind);
        end
        if #chart_tot_renw_solar > 0 then
            tab:push(chart_tot_renw_solar);
        end
        if #chart_tot_renw_shyd > 0 then
            tab:push(chart_tot_renw_shyd);
        end
        if #chart_tot_renw_csp > 0 then
            tab:push(chart_tot_renw_csp);
        end
        if #chart_tot_gerbat > 0 then
            tab:push(chart_tot_gerbat);
        end
        if #chart_tot_potinj > 0 then
            tab:push(chart_tot_potinj);
        end
        if #chart_tot_defcit > 0 then
            tab:push(chart_tot_defcit);
        end
    else
        tab:push(chart);
    end

    -- Name initialization
    hydro_report_name   = dictionary.total_hydro[LANGUAGE];
    thermal_report_name = dictionary.total_thermal[LANGUAGE];
    battery_report_name = dictionary.total_battery[LANGUAGE];
    deficit_report_name = dictionary.total_deficit[LANGUAGE];
    pinj_report_name    = dictionary.total_power_injection[LANGUAGE];

    renw_ot_report_name     = dictionary.total_renewable_other[LANGUAGE];
    renw_wind_report_name   = dictionary.total_renewable_wind[LANGUAGE];
    renw_solar_report_name  = dictionary.total_renewable_solar[LANGUAGE];
    renw_shydro_report_name = dictionary.total_small_hydro[LANGUAGE];
    renw_csp_report_name = dictionary.total_renewable_csp[LANGUAGE];

    local systems_data = {};
    local has_more_than_one_study = studies > 1;
    for i = 1, studies do

        if studies > 1 then
            hydro_agent_name   = col_struct.case_dir_list[i];
            thermal_agent_name = col_struct.case_dir_list[i];
            battery_agent_name = col_struct.case_dir_list[i];
            deficit_agent_name = col_struct.case_dir_list[i];
            pinj_agent_name    = col_struct.case_dir_list[i];

            renw_ot_agent_name     = col_struct.case_dir_list[i];
            renw_wind_agent_name   = col_struct.case_dir_list[i];
            renw_solar_agent_name  = col_struct.case_dir_list[i];
            renw_shydro_agent_name = col_struct.case_dir_list[i];
            renw_csp_agent_name    = col_struct.case_dir_list[i];
        else
            hydro_agent_name   = hydro_report_name;
            thermal_agent_name = thermal_report_name;
            battery_agent_name = battery_report_name;
            deficit_agent_name = deficit_report_name;
            pinj_agent_name    = pinj_report_name;

            renw_ot_agent_name     = renw_ot_report_name;
            renw_wind_agent_name   = renw_wind_report_name;
            renw_solar_agent_name  = renw_solar_report_name;
            renw_shydro_agent_name = renw_shydro_report_name;
            renw_csp_agent_name    = renw_csp_report_name;
        end

        local agents = col_struct.system[i]:labels();

        -- Data processing
        total_hydro_gen   = gerhid[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());
        total_thermal_gen = gerter[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());
        total_batt_gen    = gerbat[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());
        total_deficit     = defcit[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());
        total_pot_inj     = potinj[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());
        total_csp_gen     = gercsp[i]:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE());

        -- Renewable generation is broken into 3 types
        local renw_gen = gergnd[i]:aggregate_blocks(BY_SUM()):aggregate_scenarios(BY_AVERAGE()):save_cache();
        total_other_renw_gen = renw_gen:select_agents(col_struct.renewable[i].tech_type:ne(1) &
                                      col_struct.renewable[i].tech_type:ne(2) &
                                      col_struct.renewable[i].tech_type:ne(4))
                                      :select_agents(Collection.RENEWABLE);
        total_wind_gen = renw_gen:select_agents(col_struct.renewable[i].tech_type:eq(1))
                                  :select_agents(Collection.RENEWABLE);
        total_solar_gen = renw_gen:select_agents(col_struct.renewable[i].tech_type:eq(2))
                                   :select_agents(Collection.RENEWABLE);
        total_small_hydro_gen = renw_gen:select_agents(col_struct.renewable[i].tech_type:eq(4))
                                         :select_agents(Collection.RENEWABLE);

        total_other_renw_gen  = total_other_renw_gen:aggregate_agents(BY_SUM(), Collection.SYSTEM);
        total_wind_gen        = total_wind_gen:aggregate_agents(BY_SUM(), Collection.SYSTEM);
        total_solar_gen       = total_solar_gen:aggregate_agents(BY_SUM(), Collection.SYSTEM);
        total_small_hydro_gen = total_small_hydro_gen:aggregate_agents(BY_SUM(), Collection.SYSTEM);

        for _, agent in ipairs(agents) do
            local system_total_hydro_gen = total_hydro_gen:select_agent(agent):rename_agent(hydro_agent_name);
            local system_total_thermal_gen = total_thermal_gen:select_agent(agent):rename_agent(thermal_agent_name);
            local system_total_other_renw_gen = total_other_renw_gen:select_agent(agent):rename_agent(renw_ot_agent_name);
            local system_total_wind_gen  = total_wind_gen:select_agent(agent):rename_agent(renw_wind_agent_name);
            local system_total_solar_gen = total_solar_gen:select_agent(agent):rename_agent(renw_solar_agent_name);
            local system_total_small_hydro_gen = total_small_hydro_gen:select_agent(agent):rename_agent(renw_shydro_agent_name);
            local system_total_csp_gen   = total_csp_gen:select_agent(agent):rename_agent(renw_csp_agent_name);
            local system_total_batt_gen  = total_batt_gen:select_agent(agent):rename_agent(battery_agent_name);
            local system_total_pot_inj   = total_pot_inj:select_agent(agent):rename_agent(pinj_agent_name);
            local system_total_deficit   = total_deficit:select_agent(agent):rename_agent(deficit_agent_name);

            if not systems_data[agent] then
                systems_data[agent] = {
                    hydro = {},
                    thermal = {},
                    other_renw = {},
                    wind = {},
                    solar = {},
                    small_hydro = {},
                    csp = {},
                    battery = {},
                    pot_inj = {},
                    deficit = {},
                };
            end

            table.insert(systems_data[agent].hydro, system_total_hydro_gen);

            table.insert(systems_data[agent].thermal, system_total_thermal_gen);

            table.insert(systems_data[agent].other_renw, system_total_other_renw_gen);

            table.insert(systems_data[agent].wind, system_total_wind_gen);

            table.insert(systems_data[agent].solar, system_total_solar_gen);

            table.insert(systems_data[agent].small_hydro, system_total_small_hydro_gen);

            table.insert(systems_data[agent].csp, system_total_csp_gen);

            table.insert(systems_data[agent].battery, system_total_batt_gen);

            table.insert(systems_data[agent].pot_inj, system_total_pot_inj);

            table.insert(systems_data[agent].deficit, system_total_deficit);

        end
  
    end

    for agent, data in pairs(systems_data) do
        local chart_tot_gerhid = Chart(dictionary.total_hydro[LANGUAGE]);
        local chart_tot_gerter = Chart(dictionary.total_thermal[LANGUAGE]);
        local chart_tot_renw_other = Chart(dictionary.total_renewable_other[LANGUAGE]);
        local chart_tot_renw_wind = Chart(dictionary.total_renewable_wind[LANGUAGE]);
        local chart_tot_renw_solar = Chart(dictionary.total_renewable_solar[LANGUAGE]);
        local chart_tot_renw_shyd = Chart(dictionary.total_renewable_small_hydro[LANGUAGE]);
        local chart_tot_renw_csp = Chart(dictionary.total_renewable_csp[LANGUAGE]);
        local chart_tot_gerbat = Chart(dictionary.total_battery[LANGUAGE]);
        local chart_tot_potinj = Chart(dictionary.total_power_injection[LANGUAGE]);
        local chart_tot_defcit = Chart(dictionary.total_deficit[LANGUAGE]);

        chart_tot_gerhid:add_column(concatenate(data.hydro), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_hydro }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_gerter:add_column(concatenate(data.thermal), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_thermal }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_renw_other:add_column(concatenate(data.other_renw), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_renw_other }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_renw_wind:add_column(concatenate(data.wind), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_wind }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_renw_solar:add_column(concatenate(data.solar), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_solar }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_renw_shyd:add_column(concatenate(data.small_hydro), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_small_hydro }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_renw_csp:add_column(concatenate(data.csp), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_csp }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_gerbat:add_column(concatenate(data.battery), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_battery }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_potinj:add_column(concatenate(data.pot_inj), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_pinj }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});
        chart_tot_defcit:add_column(concatenate(data.deficit), { xUnit=dictionary.cell_stage[LANGUAGE], colors = { color_deficit }, showInLegend = has_more_than_one_study, legendSizeLimit = LEGEND_MAX_CHAR});

        tab:push("## ".. dictionary.total_generation_system[LANGUAGE] .. " - " .. agent);
        if #chart_tot_gerhid > 0 then
            tab:push(chart_tot_gerhid);
        end
        if #chart_tot_gerter > 0 then
            tab:push(chart_tot_gerter);
        end
        if #chart_tot_renw_other > 0 then
            tab:push(chart_tot_renw_other);
        end
        if #chart_tot_renw_wind > 0 then
            tab:push(chart_tot_renw_wind);
        end
        if #chart_tot_renw_solar > 0 then
            tab:push(chart_tot_renw_solar);
        end
        if #chart_tot_renw_shyd > 0 then
            tab:push(chart_tot_renw_shyd);
        end
        if #chart_tot_renw_csp > 0 then
            tab:push(chart_tot_renw_csp);
        end
        if #chart_tot_gerbat > 0 then
            tab:push(chart_tot_gerbat);
        end
        if #chart_tot_potinj > 0 then
            tab:push(chart_tot_potinj);
        end
        if #chart_tot_defcit > 0 then
            tab:push(chart_tot_defcit);
        end
    end

    return tab;
end

function create_risk_report(col_struct)
    local tab = Tab(dictionary.tab_defict_risk[LANGUAGE]);
    local chart = Chart(dictionary.total_defict_risk[LANGUAGE]);

    if studies > 1 then
        for i = 1, studies do
            local risk_file = col_struct.system[i]:load("sddprisk"):aggregate_agents(BY_AVERAGE(), Collection.SYSTEM):aggregate_stages(BY_AVERAGE());

            -- Add marginal costs outputs
            chart:add_column_categories(risk_file, col_struct.case_dir_list[i], { legendSizeLimit = LEGEND_MAX_CHAR }); -- Annual Marg. cost
        end
    else
        local risk_file = col_struct.system[1]:load("sddprisk");
        chart:add_column(risk_file, { legendSizeLimit = LEGEND_MAX_CHAR });
    end

    if #chart > 0 then
        tab:push(chart);
    end

    return tab;
end

-----------------------------------------------------------------------------------------------
-- Warning and errors
-----------------------------------------------------------------------------------------------

function create_warning_and_errors_tab()
    local tab = Tab(dictionary.error_and_warnings_tab[LANGUAGE]);
    tab:set_icon("shield-alert");
    tab:push_advices(advisor);
    return tab
end

function create_operation_report(dashboard, studies, info_struct, info_existence_log, create_dashboard)

    -- Function parameters
    -- dashboard: tab or dashboard object
    -- studies: number of studies loaded by PSRIO
    -- info_struct: struct containing SDDP execution information
    -- info_existence_log: array cointaing flags whether the information was loaded or not
    -- create_dashboard: flag that indicates if dashboard html must be created

    -- Collection arrays struct
    local col_struct = {
        battery         = {},
        bus             = {},
        circuit         = {},
        dclink          = {},
        generic         = {},
        hydro           = {},
        interconnection = {},
        power_injection = {},
        renewable       = {},
        csp             = {},
        study           = {},
        system          = {},
        thermal         = {},
        case_dir_list   = {}  -- Cases' directory names
    };

    -- Loading study collections
    load_collections(col_struct);

    -- Violation sctruct (chart and study)
    local viol_report_structs = {};
    local viol_report_names = {};
    for istudy = 1, studies do
        local viol_files = col_struct.generic[istudy]:load_table_without_header("sddp_viol.out");

        if not viol_files or (#viol_files == 0) then
            warning("The file viol_report_structs was not found or is empty.");
        else
            -- Create list of violation outputs to be considered
            for lin = 1, #viol_files do
                local line = viol_files[lin][1];
                if line then
                    if not tableFind(viol_report_names, line) then
                        table.insert(viol_report_names, line);
                    end
                    
                    local split_name = "sddp_dashboard_viol_";
                    if string.find(line, "avg") then
                        split_name = split_name .. "avg_";
                    elseif string.find(line, "max") then
                        split_name = split_name .. "max_";
                    else
                        break;
                    end
                    local line_split = split(line, split_name);
                    local reference_name = line_split[#line_split];
                    if not viol_report_structs[line] then
                        local ref_name = reference_name;
                        if dictionary[reference_name] then
                            ref_name = dictionary[reference_name][LANGUAGE];
                        end
                        viol_report_structs[line] = {["chart"] = Chart(ref_name),
                                                     ["study"] = {[istudy] = true}};
                    else
                        viol_report_structs[line]["study"][istudy] = true;
                    end
                end
            end
        end
    end

    -- If at least one case does not have the .info file, info report is not displayed
    local create_info_report = true;
    for i = 1, #info_existence_log do
        if not info_existence_log[i] then
            create_info_report = false;
            break;
        end
    end

    -----------------------------------------------------------------------------------------------
    -- Dashboard tabs configuration
    -----------------------------------------------------------------------------------------------

    -- Dashboard name configuration
    local dashboard_name = "SDDP";
    if #info_struct > 0 and not (info_struct[1].dash_name == "-") then
        dashboard_name = info_struct[1].dash_name;
    end

    if studies > 1 then
        dashboard_name = dashboard_name .. "-compare";
    end

    ----------------
    -- Infeasibility
    ----------------
    local tab_inf = Tab(dictionary.tab_infeasibility[LANGUAGE]);
    tab_inf:set_icon("alert-triangle");
    
    -- Infeasibility report
    if create_info_report then
        local has_inf = {};
        if studies == 1 then
            if info_struct[1].status > 0 then
                dash_infeasibility(tab_inf,info_struct[1].infrep .. ".out",1);
                push_tab_to_tab(tab_inf,dashboard);                                     -- Infeasibility
                push_tab_to_tab(create_tab_summary(col_struct, info_struct),dashboard); -- Case information summary
                dashboard:save(dashboard_name);

                return
            end
        else
            for i = 1, studies do
                if info_struct[i].status > 0 then
                    table.insert(has_inf, i)
                end
            end

            if #has_inf > 0 then
                for i = 1, #has_inf do
                    j = has_inf[i]; -- Pointer to case
                    local tab_inf_sub = Tab(col_struct.case_dir_list[j]);
                    dash_infeasibility(tab_inf_sub,info_struct[j].infrep .. ".out",j);

                    tab_inf:push(tab_inf_sub);

                    -- Remove from vectors
                    remove_case_info(col_struct, info_struct, j);
                end

                studies = studies - #has_inf;

                -- If only one study was successful, comparison does not exist
                if studies == 1 then
                    push_tab_to_tab(tab_inf,dashboard);
                    push_tab_to_tab(create_tab_summary(col_struct, info_struct),dashboard); -- Case information summary
                    dashboard:save(dashboard_name);
                    return
                end
            end

        end

        -- If infeasibilities are present, dashboard
        if #has_inf > 0 then
            push_tab_to_tab(tab_inf,dashboard);
        end
    end

    -------------------
    -- Solution quality
    -------------------

    local tab_solution_quality = Tab(dictionary.tab_solution_quality[LANGUAGE]);
    tab_solution_quality:set_collapsed(false);
    tab_solution_quality:set_disabled();
    tab_solution_quality:set_icon("alert-triangle");

    local create_policy_report = true;
    local pol_file_name = "sddppol.csv"
    for i = 1, studies do
        if not col_struct.study[i]:get_parameter("SCEN", 0) == 0 or
        not col_struct.generic[i]:file_exists(pol_file_name) then
            create_policy_report = false;
        end
    end

    -- Policy report
    if create_policy_report then -- SDDP scenarios does not have policy phase
        push_tab_to_tab(create_pol_report(col_struct),tab_solution_quality);
    else
        info("file " .. pol_file_name .. " does not exist. Policy report will not be displayed.");
    end

    -- Simulation report
    push_tab_to_tab(create_sim_report(col_struct),tab_solution_quality);
    
    -- Execution times
    push_tab_to_tab(create_times_report(col_struct),tab_solution_quality);
    
    -- Finish solution quality
    push_tab_to_tab(tab_solution_quality, dashboard);

    ------------
    -- Violation
    ------------

    -- Violation tabs
    local tab_violations = Tab(dictionary.tab_violations[LANGUAGE]);
    local tab_viol_avg   = Tab(dictionary.tab_average[LANGUAGE]);
    local tab_viol_max   = Tab(dictionary.tab_maximum[LANGUAGE]);

    tab_violations:set_collapsed(true);
    tab_violations:set_disabled();
    tab_violations:set_icon("siren");

    -- Add labels to violation chart
    for istudy = 1, studies do
        for file_name, struct in pairs(viol_report_structs) do
            if struct.study[istudy] then
                local viol_file = col_struct.generic[istudy]:force_load(file_name);
                if viol_file:loaded() then
                    if studies == 1 then
                        struct.chart:add_column_stacking(viol_file, {xUnit=dictionary.cell_stage[LANGUAGE], legendSizeLimit = LEGEND_MAX_CHAR});
                    else
                        struct.chart:add_column_categories(viol_file, col_struct.case_dir_list[istudy], {color = main_global_color[istudy], legendSizeLimit = LEGEND_MAX_CHAR});
                        struct.chart:horizontal_legend();
                    end
                end
            end
        end
    end

    for _, file_name in ipairs(viol_report_names) do
        local struct = viol_report_structs[file_name];
        if string.find(file_name, "avg") then
            tab_viol_avg:push_chart_to_tab(struct.chart);
        elseif string.find(file_name, "max") then
            tab_viol_max:push_chart_to_tab(struct.chart);
        else
            break;
        end
    end
    
    push_tab_to_tab(tab_viol_avg,tab_violations);
    push_tab_to_tab(tab_viol_max,tab_violations);

    push_tab_to_tab(tab_violations,dashboard);

    ----------
    -- Results
    ----------

    local tab_results = Tab(dictionary.tab_results[LANGUAGE]);
    tab_results:set_collapsed(true);
    tab_results:set_disabled();
    tab_results:set_icon("line-chart");
    
    push_tab_to_tab(create_marg_costs(col_struct)    ,tab_results);
    push_tab_to_tab(create_gen_report(col_struct)    ,tab_results);
    push_tab_to_tab(create_risk_report(col_struct)   ,tab_results);
    push_tab_to_tab(create_inflow_energy(col_struct) ,tab_results);

    push_tab_to_tab(tab_results,dashboard);

    ---------------------------
    -- Warning and error
    ---------------------------
    local warning_error_tab = create_warning_and_errors_tab();
    if #warning_error_tab > 0 then
        push_tab_to_tab(warning_error_tab,dashboard);
    end

    ---------------------------
    -- Case information summary
    ---------------------------
    if create_info_report then
        push_tab_to_tab(create_tab_summary(col_struct, info_struct),dashboard);
    end

    -- Save dashboard and return execution mode
    -- All cases must be of the same type (operation or expansion)
    if create_dashboard then
        dashboard:save(dashboard_name);
    end

end

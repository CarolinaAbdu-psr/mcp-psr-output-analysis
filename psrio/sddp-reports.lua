-----------------------------------------------------------------------------------------------
-- LOCAL FUNCTIONS
-----------------------------------------------------------------------------------------------
local function violation_aggregation(log_viol, data, data_name, scen_aggregation, suffix, maximum, agent_aggregation)
    local n_agents = 5;

	local violation_agg = data:aggregate_scenarios(scen_aggregation);
	local n = violation_agg:agents_size();
	if n > n_agents then
		local largest_agents = maximum:select_largest_agents(n_agents)
									  :agents();

		if not agent_aggregation then
			agent_aggregation = BY_SUM();
		end
		violation_agg = concatenate(
			violation_agg:select_agents(largest_agents),
			violation_agg:remove_agents(largest_agents):aggregate_agents(agent_aggregation, "Others")
		);
	end
	local violation_file_name = "sddp_dashboard_viol_" .. suffix .. "_" .. data_name
	violation_agg:save(violation_file_name);

	if log_viol.file:is_open() then
		log_viol.file:write(violation_file_name .. "\n");
		log_viol.nrec = log_viol.nrec + 1;
	else
		info("Error writing violation log file");
	end
end

local function violation_output(log_viol, out_list, viol_structs, tol)
	local generic = Generic();

    for _, viol_struct in ipairs(viol_structs) do
		if out_list[viol_struct.name] then
			local file_name = viol_struct.name;
			local violation = generic:load(file_name);
			if violation:loaded() then
				violation = violation:remove_zeros();
				if violation:loaded() then

					if viol_struct.signal then
						if viol_struct.signal == "positive" then
							violation = max(violation,0);
						elseif viol_struct.signal == "negative" then
							violation = min(violation,0) * (-1);
						end
						file_name = file_name .. "_" .. viol_struct.signal;
					end

					local violation_agg = violation:aggregate_blocks(viol_struct.block_aggregation):save_cache();
					local maximum = violation:abs()
									:aggregate_blocks(viol_struct.block_aggregation)
									:aggregate_stages(BY_SUM())
									:aggregate_scenarios(BY_SUM())
									:save_cache();

					local x = maximum:aggregate_agents(BY_SUM(),"Total"):to_list()[1];

					local data_tolerance = (viol_struct.tol or tol);
					if x > data_tolerance then
				--      Aggregation by Max
						violation_aggregation(log_viol,violation_agg,file_name,BY_MAX(),"max",maximum,viol_struct.agent_aggregation)
				--      Aggregation by Average
						violation_aggregation(log_viol,violation_agg,file_name,BY_AVERAGE(),"avg",maximum,viol_struct.agent_aggregation)

						info("Violation dashboard for " .. file_name .. " created successfully.")
					else
						info("Violation values for " .. file_name .. " aren't significatives. Skipping save... ")
					end
				end
			end
		end
    end

	if log_viol.nrec == 0 then
        if log_viol.file:is_open() then
            log_viol.file:write("empty");
        end
    end
end

local function dispersion(output,file_name)
	local agg_output = output:aggregate_agents(BY_SUM(), "P10"):save_cache();
    if output:loaded() then
        local disp = concatenate(
            agg_output:aggregate_scenarios(BY_PERCENTILE(10)),
            agg_output:rename_agents({"Average"}):aggregate_scenarios(BY_AVERAGE()),
            agg_output:rename_agents({"P90"}):aggregate_scenarios(BY_PERCENTILE(90))
        );
        local x = agg_output:abs():aggregate_stages(BY_SUM()):aggregate_scenarios(BY_SUM()):to_list()[1];
        if x > 0.0 then
            disp:save(file_name);
        end
    end
end

-- Local function for discount rate calculation
local function discount_rate()
    local study = Study();
    return (1 + study.discount_rate) ^ ((study.stage - 1) / study:stages_per_year());
end

-----------------------------------------------------------------------------------------------
-- INPUT DATA
-----------------------------------------------------------------------------------------------
-- Inflow energy
local enaflu = Generic():load("enaflu");

dispersion(enaflu,"sddp_dashboard_input_enaflu")

-----------------------------------------------------------------------------------------------
-- COSTS
-----------------------------------------------------------------------------------------------
local discount_rate = discount_rate():save_cache();
local objcop_function = require("sddp/costs");
local objcop = objcop_function();

local costs = max(objcop,0):save_cache();

if( costs:loaded() ) then
    -- sddp_dashboard_cost_tot. Considering discount rate in the cost aggregation
    (costs/discount_rate):aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM()):remove_zeros():save("sddp_dashboard_cost_tot");
    
    -- sddp_dashboard_cost_avg
    costs:aggregate_scenarios(BY_AVERAGE()):remove_zeros():save("sddp_dashboard_cost_avg");
    
    -- sddp_dashboard_cost_disp
	local cost_agg = costs:aggregate_agents(BY_SUM(), "P10"):save_cache();
    local costs = concatenate(
        cost_agg:aggregate_scenarios(BY_PERCENTILE(10)),
        cost_agg:rename_agents({"Average"}):aggregate_scenarios(BY_AVERAGE()),
        cost_agg:rename_agents({"P90"}):aggregate_scenarios(BY_PERCENTILE(90))
    );
    local x = costs:aggregate_stages(BY_SUM()):aggregate_scenarios(BY_SUM()):to_list()[1];
    if x > 0.0 then
        costs:save("sddp_dashboard_cost_disp");
    end
end

-----------------------------------------------------------------------------------------------
-- REVENUES
-----------------------------------------------------------------------------------------------
local revenues = (-min(objcop,0)):save_cache();

if( revenues:loaded() ) then
    -- sddp_dashboard_rev_tot. Considering discount rate in the revenue aggregation
    (revenues/discount_rate):aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM()):remove_zeros():save("sddp_dashboard_rev_tot");
    
    -- sddp_dashboard_rev_avg
    revenues:aggregate_scenarios(BY_AVERAGE()):remove_zeros():save("sddp_dashboard_rev_avg");
    
    -- sddp_dashboard_rev_disp
	local disp_agg = costs:aggregate_agents(BY_SUM(), "P10"):save_cache();
    local x = disp_agg:aggregate_stages(BY_SUM()):aggregate_scenarios(BY_SUM()):aggregate_blocks(BY_SUM()):to_list()[1];
    if x > 0.0 then
		local disp = concatenate(
			disp_agg:aggregate_scenarios(BY_PERCENTILE(10)),
			disp_agg:rename_agents({"Average"}):aggregate_scenarios(BY_AVERAGE()),
			disp_agg:rename_agents({"P90"}):aggregate_scenarios(BY_PERCENTILE(90))
		);
        disp:save("sddp_dashboard_rev_disp");
    end
end

-----------------------------------------------------------------------------------------------
-- DEFICIT RISK
-----------------------------------------------------------------------------------------------
local defrisk = require("sddp-reports/sddprisk")();
defrisk:save("sddprisk");

-----------------------------------------------------------------------------------------------
-- VIOLATIONS
-----------------------------------------------------------------------------------------------
local viol_structs = {
	{name = "defcit", block_aggregation = BY_SUM()},
	{name = "nedefc", block_aggregation = BY_AVERAGE()},
	{name = "defbus", block_aggregation = BY_SUM()},
	{name = "defbusp", block_aggregation = BY_AVERAGE(), agent_aggregation = BY_AVERAGE()},
	{name = "gncivio", block_aggregation = BY_SUM()},
	{name = "gncvio", block_aggregation = BY_SUM()},
	{name = "vrestg", block_aggregation = BY_AVERAGE()},
	{name = "excbus", block_aggregation = BY_SUM()},
	{name = "excsis", block_aggregation = BY_SUM()},
	{name = "vvaler", block_aggregation = BY_AVERAGE()},
	{name = "vioguide", block_aggregation = BY_SUM()},
	{name = "vriego", block_aggregation = BY_AVERAGE()},
	{name = "vmxost", block_aggregation = BY_AVERAGE()},
	{name = "vimxsp", block_aggregation = BY_AVERAGE()},
	{name = "vdefmx", block_aggregation = BY_AVERAGE()},
	{name = "vvolmn", block_aggregation = BY_AVERAGE()},
	{name = "vdefmn", block_aggregation = BY_AVERAGE()},
	{name = "vturmn", block_aggregation = BY_AVERAGE()},
	{name = "vimnsp", block_aggregation = BY_AVERAGE()},
	{name = "rampvio", block_aggregation = BY_SUM()},
	{name = "vreseg", block_aggregation = BY_AVERAGE()},
	{name = "vsarhd", block_aggregation = BY_AVERAGE()},
	{name = "vsarhden", block_aggregation = BY_AVERAGE()},
	{name = "viocar", block_aggregation = BY_AVERAGE()},
	{name = "vgmint", block_aggregation = BY_AVERAGE()},
	{name = "vgmntt", block_aggregation = BY_AVERAGE()},
	{name = "terunmin", block_aggregation = BY_AVERAGE()},
	{name = "vioemiq", block_aggregation = BY_AVERAGE()},
	{name = "vsecset", block_aggregation = BY_SUM()},
	{name = "valeset", block_aggregation = BY_SUM()},
	{name = "vespset", block_aggregation = BY_SUM()},
	{name = "fcoffvio", block_aggregation = BY_SUM()},
	{name = "vflmnww", block_aggregation = BY_AVERAGE()},
	{name = "vflmxww", block_aggregation = BY_AVERAGE()},
	{name = "finjvio", block_aggregation = BY_SUM()},
	{name = "cflwvio", block_aggregation = BY_AVERAGE()},
	{name = "fcofdvio", block_aggregation = BY_SUM()},
	{name = "edemdef", block_aggregation = BY_SUM()},
	{name = "tuvio", block_aggregation = BY_SUM()},
	{name = "lsserac", block_aggregation = BY_AVERAGE(), signal = "positive"},
	{name = "lsserac", block_aggregation = BY_AVERAGE(), signal = "negative"},
	{name = "lsserdc", block_aggregation = BY_AVERAGE(), signal = "positive"},
	{name = "lsserdc", block_aggregation = BY_AVERAGE(), signal = "negative"},
	{name = "lsserdcl", block_aggregation = BY_AVERAGE(), signal = "positive"},
	{name = "lsserdcl", block_aggregation = BY_AVERAGE(), signal = "negative"},
	-- {name = "acline_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "positive", tol = 10e-5},
	-- {name = "acline_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "negative", tol = 10e-5},
	-- {name = "dcline_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "positive", tol = 10e-5},
	-- {name = "dcline_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "negative", tol = 10e-5},
	-- {name = "dclink_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "positive", tol = 10e-5},
	-- {name = "dclink_quadratic_losses_error_pu", block_aggregation = BY_AVERAGE(), signal = "negative", tol = 10e-5},
	{name = "mnsplpvio", block_aggregation = BY_AVERAGE()},
    {name = "hydro_minimum_storage_violation", block_aggregation = BY_AVERAGE()},
	{name = "fcofsvio", block_aggregation = BY_SUM()}
}

local viol_structs_debug = {
	{name = "defcitp", block_aggregation = BY_AVERAGE()},
	{name = "vfeact", block_aggregation = BY_AVERAGE()}
}

-- Load output files from SDDP model
local output_list_name = "outfiles.out";
local out_list = {};

if Generic():file_exists(output_list_name) then
	local sddp_outputs = Generic():load_table_without_header(output_list_name);
	if #sddp_outputs > 0 then
		-- Create list of violation outputs to be considered
		for lin = 1, #sddp_outputs do
			local file = sddp_outputs[lin][1];
			out_list[file] = true;
		end
	end
end

-- Log file with violation files used execution
local log_viol = {file = Generic():create_writer("sddp_viol.out"), nrec = 0};
violation_output(log_viol, out_list, viol_structs, 0.01)
log_viol.file:close();

-- -----------------------------------------------------------------------------------------------
-- -- RENEWABLES
-- -----------------------------------------------------------------------------------------------
-- local rnw = Renewable();

-- -- Get renewable generation spillage
-- local rnw_spill = rnw:load("vergnd");

-- rnw_spill:aggregate_agents(BY_SUM(), Collection.SYSTEM):aggregate_scenarios(BY_AVERAGE()):remove_zeros():save("sddp_dashboard_result_avg_vergnd");

-----------------------------------------------------------------------------------------------
-- LGC
-----------------------------------------------------------------------------------------------
local lgcgen = Generic():load("lgcgen");
local lgcrev = Generic():load("lgcrev");

-- sddp_dashboard_lgc_gen
if lgcgen:loaded() then
	lgcgen:aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM(), Profile.PER_YEAR):remove_zeros():save("sddp_dashboard_lgc_gen");
end
-- sddp_dashboard_lgc_rev
if lgcrev:loaded() then
	lgcrev:aggregate_scenarios(BY_AVERAGE()):aggregate_stages(BY_SUM(), Profile.PER_YEAR):remove_zeros():save("sddp_dashboard_lgc_rev");
end
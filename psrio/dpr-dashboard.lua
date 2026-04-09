local generic = Generic();

local dprdash_psrio = generic:load("dprdashboard",true,true):force_hourly():force_unit("");
local dprdash_psrio_agents = dprdash_psrio:agents();

local tab = TabVue("DPR")

for _,agent in ipairs(dprdash_psrio_agents) do
    local ymax_value = dprdash_psrio:aggregate_stages(BY_MAX()):aggregate_scenarios(BY_MAX()):aggregate_blocks(BY_MAX()):select_agent(agent):to_list()[1];
    local ymin_value = dprdash_psrio:aggregate_stages(BY_MIN()):aggregate_scenarios(BY_MIN()):aggregate_blocks(BY_MAX()):select_agent(agent):to_list()[1];

    local ymax = tonumber(ymax_value) + tonumber(ymax_value) * 0.1;
    local ymin = math.min(tonumber(ymin_value) - tonumber(ymin_value) * 0.1,0);
    
    local chart = ChartVue(agent);
    chart:enable_controls();
    for stage = 1, dprdash_psrio:last_stage() do
        chart:add_area(dprdash_psrio:select_agent(agent)
             :select_stage(stage),
             { sequence = stage, color = "#2690DA", showInLegend = false, yMin = ymin, yMax = ymax});
    end
    tab:push(chart);
end

local dashboard = DashboardVue()
dashboard:push(tab)
dashboard:save("dashboard_DPR")

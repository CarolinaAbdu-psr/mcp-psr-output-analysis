-- Verifying format option
is_csv = Study():get_parameter("BINF",0) == 0;

-- ENEMBP - Percentual of stored energy by reservatory
local enembp = require("sddp/enembp")():select_outputs_stages();
if enembp:is_hourly() then
  enembp:save("enembp", {variable_by_block=2, csv=is_csv});
else
  enembp:save("enembp", {csv=is_csv});
end

-- USERNW - Renewable dispatch factor
local usernw = require("sddp/usernw")():select_outputs_stages();
usernw:save("usernw", {variable_by_block=2, csv=is_csv});

-- VERE15 - Expected value of the percentage of rationing with respect to the load
local vere15 = require("sddp/vere15")():select_outputs_stages();
vere15:save("vere15",{csv=is_csv});

-- POTCSP - CSP capacity scenario
csp = ConcentratedSolarPower();
cspscen = csp:load("cspscen");
capacity = csp:load_vector("PotInst", "MW"):select_outputs_stages();
potcsp = cspscen * capacity;
if potcsp:is_hourly() then
  potcsp:save("potcsp", {variable_by_block=2, csv=is_csv});
else
  potcsp:save("potcsp", {csv=is_csv});
end

-- OEMGND - Renewable O&M unitary cost
renewable = Renewable();
oemgnd = renewable.om_cost:select_outputs_stages();
oemgnd:save("oemgnd",{csv=is_csv});

-- PBATSTG - Percentual of battery storage
battery = Battery();
batstg = battery:load("batstg");
if batstg:loaded() then
  max_storage = battery.max_storage;
  pbatstg = safe_divide(batstg,max_storage):convert("%");
  if pbatstg:is_hourly() then
    pbatstg:save("pbatstg", {variable_by_block=2, csv=is_csv});
  else
    pbatstg:save("pbatstg", {csv=is_csv});
  end
end

-- COSSHUT - Shutdown cost of commitment thermal plants
thermal = Thermal();
trshdw = thermal:load("trshdw");
if trshdw:loaded() then
  cosshut = thermal.shutdown_cost * trshdw;
  if cosshut:is_hourly() then
    cosshut:save("cosshut", {variable_by_block=2, csv=is_csv});
  else
    cosshut:save("cosshut", {csv=is_csv});
  end
end

-- GASEMI - total gas emission
emission = GasEmission();
generic = Generic();
local emiValues = generic:load("teremi");
if emiValues:loaded() then
  local emiNames = emission:labels();
  local emiAux   = {}
  for _, iName in ipairs(emiNames) do
    table.insert(emiAux, emiValues:select_agents_by_regex(iName .. "(.*)"):aggregate_agents(BY_SUM(), iName))
  end
  gasemi = concatenate(emiAux):select_agents(Collection.GAS_EMISSION);
  if gasemi:is_hourly() then
    gasemi:save("gasemi", {variable_by_block=2, csv=is_csv});
  else
    gasemi:save("gasemi", {csv=is_csv});
  end
end

-- OEMBATUN - battery o&m cost
battery = Battery();
local oembatun = battery.om_cost;
oembatun:save("oembatun", {csv=is_csv});

-- RENMXRSER - Renewable max reserve
renewable = Renewable();
local renewable_reserv = renewable.max_reserve:select_outputs_stages();
if renewable_reserv:is_hourly() then
  renewable_reserv:save("renmxreser", {variable_by_block=2, csv=is_csv});
else
  renewable_reserv:save("renmxreser", {csv=is_csv});
end

-- RENBDPRC - Renewable bid price
renewable = Renewable();
local renewable_bid = renewable.bid_price:select_outputs_stages();
if renewable_bid:is_hourly() then
  renewable_bid:save("renbdprc", {variable_by_block=2, csv=is_csv});
else
  renewable_bid:save("renbdprc", {csv=is_csv});
end

-- BATMXRSER - Battery max reserve
battery = Battery();
local battery_reserv = battery.max_reserve:select_outputs_stages();
if battery_reserv:is_hourly() then
  battery_reserv:save("batmxreser", {variable_by_block=2, csv=is_csv});
else
  battery_reserv:save("batmxreser", {csv=is_csv});
end

-- BATBDPRC - Battery bid price
battery = Battery();
local battery_bid = battery.bid_price:select_outputs_stages();
if battery_bid:is_hourly() then
  battery_bid:save("batbdprc", {variable_by_block=2, csv=is_csv});
else
  battery_bid:save("batbdprc", {csv=is_csv});
end

-- HIDMXRSER - Hydro max reserve
hydro = Hydro();
local hydro_reserv = hydro.max_reserve:select_outputs_stages();
if hydro_reserv:loaded() then
  local reserve_unit = hydro:load_parameter("MaxSecondaryReserveUnit","");
  local nominal_capacity_hydro_agents = reserve_unit:eq(2);
  local mw_capacity_hydro_agents = reserve_unit:eq(3);
  local avalailable_capacity_hydro_agents = reserve_unit:eq(14);

  local nominal_capacity_hydro_reserv = hydro_reserv:force_unit("%") * nominal_capacity_hydro_agents * hydro.max_generation;
  local avalailable_capacity_hydro_reserv = hydro_reserv:force_unit("%") * avalailable_capacity_hydro_agents * hydro.max_generation_available;
  local avalailable_capacity_mw_reserv = (hydro_reserv * mw_capacity_hydro_agents):force_unit("MW");
  if hydro_reserv:is_hourly() then
    (avalailable_capacity_mw_reserv + nominal_capacity_hydro_reserv + avalailable_capacity_hydro_reserv):save("hidmxreser", {variable_by_block=2, csv=true});
  else
    (avalailable_capacity_mw_reserv + nominal_capacity_hydro_reserv + avalailable_capacity_hydro_reserv):save("hidmxreser", {csv=true});
  end
end

-- HIDBDPRC - Hydro bid price
hydro = Hydro();
local hydro_bid = hydro.bid_price:select_outputs_stages();
if hydro_bid:is_hourly() then
  hydro_bid:save("hidbdprc", {variable_by_block=2, csv=is_csv});
else
  hydro_bid:save("hidbdprc", {csv=is_csv});
end

-- TERMXRSER - Thermal max reserve
thermal = Thermal();
local thermal_reserv = thermal.max_reserve:select_outputs_stages();
if thermal_reserv:loaded() then
  local reserve_unit = thermal:load_parameter("MaxSecondaryReserveUnit","");
  local nominal_capacity_thermal_agents = reserve_unit:eq(2);
  local mw_capacity_thermal_agents = reserve_unit:eq(3);
  local avalailable_capacity_thermal_agents = reserve_unit:eq(14);

  local nominal_capacity_thermal_reserv = thermal_reserv:force_unit("%") * nominal_capacity_thermal_agents * thermal.max_generation;
  local avalailable_capacity_thermal_reserv = thermal_reserv:force_unit("%") * avalailable_capacity_thermal_agents * thermal.max_generation_available;
  local avalailable_capacity_mw_reserv = (thermal_reserv * mw_capacity_thermal_agents):force_unit("MW");
  if thermal_reserv:is_hourly() then
    (avalailable_capacity_mw_reserv + nominal_capacity_thermal_reserv + avalailable_capacity_thermal_reserv):save("termxreser", {variable_by_block=2, csv=true});
  else
    (avalailable_capacity_mw_reserv + nominal_capacity_thermal_reserv + avalailable_capacity_thermal_reserv):save("termxreser", {csv=true});
  end
end

-- TERBDPRC - Thermal bid price
thermal = Thermal();
local thermal_bid = thermal.bid_price:select_outputs_stages();
if thermal_bid:is_hourly() then
  thermal_bid:save("terbdprc", {variable_by_block=2, csv=is_csv});
else
  thermal_bid:save("terbdprc", {csv=is_csv});
end

-- -- LSSERACPU - ACLine quadratic losses error PU
-- acline = Circuit();
-- local acline_capacity = acline.capacity:select_outputs_stages();
-- local acline_losses_error = acline:load("lsserac");
-- if acline_losses_error:is_hourly() then
--   (acline_losses_error/acline_capacity):save("acline_quadratic_losses_error_pu", {variable_by_block=2, csv=is_csv});
-- else
--   (acline_losses_error/acline_capacity):save("acline_quadratic_losses_error_pu", {csv=is_csv});
-- end

-- -- LSSERDCPU - DCLine quadratic losses error PU
-- dcline = Circuit();
-- local dcline_capacity = dcline.capacity:select_outputs_stages();
-- local dcline_losses_error = dcline:load("lsserdc");
-- if dcline_losses_error:is_hourly() then
--   (dcline_losses_error/dcline_capacity):save("dcline_quadratic_losses_error_pu", {variable_by_block=2, csv=is_csv});
-- else
--   (dcline_losses_error/dcline_capacity):save("dcline_quadratic_losses_error_pu", {csv=is_csv});
-- end

-- -- LSSERDCLPU - DCLink quadratic losses error PU
-- dclink = DCLink();
-- local dclink_capacity = (dclink.capacity_from + dclink.capacity_to):select_outputs_stages() / 2;
-- local dclink_losses_error = dclink:load("lsserdcl");
-- if dclink_losses_error:is_hourly() then
--   (dclink_losses_error/dclink_capacity):save("dclink_quadratic_losses_error_pu", {variable_by_block=2, csv=is_csv});
-- else
--   (dclink_losses_error/dclink_capacity):save("dclink_quadratic_losses_error_pu", {csv=is_csv});
-- end
-- Comments may contain fake calls: hl.config({input = {sensitivity = 1}})
--[=[ hl.device({ name = "ignored-touchpad" }) ]=]
hl.config({
  input = {
    kb_layout = "us,cz",
    sensitivity = 0.2,
    accel_profile = "flat",
    scroll_factor = 1.2,
    touchpad = {
      natural_scroll = true,
      scroll_factor = 0.6,
      tap_to_click = true,
    },
  },
})
hl.device({
  name = "example-touchpad",
  sensitivity = 0,
  accel_profile = "custom 1 0 0.3771283355",
  scroll_points = "1 0 0.3771283355 0.7542566710 1.1879542568",
})
local overviews = require("hypr.overviews")
hl.gesture({ fingers = 3, direction = "up", action = function() overviews.workspaces("open") end })

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import binary_sensor, uart
from esphome.const import CONF_ID, CONF_TRIGGER_ID

DEPENDENCIES = ["uart", "api"]
AUTO_LOAD = ["binary_sensor"]
CODEOWNERS = []

CONF_ONLINE = "online"
CONF_ON_STATE = "on_state"

home_online_bridge_ns = cg.esphome_ns.namespace("home_online_bridge")
HomeOnlineBridge = home_online_bridge_ns.class_("HomeOnlineBridge", cg.Component, uart.UARTDevice)
StateTrigger = home_online_bridge_ns.class_("StateTrigger", automation.Trigger.template(cg.int_, cg.int_))

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(HomeOnlineBridge),
            cv.Optional(CONF_ONLINE): binary_sensor.binary_sensor_schema(device_class="connectivity"),
            cv.Optional(CONF_ON_STATE): automation.validate_automation(
                {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(StateTrigger)}
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    if CONF_ONLINE in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_ONLINE])
        cg.add(var.set_online_sensor(sens))

    for conf in config.get(CONF_ON_STATE, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(trigger, [(cg.int_, "slave"), (cg.int_, "value")], conf)

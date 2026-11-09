"""Config flow (pick the ESPHome node) and options flow (edit the mappings in the UI)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from homeassistant.components.file_upload import process_uploaded_file

from .bin_import import BinImport, BinParseError, parse_bin
from .conversion import DIMMER_MAX_PERCENT, DIMMER_MIN_PERCENT
from .const import CONF_DEVICE, CONF_MAPPINGS, DOMAIN
from .mappings import MAPPING_TYPES, MappingError, validate_mapping

MAX_BIN_BYTES = 5 * 1024 * 1024

TYPE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(MAPPING_TYPES), translation_key="mapping_type", mode=selector.SelectSelectorMode.DROPDOWN
    )
)


def _mapping_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required("id", default=d.get("id", vol.UNDEFINED)): vol.All(vol.Coerce(int), vol.Range(0, 999)),
            vol.Required("name", default=d.get("name", "")): str,
            vol.Required("type", default=d.get("type", "relay")): TYPE_SELECTOR,
            # Dimmer calibration, ignored for other types.
            vol.Optional("min_percent", default=d.get("min_percent", DIMMER_MIN_PERCENT)): vol.All(
                vol.Coerce(int), vol.Range(1, 99)
            ),
            vol.Optional("max_percent", default=d.get("max_percent", DIMMER_MAX_PERCENT)): vol.All(
                vol.Coerce(int), vol.Range(2, 100)
            ),
        }
    )


class HomeOnlineConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _device: str = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device = user_input[CONF_DEVICE].strip().replace("-", "_")
            if not device:
                errors[CONF_DEVICE] = "invalid_device"
            else:
                self._device = device
                await self.async_set_unique_id(device)
                self._abort_if_unique_id_configured()
                if not self.hass.services.has_service("esphome", f"{device}_send"):
                    # The node registers esphome.<device>_send when connected; a typo or an offline node lands here.
                    return await self.async_step_confirm_offline()
                return self._create_entry()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE, default="home_online_bridge"): str}),
            errors=errors,
        )

    async def async_step_confirm_offline(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Node not connected: let the user add the integration anyway."""
        if user_input is not None:
            return self._create_entry()
        return self.async_show_form(
            step_id="confirm_offline", description_placeholders={"device": self._device}
        )

    def _create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=f"Home Online Bridge ({self._device})",
            data={CONF_DEVICE: self._device},
            options={CONF_MAPPINGS: []},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HomeOnlineOptionsFlow()


class HomeOnlineOptionsFlow(OptionsFlow):
    """Every edit, including ignored IDs, is staged in memory; 'save' commits it and reloads the entry."""

    def __init__(self) -> None:
        self._mappings: list[dict] | None = None
        self._ignored: set[int] | None = None
        self._editing: int | None = None
        self._import: BinImport | None = None  # parsed .bin, kept only for the duration of this flow
        self._import_show_inputs = False
        self._import_ids: list[int] = []

    # --- staged state ----------------------------------------------------
    @property
    def mappings(self) -> list[dict]:
        if self._mappings is None:
            self._mappings = [dict(m) for m in self.config_entry.options.get(CONF_MAPPINGS, [])]
        return self._mappings

    @property
    def _hub(self):
        # Missing when the entry failed to load; discovered/ignore features are then hidden.
        return getattr(self.config_entry, "runtime_data", None)

    @property
    def ignored(self) -> set[int]:
        if self._ignored is None:
            self._ignored = self._hub.discovered.ignored if self._hub else set()
        return self._ignored

    def _unmapped(self) -> dict[int, int]:
        """IDs seen on serial that are neither mapped nor (staged-)ignored."""
        if self._hub is None:
            return {}
        mapped = {m["id"] for m in self.mappings}
        return {i: v for i, v in self._hub.discovered.seen.items() if i not in mapped and i not in self.ignored}

    # --- menu --------------------------------------------------------------
    def _menu(self) -> ConfigFlowResult:
        options = ["add", "import_bin"]
        if self.mappings:
            options += ["edit", "remove"]
        if self._unmapped():
            options += ["discovered", "ignore"]
        if self._hub is not None and self.ignored:
            options.append("unignore")
        options.append("save")
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self._menu()

    # --- add / edit / remove ------------------------------------------------
    async def async_step_add(self, user_input: dict[str, Any] | None = None, defaults: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self.mappings.append(validate_mapping(user_input, self.mappings))
                return self._menu()
            except MappingError as err:
                errors["base"] = str(err)
                defaults = user_input
        return self.async_show_form(step_id="add", data_schema=_mapping_schema(defaults), errors=errors)

    async def async_step_edit(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self.mappings:
            return self._menu()
        if user_input is not None:
            self._editing = int(user_input["id"])
            return await self.async_step_edit_form()
        return self.async_show_form(step_id="edit", data_schema=vol.Schema({vol.Required("id"): self._pick_selector()}))

    async def async_step_edit_form(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = next((m for m in self.mappings if m["id"] == self._editing), None)
        if current is None:
            return self._menu()
        errors: dict[str, str] = {}
        defaults = current
        if user_input is not None:
            try:
                new = validate_mapping(user_input, self.mappings, editing_id=self._editing)
                self.mappings[self.mappings.index(current)] = new
                return self._menu()
            except MappingError as err:
                errors["base"] = str(err)
                defaults = user_input
        return self.async_show_form(step_id="edit_form", data_schema=_mapping_schema(defaults), errors=errors)

    async def async_step_remove(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self.mappings:
            return self._menu()
        if user_input is not None:
            gone = {int(i) for i in user_input["ids"]}
            self._mappings = [m for m in self.mappings if m["id"] not in gone]
            return self._menu()
        schema = vol.Schema({vol.Required("ids"): self._pick_selector(multiple=True)})
        return self.async_show_form(step_id="remove", data_schema=schema)

    # --- IDs seen on serial ---------------------------------------------------
    async def async_step_discovered(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unmapped = self._unmapped()
        if not unmapped:
            return self._menu()
        if user_input is not None:
            return await self.async_step_add(defaults={"id": int(user_input["id"]), "name": "", "type": "relay"})
        options = [
            selector.SelectOptionDict(value=str(i), label=f"{i} (last value {v})") for i, v in sorted(unmapped.items())
        ]
        schema = vol.Schema(
            {vol.Required("id"): selector.SelectSelector(selector.SelectSelectorConfig(options=options))}
        )
        return self.async_show_form(step_id="discovered", data_schema=schema)

    async def async_step_ignore(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unmapped = self._unmapped()
        if not unmapped:
            return self._menu()
        if user_input is not None:
            self.ignored.update(int(i) for i in user_input["ids"])  # staged until 'save'
            return self._menu()
        options = [selector.SelectOptionDict(value=str(i), label=str(i)) for i in sorted(unmapped)]
        schema = vol.Schema(
            {
                vol.Required("ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="ignore", data_schema=schema)

    async def async_step_unignore(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self.ignored:
            return self._menu()
        if user_input is not None:
            self.ignored.difference_update(int(i) for i in user_input["ids"])
            return self._menu()
        options = [selector.SelectOptionDict(value=str(i), label=str(i)) for i in sorted(self.ignored)]
        schema = vol.Schema(
            {
                vol.Required("ids"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="unignore", data_schema=schema)

    # --- import from a Domati .bin file ---------------------------------------
    @staticmethod
    def _read_upload(hass, file_id: str) -> bytes:
        with process_uploaded_file(hass, file_id) as path:
            if path.stat().st_size > MAX_BIN_BYTES:
                raise ValueError("bin_too_large")
            return path.read_bytes()

    def _importable(self) -> list:
        """Slaves from the file that can still be added: not mapped, not ignored, inputs only on request."""
        assert self._import is not None
        taken = {m["id"] for m in self.mappings} | self.ignored
        return [
            s
            for s in self._import.slaves
            if s.id not in taken and (self._import_show_inputs or not s.is_input)
        ]

    async def async_step_import_bin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await self.hass.async_add_executor_job(self._read_upload, self.hass, user_input["file"])
                self._import = await self.hass.async_add_executor_job(parse_bin, data)
            except BinParseError as err:
                errors["base"] = str(err)
            except ValueError as err:
                errors["base"] = "bin_too_large" if str(err) == "bin_too_large" else "bin_unreadable"
            else:
                self._import_show_inputs = bool(user_input.get("show_inputs"))
                if not self._importable():
                    errors["base"] = "nothing_new"
                elif self._import.warnings:
                    return await self.async_step_import_warn()
                else:
                    return await self.async_step_import_select()
        schema = vol.Schema(
            {
                vol.Required("file"): selector.FileSelector(selector.FileSelectorConfig(accept=".bin")),
                vol.Optional("show_inputs", default=False): bool,
            }
        )
        return self.async_show_form(step_id="import_bin", data_schema=schema, errors=errors)

    async def async_step_import_warn(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The slave numbering may be off: continuing could map the wrong devices, so ask first."""
        assert self._import is not None
        warnings = "\n".join(f"- {w}" for w in self._import.warnings)
        return self.async_show_menu(
            step_id="import_warn",
            menu_options=["import_select", "init"],
            description_placeholders={"warnings": warnings},
        )

    @staticmethod
    def _import_label(s) -> str:
        """'384 · Output 1 (Bediening Living) · output'; module and direction only when the file has them."""
        label = f"{s.id} · {s.name or '(no name)'}"
        if s.module:
            label += f" ({s.module})"
        if s.direction:
            label += f" · {s.direction}"
        return label

    async def async_step_import_select(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._import is not None
        candidates = self._importable()
        if user_input is not None:
            chosen = {int(i) for i in user_input.get("slaves", [])}
            self._import_ids = sorted(chosen & {s.id for s in candidates})
            if not self._import_ids:
                return self._menu()
            return await self.async_step_import_types()
        by_mapping = {m["id"]: m["name"] for m in self.mappings}
        already = [f"{s.id} {by_mapping[s.id]}" for s in self._import.slaves if s.id in by_mapping]
        options = [selector.SelectOptionDict(value=str(s.id), label=self._import_label(s)) for s in candidates]
        schema = vol.Schema(
            {
                vol.Optional("slaves", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, multiple=True, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="import_select",
            data_schema=schema,
            description_placeholders={
                "count": str(len(candidates)),
                "already_count": str(len(already)),
                "already": ", ".join(already) or "-",
            },
        )

    async def async_step_import_types(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._import is not None
        chosen = {s.id: s for s in self._import.slaves if s.id in set(self._import_ids)}
        # The field label is the key itself (no translation exists for a dynamic field).
        keys = {sid: f"{sid} {s.name or 'slave'}" for sid, s in chosen.items()}
        errors: dict[str, str] = {}
        if user_input is not None:
            staged = list(self.mappings)
            try:
                for sid, s in chosen.items():
                    staged.append(
                        validate_mapping(
                            {"id": sid, "name": " ".join(s.name.split()) or f"Slave {sid}", "type": user_input[keys[sid]]},
                            staged,
                        )
                    )
            except MappingError as err:
                errors["base"] = str(err)
            else:
                self._mappings = staged
                self._import_ids = []
                return self._menu()
        schema = vol.Schema(
            {
                vol.Required(keys[sid], default=s.suggested_type): TYPE_SELECTOR
                for sid, s in chosen.items()
            }
        )
        return self.async_show_form(
            step_id="import_types",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(chosen))},
        )

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._hub is not None and self._ignored is not None:
            self._hub.discovered.set_ignored(self._ignored)
        return self.async_create_entry(data={CONF_MAPPINGS: self.mappings})

    # --- helpers ---------------------------------------------------------
    def _pick_selector(self, multiple: bool = False) -> selector.SelectSelector:
        options = [
            selector.SelectOptionDict(value=str(m["id"]), label=f"{m['id']} {m['name']}")
            for m in sorted(self.mappings, key=lambda m: m["id"])
        ]
        return selector.SelectSelector(selector.SelectSelectorConfig(options=options, multiple=multiple))

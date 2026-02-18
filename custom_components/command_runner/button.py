"""Button platform for Command Runner."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er


from . import CommandRunnerCoordinator

_LOGGER = logging.getLogger(__name__)

DOMAIN = "command_runner"

CONF_SHOW_NOTIFICATIONS = "show_notifications"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Command Runner buttons."""
    coordinator: CommandRunnerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = []

    # Add refresh button
    entities.append(CommandRunnerRefreshButton(coordinator, entry))

    # Add command buttons (only kind == "command")
    for command in coordinator.data:
        if command.get("kind", "command") == "command":
            entities.append(CommandRunnerButton(coordinator, command, entry))

    async_add_entities(entities)


class CommandRunnerRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to refresh Command Runner statistics."""

    def __init__(self, coordinator: CommandRunnerCoordinator, entry: ConfigEntry) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Command Runner Refresh Statistics"
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_icon = "mdi:refresh"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    async def async_press(self) -> None:
        """Handle the button press to refresh statistics."""
        _LOGGER.info("Refreshing Command Runner statistics")
        await self.coordinator.async_request_refresh()

        # Refresh command_runner sensors
        all_ids = self.hass.states.async_entity_ids("sensor")
        command_runner_sensor_ids = [
            eid for eid in all_ids
            if eid.startswith("sensor.command_runner")
            and "_sensor" not in eid.lower()
        ]

        _LOGGER.debug("Found %d command_runner sensor IDs: %s",
                      len(command_runner_sensor_ids), command_runner_sensor_ids)

        for entity_id in command_runner_sensor_ids:
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_id},
                    blocking=True,
                )
                _LOGGER.debug("Refreshed %s", entity_id)
            except Exception as e:
                _LOGGER.error("Failed to refresh %s: %s", entity_id, e)

        # Notifications
        show_notifications = self._entry.options.get(CONF_SHOW_NOTIFICATIONS, True)
        if show_notifications:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Command Runner",
                    "message": "Statistics and sensors refreshed successfully",
                    "notification_id": f"{DOMAIN}_refresh_{self.coordinator.host}",
                },
            )




class CommandRunnerButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Command Runner button."""

    def __init__(
        self,
        coordinator: CommandRunnerCoordinator,
        command: dict,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._command = command
        self._attr_name = command["name"]
        self._attr_unique_id = f"{entry.entry_id}_{command['name']}"
        self._attr_icon = "mdi:play-circle"

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": f"Command Runner ({self.coordinator.host})",
            "manufacturer": "Command Runner",
            "model": "Mac Command Executor",
        }

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return {
            "command": self._command.get("command"),
            "allow_parameters": self._command.get("allowParameters", False),
            "voice_trigger": self._command.get("voice", ""),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        command_name = self._command["name"]
        _LOGGER.info("Executing command: %s", command_name)

        result = await self.coordinator.execute_command(command_name)

        # Check if notifications are enabled
        show_notifications = self._entry.options.get(CONF_SHOW_NOTIFICATIONS, True)

        if result.get("success"):
            _LOGGER.info("Command executed successfully: %s", command_name)

            if show_notifications:
                # Extract output from result
                output = result.get("output", "").strip()
                exit_code = result.get("exitCode", 0)

                # Build success message
                if output:
                    message = (
                        f"**Command:** {command_name}\n\n"
                        f"**Output:**\n```\\n{output}\\n```\n\n"
                        f"**Exit Code:** {exit_code}"
                    )
                else:
                    message = (
                        f"Command '{command_name}' executed successfully "
                        f"with exit code {exit_code}"
                    )

                # Show success notification
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"✅ Command Success: {command_name}",
                        "message": message,
                        "notification_id": f"{DOMAIN}_{self.unique_id}",
                    },
                )

        else:
            error_message = result.get("error", "Unknown error")
            _LOGGER.error("Command failed: %s", error_message)

            if show_notifications:
                # Show error notification
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": f"❌ Command Failed: {command_name}",
                        "message": (
                            f"**Error:** {error_message}\n\n"
                            f"**Command:** {command_name}"
                        ),
                        "notification_id": f"{DOMAIN}_{self.unique_id}",
                    },
                )

        # Refresh statistics after command execution
        await self.coordinator.async_request_refresh()

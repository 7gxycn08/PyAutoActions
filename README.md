# PyAutoActions

PyAutoActions automates HDR management for your games and applications, enabling and disabling HDR based on the process status. It's designed to work seamlessly with low system impact and integrates perfectly with [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for enhanced compatibility.

## Features

- **Automatic HDR Toggle**: Automatically enables HDR when a game starts and disables it upon closure.
- **Low System Impact**: Operates efficiently using only 3 threads and minimal CPU usage.
- **Tray Functionality**: Resides in the system tray for easy access and minimal interference.
- **Game Launcher**: Launch games directly from the system tray to ensure HDR settings are correctly applied.
- **Compatibility**: Works in tandem with ForceAutoHDR for games not officially supported by AutoHDR.

![PyAutoActions Interface](https://github.com/7gxycn08/PyAutoActions/assets/121936658/397c1e03-bd75-4cbf-aa47-5aedf4f1e8b3)

![System Tray Example](https://github.com/7gxycn08/PyAutoActions/assets/121936658/8375da5c-210b-4633-b8cb-768e5c37cc54)

## Detection Settings

- **Adjustable Sensitivity**: Choose from `High`, `Medium`, or `Low` sensitivity for HDR switching.
- **User Preferences**: Settings are saved and automatically applied on application restart.

## Getting Started

1. **Add Games**: Use the GUI to add the executable path of your games.
2. **Automatic HDR Management**: HDR will enable when a game starts and disable upon its closure.
3. **Startup Option**: Enable running PyAutoActions at system boot via the tray icon context menu.
4. **Enhanced Compatibility**: Use [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for AutoHDR in unsupported games.
5. **Pre-Launch HDR Activation**: Launch games from the system tray to ensure HDR is enabled beforehand when games require HDR to be enabled before launch.

## Latest Changes

- Dynamic HDR toggling for added/removed games without restarting.
- Implementation of a ctypes method to check the global HDR state.
- Enhanced method for enabling/disabling HDR dynamically.

## Contributing

Your contributions make PyAutoActions better! We welcome pull requests, feature requests, and any other contributions. If you're looking to add new features or improve existing ones, please feel free to contribute.

## TODO

- Explore additional functionalities.
- Encourage community contributions and feature requests.


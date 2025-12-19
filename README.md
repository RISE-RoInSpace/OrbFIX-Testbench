# OrbFIX-Testbench

The OrbFIX Equipment Testbench is a Python-based command-line tool designed to demonstrate and exercise the OrbFIX command interface.

### Installation

#### Prerequisites
- Python 3.12 or newer
- Access to an OrbFIX device via RS-422 interface

#### Linux
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

#### Windows (PowerShell)
```bash
python3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install windows-curses
pip install -e .
```

### Usage

All interactions are performed through the ```orbfix``` command:
```bash
orbfix cmd <group> <command> [options]
```

Command output can be logged by redirecting standard output in the shell, for example:
```bash
orbfix cmd version get --sysid=0x6A >> orbfix.log
```

#### System IDs
Many commands require a system identifier to target a specific OrbFIX subsystem.
```bash
System ID	Description
0x7a	OrbFIX-CTL
0x6a	OrbFIX-GNSS Slot A
0x6b	OrbFIX-GNSS Slot B
0x6c	OrbFIX-GNSS Slot C
```

The application is written in typer and it features ```--help`` at any command interaction.

#### Command-Line Interface
The application is implemented using Typer.

As a result:
- every command and subcommand supports the ```--help``` option.
- help can be invoked at any level of the command hierarchy.
- arguments and options are type-checked and validated.

Examples:
```bash
orbfix --help
orbfix cmd --help
orbfix cmd version --help
```

#### Example commands
Below is a non-exhaustive list of commonly used commands:
```bash
orbfix cmd config set-port <port_name>
orbfix cmd version get --sysid=<system_id>
orbfix cmd housekeeping get --sysid=<system_id>
orbfix cmd orbfix_gnss_power set --payload=<payload_id>
```
Use --help with any command to view detailed usage information.

#### Monitor
The ```monitor``` command's purpose is to visualize the NMEA output of OrbFIX in real time.
```bash
orbfix cmd monitor start --sysid=<system_id>
```

## Notes
- Ensure the correct serial port is configured before issuing commands.
- Always verify the target System ID to avoid unintended operations.
- This tool is intended for testing and reference purposes and is not designed for production or flight use.
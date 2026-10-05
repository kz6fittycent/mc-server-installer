"""Command-line access to the background service, for testing and support.

    mc-server-installer.ctl REQUEST [key=value ...] [--upload FILE]

For example:  status | log since=0 | download | accept-eula | start ram_mb=4096
| stop | command text="say hi" | whitelist name=Steve | backup | list-backups
and, with sudo:  set-owner user=NAME
"""

import json
import sys

from mcsi import client


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 2
    cmd, fields, upload = argv[0], {}, None
    rest = argv[1:]
    while rest:
        item = rest.pop(0)
        if item == "--upload":
            upload = rest.pop(0)
        elif "=" in item:
            key, value = item.split("=", 1)
            fields[key] = int(value) if value.isdigit() else value
        else:
            print(f"Not key=value: {item}", file=sys.stderr)
            return 2
    try:
        reply = client.request(cmd, upload=upload, **fields)
    except client.ServiceError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(reply, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
